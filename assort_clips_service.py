import json
import asyncio

from config import STREAM_METADATA_TABLE
from utils.logger import app_logger as logger
from utils.helpers import get_video_frame_filename
from repositories.aurora_service import AuroraService

class AssortClipsService:
    def __init__(self):
        self.is_db_service_initialized = False
        self.db_service = AuroraService(pool_size=10)

    async def intialize_db_service(self):
        if not self.is_db_service_initialized:
            logger.info("[AudioTranscriber] Initializing DB Connection")
            await self.db_service.initialize()
            self.is_db_service_initialized = True
        
    def get_one_groups(self, arr):
        groups = []
        start = None

        for i, val in enumerate(arr):
            if val == 1 and start is None:
                start = i  # start of a new group
            elif val == 0 and start is not None:
                groups.append((start, i - 1))  # end of a group
                start = None

        # If array ends with 1s, close the last group
        if start is not None:
            groups.append((start, len(arr) - 1))

        return groups
    
    def consolidate_groups(self, groups):
        if not groups:
            return []

        consolidated = [groups[0]]

        for start, end in groups[1:]:
            prev_start, prev_end = consolidated[-1]

            # If the new group starts just one index after the previous group ends
            if start - prev_end == 2:  
                # Merge the groups
                consolidated[-1] = (prev_start, end)
            else:
                consolidated.append((start, end))

        return consolidated
    
    async def assort_clips(self, stream_id, audio_processor_event: asyncio.Event, video_processor_event: asyncio.Event):
        should_break = False
        i = 0
        await self.intialize_db_service()
        while True:
            if should_break:
                logger.info("[AssortClipsService] exiting assort clips service.")
                break
            
            scored_clips = await self.db_service.get_scored_clips_by_stream(stream_id, i, i+300)

            if len(scored_clips) < 100:
                if audio_processor_event.is_set() and video_processor_event.is_set():
                    should_break = True
                else:
                    logger.info("[AssortClipsService] waiting for data to become available...")
                    await asyncio.sleep(5)
                    continue
            
            potential_highlights = []
            # Write the logic
            for clip in scored_clips:
                saliency_score = clip["saliency_score"]
                highlight_score = clip["highlight_score"]
                if (highlight_score >= 0.7) or (saliency_score >= 0.8 and highlight_score >= 0.6):
                    potential_highlights.append(1)
                else:
                    potential_highlights.append(0)

            highlight_groups = self.consolidate_groups(self.get_one_groups(potential_highlights))

            highlights = []

            for (start_idx, end_idx) in highlight_groups:
                highlight = {
                    "start_time": scored_clips[start_idx]["start_time"],
                    "end_time": scored_clips[end_idx]["end_time"],
                    "caption": ' '.join(scored_clips[start_idx:end_idx+1]),
                    "thumbnail": get_video_frame_filename(i),
                }
                highlights.append(highlight)

            logger.info(f"[AssortClipsService] generated highlights {highlights}")

            await self.db_service.update_dict(
                STREAM_METADATA_TABLE, 
                {"highlights": json.dumps(highlights)},
                where_clause="stream_id=%s",
                where_params=(stream_id,)
            )
            
