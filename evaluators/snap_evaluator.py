import os
import math
import json
from typing import Dict, List, Tuple, Optional

import cv2

from llm.claude import Claude
from utils.logger import app_logger as logger
from utils.helpers import numpy_to_base64, get_video_frame_filename, EMPTY_STRING
from repositories.aurora_service import AuroraService
from candidate_clip import CandidateClip
from config import AUDIO_CHUNK, VIDEO_FRAME_SAMPLE_RATE


LLM_COMPARE_PROMPT = """
You are an expert video editor. Compare two highlight candidates (Original vs Snapped)
from the same source. Choose the one that is a better highlight based on:
- Clean boundaries (scene/topic change; not cutting words or actions mid-step).
- Visual coherence (motion/emotion continuity) and narrative completeness.
- Audio/Transcript coherence (no truncated words; meaningful content).

Return strict JSON: {"winner":"original|snapped","confidence":float,"rationale":"..."}
Do not include extra text.
"""


class SnapEvaluator:
    """
    LLM-based evaluator to decide whether a snapped window is better than the
    original window for a given stream.

    It prepares a compact set of images (edge and mid frames) and transcripts for
    both candidates and asks the LLM to choose. This is not wired into the
    pipeline yet — intended to be called from assort_clips stage.
    """

    def __init__(self, db_pool_size: int = 5):
        self.llm = Claude()
        self.db = AuroraService(pool_size=db_pool_size)
        self._db_ready = False

    async def _ensure_db(self):
        if not self._db_ready:
            await self.db.initialize()
            self._db_ready = True

    def _load_frame(self, frames_dir: str, idx: int) -> Optional[cv2.Mat]:
        if idx < 0:
            return None
        path = os.path.join(frames_dir, get_video_frame_filename(idx))
        if not os.path.exists(path):
            return None
        return cv2.imread(path)

    def _edge_and_key_frames(
        self, base_path: str, start: float, end: float, max_mid_frames: int = 3
    ) -> List[cv2.Mat]:
        """
        Collect a compact set of frames around the window edges plus a few mid frames.
        Order: [pre-start (opt), start, mids..., end-1 (opt), post-end (opt)]
        """
        frames_dir = os.path.join(base_path, "frames")
        fps = VIDEO_FRAME_SAMPLE_RATE
        start_idx = int(start * fps)
        end_idx = int(end * fps)

        imgs: List[cv2.Mat] = []
        # Pre-start (outside)
        pre = self._load_frame(frames_dir, start_idx - 1)
        if pre is not None:
            imgs.append(pre)
        # Start (inside)
        s_img = self._load_frame(frames_dir, start_idx)
        if s_img is not None:
            imgs.append(s_img)

        # Mid frames (inside)
        total = max(0, end_idx - start_idx)
        if total > 2 and max_mid_frames > 0:
            # Spread mid points between (start_idx+1) .. (end_idx-1)
            mids: List[int] = []
            for k in range(1, max_mid_frames + 1):
                pos = start_idx + math.floor(k * total / (max_mid_frames + 1))
                if pos <= start_idx or pos >= end_idx:
                    continue
                mids.append(pos)
            for mi in mids:
                m_img = self._load_frame(frames_dir, mi)
                if m_img is not None:
                    imgs.append(m_img)

        # End-1 (inside last frame)
        e_img = self._load_frame(frames_dir, end_idx - 1)
        if e_img is not None:
            imgs.append(e_img)

        # Post-end (outside)
        post = self._load_frame(frames_dir, end_idx)
        if post is not None:
            imgs.append(post)

        return imgs

    async def _transcript_for_window(self, stream_id: str, clip: CandidateClip) -> str:
        # Fetch required audio rows for this window
        await self._ensure_db()
        chunks = clip.get_audio_chunk_indexes(AUDIO_CHUNK)
        rows = []
        if not chunks:
            return EMPTY_STRING
        if len(chunks) == 1:
            rows = await self.db.get_audios_by_stream(stream_id=stream_id, start_chunk=chunks[0], limit=1)
        else:
            rows = await self.db.get_audios_by_stream(stream_id=stream_id, start_chunk=chunks[0], end_chunk=chunks[-1])
        return clip.get_transcript(rows)

    async def compare(
        self,
        stream_id: str,
        base_path: str,
        original: Tuple[float, float],
        snapped: Tuple[float, float],
    ) -> Dict:
        """
        Ask the LLM to choose between the original and snapped windows.

        Returns a dict like:
        {
          "winner": "original"|"snapped",
          "confidence": 0.0-1.0,
          "rationale": str,
          "delta": {"start_shift": float, "end_shift": float}
        }
        """
        o_start, o_end = original
        s_start, s_end = snapped
        delta = {"start_shift": round(s_start - o_start, 3), "end_shift": round(s_end - o_end, 3)}

        # Build candidate clips
        clip_o = CandidateClip(base_path, o_start, o_end)
        clip_s = CandidateClip(base_path, s_start, s_end)

        # Collect images (edge + mids) and transcripts
        imgs_o = [numpy_to_base64(img) for img in self._edge_and_key_frames(base_path, o_start, o_end)]
        imgs_s = [numpy_to_base64(img) for img in self._edge_and_key_frames(base_path, s_start, s_end)]

        tx_o = await self._transcript_for_window(stream_id, clip_o)
        tx_s = await self._transcript_for_window(stream_id, clip_s)

        # Craft user content sequence with clear segment separators
        content_blocks: List[str] = []
        content_blocks.append("Candidate A (Original). Transcript A:" + (tx_o or ""))
        # Images follow via Claude client API
        content_blocks.append("Candidate B (Snapped). Transcript B:" + (tx_s or ""))

        # Compose images: first A images then B images; the prompt documents the order.
        # Claude client expects a single list of messages; we pass text blocks + images.
        # We rely on order: [Text(A), Images(A...), Text(B), Images(B...)]
        queries = content_blocks
        images = imgs_o + imgs_s

        try:
            resp = await self.llm.invoke(
                prompt=LLM_COMPARE_PROMPT,
                response_type="json",
                queries=queries,
                images=images,
                max_tokens=400,
            )
            winner = str(resp.get("winner", "")).strip().lower()
            if winner not in ("original", "snapped"):
                # try to coerce common variants
                if winner in ("a", "candidate a"):
                    winner = "original"
                elif winner in ("b", "candidate b"):
                    winner = "snapped"
                else:
                    winner = "snapped"  # default to snapped if unclear
            confidence = float(resp.get("confidence", 0.5))
            rationale = str(resp.get("rationale", ""))
            return {
                "winner": winner,
                "confidence": confidence,
                "rationale": rationale,
                "delta": delta,
            }
        except Exception as e:
            logger.error(f"[SnapEvaluator] LLM comparison failed: {e}")
            return {
                "winner": "original",
                "confidence": 0.0,
                "rationale": "fallback-original due to LLM error",
                "delta": delta,
            }

