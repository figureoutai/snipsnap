import json
import asyncio

from typing import List
from llm.claude import Claude
from config import STREAM_METADATA_TABLE, HIGHLIGHT_CHUNK, CANDIDATE_SLICE
from utils.logger import app_logger as logger
from utils.helpers import get_video_frame_filename
from repositories.aurora_service import AuroraService

GROUPING_AND_TITLE_PROMPT = """
    You are an AI assistant that groups sentences describing the same event. 
    You will be given a sequence of sentences in order describing the scenes from a video. Follow these steps for each input:
        1. Read the full list of sentences.
        2. Compare adjacent sentences and decide whether each pair belongs to the same event.
        3. Merge contiguous sentences into a group when they describe the same event.
        4. Each group must be contiguous (consecutive indexes).
        5. Give each group a short descriptive title (3-6 words is ideal).
        6. Return only a valid JSON object with a top-level key "groups" whose value is a list of groups. Each group is an object with "title" and "indexes" (0-based list of integers).
        7. Do not output any reasoning, explanations, or extra text — only the JSON.
        8. If a sentence is unique (not contiguous with same-event neighbors), it becomes a single-item group.
        9. Think step-by-step internally but do not reveal your chain-of-thought.

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
            - Sentence 1 describes the same brawl, just from a reporter's perspective.
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
                    "indexes": [2]
                }
            ]
        }
    ---
    ## Output format (JSON):
        {
            "groups": [
                {
                    "title": "Downtown apartment fire",
                    "indexes": [0, 1, 3]
                },
                {
                    "title": "Football championship celebration",
                    "indexes": [2]
                },
                {
                    "title": "Goal highlights",
                    "indexes": [4, 5, 6, 7, 8]
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
    
    async def has_more_clips(self, stream_id, end_time):
        return await self.db_service.has_more_entries_after(stream_id, end_time)

    
    async def assort_clips(self, stream_id, clip_scorer_event: asyncio.Event):
        should_break = False
        i = 0
        await self.intialize_db_service()
        while True:
            if should_break:
                logger.info("[AssortClipsService] exiting assort clips service.")
                break
            
            scored_clips = await self.db_service.get_scored_clips_by_stream(stream_id, i, i+HIGHLIGHT_CHUNK)

            if len(scored_clips) < HIGHLIGHT_CHUNK//CANDIDATE_SLICE:
                if clip_scorer_event.is_set():
                    if len(scored_clips) == 0:
                        should_break = True
                        continue
                    elif await self.db_service.has_more_entries_after(stream_id, scored_clips[-1]["end_time"]):
                        logger.info("[AssortClipsService] clip scorer has exited but have more clips to process, fetching them")
                        continue
                    logger.info("[AssortClipsService] no more clips to be fetched, can safely break in next iteration")
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
                if (highlight_score >= 0.6) or (saliency_score >= 0.7 and highlight_score >= 0.5):
                    potential_highlights.append(1)
                else:
                    potential_highlights.append(0)

            highlight_groups = self.consolidate_groups(self.get_one_groups(potential_highlights))

            highlights = []

            for (start_idx, end_idx) in highlight_groups:
                groups = await self.title_service.group_and_generate_title([clip["caption"] for clip in scored_clips[start_idx:end_idx+1]])
                for group in groups:
                    l, r = start_idx + group["indexes"][0], start_idx + group["indexes"][-1]
                    highlight = {
                        "start_time": scored_clips[l]["start_time"],
                        "end_time": scored_clips[r]["end_time"],
                        "caption": ' '.join([clip["caption"] for clip in scored_clips[l:r+1]]),
                        "thumbnail": get_video_frame_filename(l),
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
            i += HIGHLIGHT_CHUNK
    