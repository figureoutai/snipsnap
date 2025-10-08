import av
import os
import cv2
import asyncio
import librosa
import numpy as np

from utils.logger import app_logger as logger
from candidate_clip import CandidateClip
from utils.helpers import get_audio_filename, get_video_frame_filename
from config import VIDEO_FRAME_SAMPLE_RATE, BASE_DIR, CANDIDATE_SLICE, STEP_BACK, AUDIO_CHUNK


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


class SaliencyScorerService:
    def __init__(self):
        self.scorer = SaliencyScorer()
    
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
    
    async def score_saliency(self, stream_id, audio_processor_event: asyncio.Event, video_processor_event: asyncio.Event):
        base_path = f"{BASE_DIR}/{stream_id}"
        should_break = False
        i = 0
        while True:
            if should_break:
                break
            start_time, end_time = self._get_slice(i)
            candidate_clip = CandidateClip(base_path, start_time, end_time)
            audio_chunk_indexes = candidate_clip.get_audio_chunk_indexes(AUDIO_CHUNK)

            frame_metdata = [] # TODO: get frame metadata from aurora offset = start_time * VIDEO_FRAME_SAMPLE_RATE, limit = CANDIDATE_SLICE * VIDEO_FRAME_SAMPLE_RATE
            audio_metdata = [] # TODO: get audio metadata from aurora, for audio chunk indexes
            
            if len(frame_metdata) != CANDIDATE_SLICE * VIDEO_FRAME_SAMPLE_RATE or len(audio_metdata) != len(audio_chunk_indexes):
                if audio_processor_event.is_set() and video_processor_event.is_set():
                    should_break = True
                else:
                    await asyncio.sleep(0.2)
                    continue
            
            score = self.get_slice_saliency_score(start_time, end_time, base_path)
            # TODO: store the data in saliency score table
            metadata = {
                "stream_id": stream_id,
                "start_time": start_time,
                "end_time": end_time,
                "saliency_score": score,
                "caption": "",
                "highlight_score": 0
            }
            i += 1


if __name__ == "__main__":
    scorer = SaliencyScorerService()
    for i in range(0, 25):
        start = i * 5
        end = start + 5
        if start > 0:
            scorer.score_saliency(start-2, end-2)
        else:
            scorer.score_saliency(0, 5)




