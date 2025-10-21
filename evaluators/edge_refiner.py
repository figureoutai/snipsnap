import os
import math
import json
from typing import Dict, List, Tuple, Optional

import cv2

from utils.logger import app_logger as logger
from utils.helpers import numpy_to_base64, EMPTY_STRING, ERROR_STRING
from repositories.aurora_service import AuroraService
from candidate_clip import CandidateClip
from config import AUDIO_CHUNK, VIDEO_FRAME_SAMPLE_RATE
from agents.edge_refiner_agent import StrandsEdgeRefinerAgent


LLM_EDGE_REFINER_PROMPT = """
You are an expert highlight refiner.

Decide using tools only:
- Call exactly one of: choose_keep | choose_topic | choose_scene | choose_micro_adjust.
- If you choose micro_adjust, provide deltas within the allowed ranges.
- Then call emit_plan(action, start_delta, end_delta, reason, confidence) as your final step.

Do not perform snapping or clamping — those are handled downstream.
Prefer transcript coherence; use scene cues if transcript is weak.
"""


class EdgeRefiner:
    def __init__(self, db_pool_size: int = 5):
        self.db = AuroraService(pool_size=db_pool_size)
        self._db_ready = False
        self._agent = StrandsEdgeRefinerAgent()

    async def _ensure_db(self):
        if not self._db_ready:
            await self.db.initialize()
            self._db_ready = True

    def _load_frame(self, frames_dir: str, idx: int) -> Optional[cv2.Mat]:
        if idx < 0:
            return None
        path = os.path.join(frames_dir, f"frame_{idx:09d}.jpg")
        if not os.path.exists(path):
            return None
        return cv2.imread(path)

    def _edge_and_key_frames(self, base_path: str, start: float, end: float, max_mid_frames: int = 3) -> List[str]:
        frames_dir = os.path.join(base_path, "frames")
        fps = VIDEO_FRAME_SAMPLE_RATE
        start_idx = int(start * fps)
        end_idx = int(end * fps)

        imgs: List[str] = []
        for idx in [start_idx - 1, start_idx]:
            img = self._load_frame(frames_dir, idx)
            if img is not None:
                imgs.append(numpy_to_base64(img))

        total = max(0, end_idx - start_idx)
        if total > 2 and max_mid_frames > 0:
            for k in range(1, max_mid_frames + 1):
                pos = start_idx + math.floor(k * total / (max_mid_frames + 1))
                if pos <= start_idx or pos >= end_idx:
                    continue
                img = self._load_frame(frames_dir, pos)
                if img is not None:
                    imgs.append(numpy_to_base64(img))

        for idx in [end_idx - 1, end_idx]:
            img = self._load_frame(frames_dir, idx)
            if img is not None:
                imgs.append(numpy_to_base64(img))

        return imgs

    async def _transcript_for_window(self, stream_id: str, clip: CandidateClip) -> str:
        await self._ensure_db()
        chunks = clip.get_audio_chunk_indexes(AUDIO_CHUNK)
        if not chunks:
            return EMPTY_STRING
        if len(chunks) == 1:
            rows = await self.db.get_audios_by_stream(stream_id=stream_id, start_chunk=chunks[0], limit=1)
        else:
            rows = await self.db.get_audios_by_stream(stream_id=stream_id, start_chunk=chunks[0], end_chunk=chunks[-1])
        # Filter error/empty transcripts defensively using project sentinel values
        rows = [
            r for r in rows
            if r.get("transcript") and r["transcript"] not in (EMPTY_STRING, ERROR_STRING)
        ]
        return clip.get_transcript(rows)

    def _nearest(self, t: float, arr: List[float]) -> Tuple[Optional[float], Optional[float]]:
        if not arr:
            return None, None
        best = min(arr, key=lambda x: abs(x - t))
        return best, (best - t)

    async def refine(
        self,
        stream_id: str,
        base_path: str,
        snapped_start: float,
        snapped_end: float,
        topic_boundaries: List[float],
        scene_boundaries: List[float],
        min_len: float,
        max_len: float,
        start_delta_range: Tuple[float, float] = (-1.0, 1.0),
        end_delta_range: Tuple[float, float] = (-1.5, 1.5),
    ) -> Dict:
        # Build context JSON block
        ts_start_topic, d_start_topic = self._nearest(snapped_start, topic_boundaries)
        ts_start_scene, d_start_scene = self._nearest(snapped_start, scene_boundaries)
        ts_end_topic, d_end_topic = self._nearest(snapped_end, topic_boundaries)
        ts_end_scene, d_end_scene = self._nearest(snapped_end, scene_boundaries)

        ctx = {
            "window": {
                "snapped_start": round(snapped_start, 3),
                "snapped_end": round(snapped_end, 3),
                "duration": round(snapped_end - snapped_start, 3),
                "min_len": min_len,
                "max_len": max_len,
                "fps": VIDEO_FRAME_SAMPLE_RATE,
            },
            "boundaries": {
                "start": {
                    "topic_candidate_sec": None if ts_start_topic is None else round(ts_start_topic, 3),
                    "topic_delta_sec": None if d_start_topic is None else round(d_start_topic, 3),
                    "scene_candidate_sec": None if ts_start_scene is None else round(ts_start_scene, 3),
                    "scene_delta_sec": None if d_start_scene is None else round(d_start_scene, 3),
                },
                "end": {
                    "topic_candidate_sec": None if ts_end_topic is None else round(ts_end_topic, 3),
                    "topic_delta_sec": None if d_end_topic is None else round(d_end_topic, 3),
                    "scene_candidate_sec": None if ts_end_scene is None else round(ts_end_scene, 3),
                    "scene_delta_sec": None if d_end_scene is None else round(d_end_scene, 3),
                },
            },
            "limits": {
                "start_delta_range_sec": list(start_delta_range),
                "end_delta_range_sec": list(end_delta_range),
            },
        }

        # Transcript & images
        clip = CandidateClip(base_path, snapped_start, snapped_end)
        transcript = await self._transcript_for_window(stream_id, clip)
        images = self._edge_and_key_frames(base_path, snapped_start, snapped_end)

        queries = [json.dumps(ctx), f"Transcript (inside window):\n{transcript or ''}"]

        # Use Strands Agent with native @tool flow
        try:
            instruction = (
                f"{LLM_EDGE_REFINER_PROMPT}\n\n"
                "Tool protocol: 1) choose_*; 2) emit_plan. Do not free-type text."
            )
            ctx_text = "\n\n".join(q for q in queries if q)
            prompt = (
                f"{instruction}\n\n"
                f"orig_start={snapped_start:.3f}; orig_end={snapped_end:.3f};\n"
                f"min_len={min_len:.2f}; max_len={max_len:.2f};\n"
                f"start_delta_range={list(start_delta_range)}; end_delta_range={list(end_delta_range)};\n"
                f"topics={topic_boundaries}; scenes={scene_boundaries};\n\n"
                f"{ctx_text}"
            )
            output = await self._agent.invoke_async(prompt)
            parsed = json.loads(output) if isinstance(output, str) else output
            action = str(parsed.get("action", "keep")).lower().strip()
            start_delta = float(parsed.get("start_delta", 0.0))
            end_delta = float(parsed.get("end_delta", 0.0))
            reason = str(parsed.get("reason", ""))
            confidence = float(parsed.get("confidence", 0.0))
            return {
                "action": action,
                "start_delta": start_delta,
                "end_delta": end_delta,
                "reason": reason,
                "confidence": confidence,
            }
        except Exception as e:
            logger.warning(f"[EdgeRefiner] Strands agent refine failed: {e}")
            return {"action": "keep", "start_delta": 0.0, "end_delta": 0.0, "reason": "fallback-keep", "confidence": 0.0}
