import cv2
import asyncio
import librosa
import numpy as np

from typing import List
from llm.claude import Claude
from candidate_clip import CandidateClip
from utils.logger import app_logger as logger
from repositories.aurora_service import AuroraService
from utils.helpers import numpy_to_base64, EMPTY_STRING
from config import (
    VIDEO_FRAME_SAMPLE_RATE, 
    BASE_DIR, 
    CANDIDATE_SLICE, 
    STEP_BACK,
    AUDIO_CHUNK,
    SCORE_METADATA_TABLE
)

class CaptionService:
    def __init__(self):
        self.llm = Claude()

    async def generate_clip_caption(self, candidate_clip: CandidateClip, audio_metadata: List):
        transcript = candidate_clip.get_transcript(audio_metadata)
        images = [numpy_to_base64(img) for img in candidate_clip.load_images()]
        response = self.llm.invoke(prompt="", response_type="json", query=transcript, images=images, max_tokens=500)
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

    async def intialize_db_service(self):
        if not self.is_db_service_initialized:
            logger.info("[AudioTranscriber] Initializing DB Connection")
            await self.db_service.initialize()
            self.is_db_service_initialized = True
    
    def get_slice_saliency_score(self, candidate_clip: CandidateClip):
        audio = candidate_clip.load_audio_segment(AUDIO_CHUNK)
        frames = candidate_clip.load_images()
        return self.scorer.compute_saliency(frames, audio)
    
    def _get_slice(self, i):
        start = i * CANDIDATE_SLICE
        end = start + CANDIDATE_SLICE
        if start > 0:
            return start - STEP_BACK, end - STEP_BACK
        else:
            return 0, 5
    
    async def score_clips(self, stream_id, audio_processor_event: asyncio.Event, video_processor_event: asyncio.Event):
        base_path = f"{BASE_DIR}/{stream_id}"
        should_break = False
        i = 0
        await self.intialize_db_service()
        while True:
            if should_break:
                logger.info("[SaliencyScorerService] exiting saliency scorer service.")
                break
            start_time, end_time = self._get_slice(i)
            candidate_clip = CandidateClip(base_path, start_time, end_time)
            audio_chunk_indexes = candidate_clip.get_audio_chunk_indexes(AUDIO_CHUNK)

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

            if not all([meta["transcript"] != EMPTY_STRING for meta in audio_metadata]):
                await asyncio.sleep(0.5)
                continue

            frame_metdata = await self.db_service.get_videos_by_stream(
                stream_id=stream_id, 
                start_frame=start_time*VIDEO_FRAME_SAMPLE_RATE,
                limit=CANDIDATE_SLICE*VIDEO_FRAME_SAMPLE_RATE
            )       
            
            if len(frame_metdata) != CANDIDATE_SLICE * VIDEO_FRAME_SAMPLE_RATE or len(audio_metadata) != len(audio_chunk_indexes):
                if audio_processor_event.is_set() and video_processor_event.is_set():
                    should_break = True
                else:
                    await asyncio.sleep(0.2)
                    continue
            
            score = self.get_slice_saliency_score(candidate_clip)
            highlight_score, caption = await self.caption_service.generate_clip_caption(candidate_clip, audio_metadata)
            metadata = {
                "stream_id": stream_id,
                "start_time": start_time,
                "end_time": end_time,
                "saliency_score": score,
                "caption": caption,
                "highlight_score": highlight_score
            }
            await self.db_service.insert_dict(SCORE_METADATA_TABLE, metadata)
            i += 1
            