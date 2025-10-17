import cv2
import asyncio
import librosa
import numpy as np

from typing import List
from llm.claude import Claude
from candidate_clip import CandidateClip
from utils.logger import app_logger as logger
from audio_transcriber import AudioTranscriber
from repositories.aurora_service import AuroraService
from utils.helpers import numpy_to_base64, EMPTY_STRING, ERROR_STRING
from config import (
    VIDEO_FRAME_SAMPLE_RATE, 
    BASE_DIR, 
    CANDIDATE_SLICE, 
    STEP_BACK,
    AUDIO_CHUNK,
    SCORE_METADATA_TABLE
)

CAPTION_AND_SCORER_PROMPT = """
    You are an expert video editor and story curator.
    Your job is to evaluate whether a given sequence of video frames (images) and its corresponding audio transcript together represent a *highlight-worthy* moment.
    
    ---
    
    ### 1. Your Analysis Should Consider:
        **Visual elements**
        - Actions, emotions, expressions, reactions, motion, or significant visual changes.
        - Visual storytelling cues such as crowd reactions, celebrations, tension, or setup moments.
        - Aesthetic or cinematic appeal (beautiful, dramatic, or funny visuals).
    
    **Audio / Transcript content**
        - Emotional tone (excitement, laughter, suspense, sadness, inspiration, anger, etc.)
        - Important statements, turning points, or quotable lines.
        - Voice intensity, crowd reactions, or dramatic pauses that enhance impact.
    
    ---
    
    ### 2. Scoring Guidelines:
        Return a *highlight_score* between **0.0 and 1.0** (with 1 decimal place):
            - **1.0** → Peak highlight (visually/emotionally intense, memorable, or pivotal)
            - **0.7-0.9** → Strong highlight (not the climax, but very engaging or significant)
            - **0.4-0.6** → Moderately interesting (some value, but not standout)
            - **0.1-0.3** → Lowlight (routine, setup, or background)
            - **0.0** → Not a highlight (irrelevant, static, filler)
    
    **Important:** 
        Setup or anticipation moments (e.g. “speaker about to announce results,” “dramatic pause before reveal”) *can* be moderately or highly highlight-worthy if they build emotional or narrative tension.
    
    ---
    
    ### 3. Your Output:
        Return a short, vivid **caption** (≤ 15 words) summarizing what's happening overall, and a numeric **highlight_score**.
    
    ---
    
    ### 4. Examples
    
    **Example 1**
        Frames: [Image of soccer player dribbling, Image of goal kick, Image of cheering crowd]  
        Transcript: “And he shoots—what a goal! Unbelievable finish from Ronaldo!”  
        Output:
        {
            "caption": "Ronaldo scores a spectacular goal as the crowd erupts",
            "highlight_score": 1.0
        }
    
    **Example 2**
        Frames: [Team huddle before kickoff, focused faces, crowd cheering softly]  
        Transcript: “Let's go out there and give it everything we've got.”  
        Output:
        {
            "caption": "Team huddles with determination before the match",
            "highlight_score": 0.7
        }
    
    **Example 3**
        Frames: [Presenter opening laptop, static slides]  
        Transcript: “Next, we'll review last quarter's performance.”  
        Output:
        {
            "caption": "Presenter begins reviewing quarterly performance",
            "highlight_score": 0.2
        }
    
    **Example 4**
        Frames: [Close-up of guest tearing up, host nodding sympathetically]  
        Transcript: “It was the hardest time of my life, but it made me stronger.”  
        Output:
        {
            "caption": "Guest shares an emotional personal story",
            "highlight_score": 0.9
        }
    
    ---
    
    ### 5. Output Format (JSON)
    {
        "caption": "...",
        "highlight_score": ...
    }
    Do not add anything extra.
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

    async def intialize_db_service(self):
        if not self.is_db_service_initialized:
            logger.info("[AudioTranscriber] Initializing DB Connection")
            await self.db_service.initialize()
            self.is_db_service_initialized = True

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
        while True:
            if should_break:
                logger.info("[ClipScorerService] exiting saliency scorer service.")
                clip_scorer_event.set()
                break
            start_time, end_time = self._get_slice(i)
            candidate_clip = CandidateClip(base_path, start_time, end_time)
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

            frame_metdata = await self.db_service.get_videos_by_stream(
                stream_id=stream_id, 
                start_frame=start_time*VIDEO_FRAME_SAMPLE_RATE,
                limit=CANDIDATE_SLICE*VIDEO_FRAME_SAMPLE_RATE
            )       
            
            if (len(frame_metdata) != CANDIDATE_SLICE * VIDEO_FRAME_SAMPLE_RATE) or (len(audio_metadata) != len(audio_chunk_indexes)):
                if audio_processor_event.is_set() and video_processor_event.is_set():
                    should_break = True
                    if not audio_metadata or not frame_metdata:
                        continue
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
            