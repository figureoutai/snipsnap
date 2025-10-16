import json
import asyncio

from typing import List
from llm.claude import Claude
from config import STREAM_METADATA_TABLE
from utils.logger import app_logger as logger
from utils.helpers import get_video_frame_filename
from repositories.aurora_service import AuroraService

GROUPING_AND_TITLE_PROMPT = """
    You are an AI assistant that groups sentences describing the same event. Follow these steps for each input:
        1. Read all sentences carefully.
        2. Compare each sentence to identify which sentences belong to the same event.
        3. Think step-by-step as you decide which sentences belong together.
        4. Assign sentences to groups.
        5. Give each group a short descriptive title.
        6. For each group, return only the start and the end indexes (0-based) of the sentences in that group. If there is only one sentence the start and end index will be the same. 
        7. Return the output as a valid JSON format exactly like the example below. No need to return the reasoning.

    ---

    ### Few-Shot Example 1
        Input:
        [
            "Violent brawl erupts between Swans and Lions fans at Brisbane's Gabba stadium.",
            "Reporter covering post-game brawl between Swans and Lions fans at Brisbane's Gabba stadium.",
            "Sunny day at the beach with kids playing volleyball."
        ]

        Step-by-step reasoning:
            - Sentence 0 describes a brawl between Swans and Lions fans at a stadium.
            - Sentence 1 describes the same brawl, just from a reporter’s perspective.
            - Sentence 2 is unrelated, about a beach volleyball event.
            - Therefore, sentences 0 and 1 belong to one group, and sentence 2 belongs to another group.

        Output:
        {
            "groups": [
                {
                    "title": "Swans vs Lions post-game brawl",
                    "indexes": [0, 1]
                },
                {
                    "title": "Beach volleyball fun",
                    "indexes": [2]
                }
            ]
        }

    ---

    ### Few-Shot Example 2
        Input:
        [
            "Fire breaks out in downtown apartment building, firefighters on site.",
            "Residents evacuated from downtown apartment building due to fire.",
            "Local football team wins championship, fans celebrate in city square."
        ]

        Step-by-step reasoning:
            - Sentence 0 and 1 describe the same fire event in a downtown apartment.
            - Sentence 2 is unrelated, about a football celebration.
            - Therefore, sentences 0 and 1 belong to one group, and sentence 2 to another.

        Output:
        {
            "groups": [
                {
                    "title": "Downtown apartment fire",
                    "indexes": [0, 1]
                },
                {
                    "title": "Football championship celebration",
                    "indexes": [2, 2]
                }
            ]
        }
    ---
    ## Output format (JSON):
        {
            "groups": [
                {
                    "title": "Downtown apartment fire",
                    "indexes": [0, 1]
                },
                {
                    "title": "Football championship celebration",
                    "indexes": [2, 2]
                },
                {
                    "title": "Goal highlights",
                    "indexes": [3, 8]
                }
            ]
        }
    **Note**: Do not add anything extra to the output. 
"""

class GroupAndTitleService:
    def __init__(self):
        self.llm = Claude()

    async def group_and_generate_title(self, sentences: List[str]):
        response = await self.llm.invoke(prompt=GROUPING_AND_TITLE_PROMPT, response_type="json", queries=sentences, max_tokens=500)
        return response["groups"]

class AssortClipsService:
    def __init__(self):
        self.is_db_service_initialized = False
        self.db_service = AuroraService(pool_size=10)
        self.title_service = GroupAndTitleService()

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
    
    async def assort_clips(self, stream_id, clip_scorer_event: asyncio.Event):
        should_break = False
        i = 0
        await self.intialize_db_service()
        while True:
            if should_break:
                logger.info("[AssortClipsService] exiting assort clips service.")
                break
            
            scored_clips = await self.db_service.get_scored_clips_by_stream(stream_id, i, i+300)

            if len(scored_clips) < 100:
                if clip_scorer_event.is_set():
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
                groups = await self.title_service.group_and_generate_title([clip["caption"] for clip in scored_clips[start_idx:end_idx+1]])
                logger.info(f"[AssortClipsService] grouping from llm {groups}")
                for group in groups:
                    l, r = (group["indexes"][0], group["indexes"][1]) if len(group["indexes"]) == 2 else (group["indexes"][0], group["indexes"][0])
                    highlight = {
                        "start_time": scored_clips[l]["start_time"],
                        "end_time": scored_clips[r]["end_time"],
                        "caption": ' '.join([clip["caption"] for clip in scored_clips[l:r+1]]),
                        "thumbnail": get_video_frame_filename(i),
                        "title": group["title"]
                    }
                    highlights.append(highlight)

            logger.info(f"[AssortClipsService] generated highlights {highlights}")

            await self.db_service.update_dict(
                STREAM_METADATA_TABLE, 
                {"highlights": json.dumps(highlights)},
                where_clause="stream_id=%s",
                where_params=(stream_id,)
            )
            
