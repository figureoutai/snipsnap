import cv2
import asyncio
import librosa
import numpy as np

import os
import json
from typing import List, Dict
from llm.claude import Claude
from candidate_clip import CandidateClip
from utils.logger import app_logger as logger
from audio_transcriber import AudioTranscriber
from repositories.aurora_service import AuroraService
from utils.helpers import numpy_to_base64, EMPTY_STRING, ERROR_STRING
from detectors.scene_detector import detect_scene_boundaries
from nlp.text_tiling import text_tiling_boundaries
from utils.boundary_snapper import snap_window
from config import (
    VIDEO_FRAME_SAMPLE_RATE, 
    BASE_DIR, 
    CANDIDATE_SLICE, 
    STEP_BACK,
    AUDIO_CHUNK,
    SCORE_METADATA_TABLE,
    SNAP_MAX_SHIFT_SCENE_START,
    SNAP_MAX_SHIFT_SCENE_END,
    SNAP_MAX_SHIFT_TOPIC,
    HIGHLIGHT_MIN_LEN,
    HIGHLIGHT_MAX_LEN,
    TEXT_TILING_BLOCK,
    TEXT_TILING_STEP,
    TEXT_TILING_SMOOTH,
    TEXT_TILING_CUTOFF_STD,
)

CAPTION_AND_SCORER_PROMPT = """
    You are an expert video editor and content curator.
    Your task is to judge if a given set of video frames (images) and the corresponding audio transcript represent a highlight-worthy moment.

    ## You should analyze:
        1. What's visually happening in the frames (motion, emotion, action, etc.)
        2. The spoken content in the transcript (emotion, importance, excitement, etc.)

    ## Then return:
        1. A caption (a short, descriptive summary of what's happening)
        2. A highlight_score between 0 and 1 (with 1 decimal place), where:
            - 1.0 → Extremely highlight-worthy (exciting, emotional, visually or contextually important)
            - 0.0 → Not a highlight at all (irrelevant, static, repetitive, or dull)

    ## Examples:-

        Example 1:
            Frames description: [Image of soccer player dribbling, Image of goal kick, Image of cheering crowd]
            Transcript: “And he shoots—what a goal! Unbelievable finish from Ronaldo!”
            Output:
            {
                "caption": "Ronaldo scores a spectacular goal after dribbling past defenders",
                "highlight_score": 1.0
            }

        Example 2:
            Frames description: [Image of players walking off the field, Image of empty stadium seats]
            Transcript: "We\'ll be back after the break."
            Output:
            {
                "caption": "Players taking a break before the next round",
                "highlight_score": 0.1
            }

        Example 3:
            Frames description: [Image of presenter on stage, Image of confetti, Image of cheering crowd]
            Transcript: "And the winner is… Team Alpha!"
            Output:
            {
                "caption": "Team Alpha announced as the winner amid cheers",
                "highlight_score": 0.9
            }

        Example 4:
            Frames : [Image of person talking calmly during an interview]
            Transcript: "So we started the project in 2018 with just five people."
            Output:
            {
                "caption": "Speaker describes the project's early beginnings",
                "highlight_score": 0.3
            }

    ## Output format (JSON):
        {
            "caption": "...",
            "highlight_score": ...
        }
    **Note**: Do not add anything extra to the output.
"""

class CaptionService:
    def __init__(self):
        self.llm = Claude()

    async def generate_clip_caption(self, candidate_clip: CandidateClip, audio_metadata: List):
        transcript = candidate_clip.get_transcript(audio_metadata)
        logger.info(f"[CaptionService] transcript: {transcript}")
        images = [numpy_to_base64(img) for img in candidate_clip.load_images()]
        response = await self.llm.invoke(prompt=CAPTION_AND_SCORER_PROMPT, response_type="json", queries=[transcript], images=images, max_tokens=500)
        return response["highlight_score"], response["caption"]


class SaliencyScorer:
    def __init__(self, alpha_motion=0.7, alpha_audio=0.3):
        self.alpha_motion = alpha_motion
        self.alpha_audio = alpha_audio

    # ---------- AUDIO ----------
    def compute_audio_rms(self, y: np.ndarray):
        if np.issubdtype(y.dtype, np.integer):
            max_val = np.iinfo(y.dtype).max
            y = y / max_val
        return np.mean(librosa.feature.rms(y=y)[0])

    # ---------- VIDEO (OPTICAL FLOW) ----------
    def compute_motion_score(self, frames: list[np.ndarray]):
        if len(frames) < 2:
            return 0.0
        gray_frames = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in frames]
        magnitudes = []
        for i in range(len(gray_frames) - 1):
            flow = cv2.calcOpticalFlowFarneback(
                gray_frames[i], gray_frames[i + 1], None,
                0.5, 3, 15, 3, 5, 1.2, 0
            )
            mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
            magnitudes.append(np.mean(mag))
        return float(np.mean(magnitudes))

    # ---------- FINAL SCORE ----------
    def compute_saliency(self, frames, audio):
        motion = self.compute_motion_score(frames)
        audio_rms = self.compute_audio_rms(audio)

        # Normalize each (soft)
        motion_n = np.tanh(motion)
        audio_n = np.tanh(audio_rms)

        saliency = (
            self.alpha_motion * motion_n +
            self.alpha_audio * audio_n 
        )
        return float(saliency)

