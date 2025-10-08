import asyncio

from typing import List
from llm.claude import Claude
from asyncio import Event as AsyncEvent
from candidate_clip import CandidateClip
from utils.logger import app_logger as logger
from utils.helpers import numpy_to_base64, run_sync_func
from config import BASE_DIR, AUDIO_CHUNK, CANDIDATE_SLICE, VIDEO_FRAME_SAMPLE_RATE

class CaptionService:
    def __init__(self):
        self.llm = Claude()

    async def generate_clip_caption(self, candidate_clip: CandidateClip, audio_metadata: List):
        transcript = candidate_clip.get_transcript(audio_metadata)
        images = [numpy_to_base64(img) for img in candidate_clip.load_images()]
        response = self.llm.invoke(prompt="", response_type="json", query=transcript, images=images, max_tokens=500)
        return response["highlight_score"], response["caption"]

    async def generate_captions(self, stream_id, audio_processor_event: AsyncEvent, video_processor_event: AsyncEvent):
        base_path = f"{BASE_DIR}/{stream_id}"
        should_break = False
        i = 0
        while True:
            if should_break:
                logger.info("[CaptionService] exiting caption service.")
                break
            start_time, end_time = self._get_slice(i)
            candidate_clip = CandidateClip(base_path, start_time, end_time)
            audio_chunk_indexes = candidate_clip.get_audio_chunk_indexes(AUDIO_CHUNK)

            frame_metdata = [] # TODO: get frame metadata from aurora offset = start_time * VIDEO_FRAME_SAMPLE_RATE, limit = CANDIDATE_SLICE * VIDEO_FRAME_SAMPLE_RATE
            audio_metadata = [] # TODO: get audio metadata from aurora, for audio chunk indexes
            
            if len(frame_metdata) != CANDIDATE_SLICE * VIDEO_FRAME_SAMPLE_RATE or len(audio_metadata) != len(audio_chunk_indexes):
                if audio_processor_event.is_set() and video_processor_event.is_set():
                    should_break = True
                else:
                    await asyncio.sleep(0.2)
                    continue
            
            highlight_score, caption = await run_sync_func(self.generate_clip_caption, candidate_clip, audio_metadata)
            # TODO: store the data in saliency score table
            metadata = {
                "stream_id": stream_id,
                "start_time": start_time,
                "end_time": end_time,
                "caption": caption,
                "highlight_score": highlight_score
            }
            i += 1