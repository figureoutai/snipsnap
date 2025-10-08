import asyncio

from typing import List
from asyncio import Event as AsyncEvent
from candidate_clip import CandidateClip
from config import BASE_DIR, AUDIO_CHUNK, CANDIDATE_SLICE, VIDEO_FRAME_SAMPLE_RATE

class CaptionService:
    def generate_clip_caption(self, candidate_clip: CandidateClip, audio_metadata: List):
        pass

    async def generate_captions(self, stream_id, audio_processor_event: AsyncEvent, video_processor_event: AsyncEvent):
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
            
            score = self.generate_clip_caption(candidate_clip, audio_metdata)
            # TODO: store the data in saliency score table
            metadata = {
                "stream_id": stream_id,
                "start_time": start_time,
                "end_time": end_time,
                "saliency_score": score,
                "caption": ""
            }
            i += 1