class ClipScorerService:
    def __init__(self):
        self.scorer = SaliencyScorer()
        self.caption_service = CaptionService()
        self.is_db_service_initialized = False
        self.db_service = AuroraService(pool_size=10)
        # Boundary caches per stream_id
        self._scene_boundaries: Dict[str, List[float]] = {}
        self._topic_boundaries: Dict[str, List[float]] = {}
        # Optional: try to read a local video path from env for scene detection
        self._video_path_env = os.environ.get("VIDEO_PATH")

    async def intialize_db_service(self):
        if not self.is_db_service_initialized:
            logger.info("[AudioTranscriber] Initializing DB Connection")
            await self.db_service.initialize()
            self.is_db_service_initialized = True

    # -------- Agentic helpers (Observe -> Plan -> Act) --------
    async def _ensure_scene_boundaries(self, stream_id: str):
        if stream_id in self._scene_boundaries:
            return
        video_path = self._video_path_env
        if video_path and os.path.isfile(video_path):
            try:
                logger.info(f"[ClipScorerService] Detecting scene boundaries for {stream_id}...")
                cuts = detect_scene_boundaries(video_path)
                self._scene_boundaries[stream_id] = cuts
                logger.info(f"[ClipScorerService] Scene boundaries: {len(cuts)} cuts detected.")
            except Exception as e:
                logger.warning(f"[ClipScorerService] Scene detection skipped due to error: {e}")
                self._scene_boundaries[stream_id] = []
        else:
            # No local path; skip scenes (topic boundaries still useful)
            self._scene_boundaries[stream_id] = []

    async def _flatten_transcript_words(self, stream_id: str) -> List[Dict]:
        # Pull all audio chunks seen so far for this stream (ordered)
        rows = await self.db_service.get_audios_by_stream(stream_id=stream_id)
        words: List[Dict] = []
        for row in rows:
            t = row.get("transcript")
            if not t or t in (EMPTY_STRING, ERROR_STRING):
                continue
            try:
                items = json.loads(t)
            except Exception:
                continue
            start0 = float(row.get("start_timestamp") or 0.0)
            for it in items:
                if it.get("type") != "pronunciation":
                    continue
                st = it.get("start_time")
                if st is None:
                    continue
                words.append({
                    "content": it.get("content", ""),
                    "start_time": float(st) + start0,
                    "type": "pronunciation",
                })
        return words

    async def _ensure_topic_boundaries(self, stream_id: str):
        if stream_id in self._topic_boundaries:
            return
        words = await self._flatten_transcript_words(stream_id)
        # Only compute if we have enough tokens for stable boundaries
        if len(words) >= 2 * TEXT_TILING_BLOCK:
            try:
                b = text_tiling_boundaries(
                    words,
                    block_size=TEXT_TILING_BLOCK,
                    step=TEXT_TILING_STEP,
                    smoothing_width=TEXT_TILING_SMOOTH,
                    cutoff_std=TEXT_TILING_CUTOFF_STD,
                )
                self._topic_boundaries[stream_id] = b
                logger.info(f"[ClipScorerService] Topic boundaries: {len(b)} found.")
            except Exception as e:
                logger.warning(f"[ClipScorerService] TextTiling failed: {e}")
                self._topic_boundaries[stream_id] = []
        else:
            self._topic_boundaries[stream_id] = []

    def _snap_window(self, stream_id: str, start: float, end: float):
        scenes = self._scene_boundaries.get(stream_id, [])
        topics = self._topic_boundaries.get(stream_id, [])
        s, e, tags = snap_window(
            start,
            end,
            scene_boundaries=scenes,
            topic_boundaries=topics,
            max_shift_scene_start=SNAP_MAX_SHIFT_SCENE_START,
            max_shift_scene_end=SNAP_MAX_SHIFT_SCENE_END,
            max_shift_topic=SNAP_MAX_SHIFT_TOPIC,
            min_len=HIGHLIGHT_MIN_LEN,
            max_len=HIGHLIGHT_MAX_LEN,
        )
        return s, e, tags

    async def transcribe_leftover_audio_chunks(self, stream_id, audio_chunks):
        transcriber = AudioTranscriber(f"{BASE_DIR}/{stream_id}/audio_chunks")
        for chunk in audio_chunks:
            if chunk["transcript"] == ERROR_STRING:
                filename = chunk["filename"]
                sample_rate = chunk["sample_rate"]
                try:
                    logger.info(f"[ClipScorerService] transcribing audio for leftover {filename}")
                    await transcriber.transcribe_audio_stream(stream_id, filename, sample_rate)
                except Exception as e:
                    logger.error(f"[ClipScorerService] encountered error while transcribing audio {filename}: {str(e)}")

            
    
    def get_slice_saliency_score(self, candidate_clip: CandidateClip):
        audio = candidate_clip.load_audio_segment(AUDIO_CHUNK)
        frames = candidate_clip.load_images()
        return self.scorer.compute_saliency(frames, audio)
    
    def _get_slice(self, i):
        start = i * CANDIDATE_SLICE
        end = start + CANDIDATE_SLICE
        return start, end
    
    async def score_clips(self, stream_id, clip_scorer_event: asyncio.Event, audio_processor_event: asyncio.Event, video_processor_event: asyncio.Event):
        base_path = f"{BASE_DIR}/{stream_id}"
        should_break = False
        i = 0
        await self.intialize_db_service()
        # Observe (once): try to compute scene boundaries if possible
        await self._ensure_scene_boundaries(stream_id)
        while True:
            if should_break:
                logger.info("[ClipScorerService] exiting saliency scorer service.")
                clip_scorer_event.set()
                break
            start_time, end_time = self._get_slice(i)
            # Plan: ensure topic boundaries once transcripts exist
            await self._ensure_topic_boundaries(stream_id)

            # Plan: decide snapped window using boundaries & constraints
            snapped_start, snapped_end, tags = self._snap_window(stream_id, start_time, end_time)
            if (snapped_start, snapped_end) != (start_time, end_time):
                logger.info(f"[ClipScorerService] Snapped window {start_time}-{end_time} -> {snapped_start}-{snapped_end} ({tags})")
            candidate_clip = CandidateClip(base_path, snapped_start, snapped_end)
            audio_chunk_indexes = candidate_clip.get_audio_chunk_indexes(AUDIO_CHUNK)

            logger.info(f"[ClipScorerService] scoring for interval {start_time} - {end_time}.")

            audio_metadata = []
            if len(audio_chunk_indexes) == 1:
                audio_metadata = await self.db_service.get_audios_by_stream(
                    stream_id=stream_id,
                    start_chunk=audio_chunk_indexes[0],
                    limit=1
                )
            else:
                audio_metadata = await self.db_service.get_audios_by_stream(
                    stream_id=stream_id,
                    start_chunk=audio_chunk_indexes[0],
                    end_chunk=audio_chunk_indexes[1]
                )

            if not all([((meta["transcript"] != EMPTY_STRING) and (meta["transcript"] != ERROR_STRING)) for meta in audio_metadata]):
                await self.transcribe_leftover_audio_chunks(stream_id, audio_metadata)
                await asyncio.sleep(0.5)
                continue

            # Ensure a baseline of frames exist near the original schedule; since we may have snapped,
            # do a soft check for the snapped window frames as well (best-effort).
            frame_metdata = await self.db_service.get_videos_by_stream(
                stream_id=stream_id,
                start_frame=int(snapped_start*VIDEO_FRAME_SAMPLE_RATE),
                limit=int(max(1, (snapped_end - snapped_start) * VIDEO_FRAME_SAMPLE_RATE))
            )

            if (len(frame_metdata) == 0) or (len(audio_metadata) != len(audio_chunk_indexes)):
                if audio_processor_event.is_set() and video_processor_event.is_set():
                    should_break = True
                    if not audio_metadata or not frame_metdata:
                        continue
                else:
                    await asyncio.sleep(0.2)
                    continue
            
            # Act: compute saliency & caption on the snapped window
            score = self.get_slice_saliency_score(candidate_clip)
            highlight_score, caption = await self.caption_service.generate_clip_caption(candidate_clip, audio_metadata)
            metadata = {
                "stream_id": stream_id,
                "start_time": snapped_start,
                "end_time": snapped_end,
                "saliency_score": score,
                "caption": caption,
                "highlight_score": highlight_score
            }
            await self.db_service.insert_dict(SCORE_METADATA_TABLE, metadata)
            i += 1
            
