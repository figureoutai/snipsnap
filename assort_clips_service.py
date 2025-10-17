import json
import asyncio

from typing import List
from llm.claude import Claude
from config import (
    STREAM_METADATA_TABLE,
    HIGHLIGHT_CHUNK,
    CANDIDATE_SLICE,
    VIDEO_FRAME_SAMPLE_RATE,
    SNAP_MAX_SHIFT_SCENE_START,
    SNAP_MAX_SHIFT_SCENE_END,
    SNAP_MAX_SHIFT_TOPIC,
    HIGHLIGHT_MIN_LEN,
    HIGHLIGHT_MAX_LEN,
    HIGHLIGHT_MAX_LEN,
    BASE_DIR,
    LLM_SNAP_ARBITRATE,
    LLM_SNAP_MIN_DELTA_SEC,
)
from utils.logger import app_logger as logger
from utils.helpers import get_video_frame_filename
from repositories.aurora_service import AuroraService
from detectors.scene_detector import detect_scene_boundaries
from nlp.text_tiling import text_tiling_boundaries
from utils.boundary_snapper import snap_window
import os
from evaluators.snap_evaluator import SnapEvaluator
from evaluators.edge_refiner import EdgeRefiner

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
        # Boundary caches per stream_id
        self._scene_boundaries = {}
        self._topic_boundaries = {}
        self._topic_words_count = {}
        self.snap_evaluator: SnapEvaluator | None = None
        self.edge_refiner: EdgeRefiner | None = None

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

    async def _flatten_transcript_words(self, stream_id: str):
        rows = await self.db_service.get_audios_by_stream(stream_id=stream_id)
        words = []
        for row in rows:
            t = row.get("transcript")
            if not t:
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

    async def _ensure_boundaries(self, stream_id: str, clip_scorer_event: asyncio.Event | None = None):
        # Scene boundaries from frames if not cached
        if stream_id not in self._scene_boundaries:
            frames_dir = os.path.join(BASE_DIR, stream_id, "frames")
            if os.path.isdir(frames_dir):
                try:
                    cuts = detect_scene_boundaries(frames_dir=frames_dir, fps=VIDEO_FRAME_SAMPLE_RATE)
                except Exception as e:
                    logger.warning(f"[AssortClipsService] Scene detection failed: {e}")
                    cuts = []
            else:
                cuts = []
            self._scene_boundaries[stream_id] = cuts

        # Topic boundaries via TextTiling, with lightweight refresh when new transcript arrives
        refresh_threshold = 100  # recompute when we have 100 new words
        need_recompute = stream_id not in self._topic_boundaries
        try:
            words = await self._flatten_transcript_words(stream_id)
            current_count = len(words)
        except Exception as e:
            logger.warning(f"[AssortClipsService] Failed to read words for TextTiling: {e}")
            words = []
            current_count = 0

        last_count = self._topic_words_count.get(stream_id, 0)
        if not need_recompute:
            if clip_scorer_event is not None and clip_scorer_event.is_set():
                need_recompute = True
            elif current_count - last_count >= refresh_threshold:
                need_recompute = True

        if need_recompute:
            try:
                topics = text_tiling_boundaries(words)
            except Exception as e:
                logger.warning(f"[AssortClipsService] TextTiling failed: {e}")
                topics = []
            self._topic_boundaries[stream_id] = topics
            self._topic_words_count[stream_id] = current_count

    def _snap_highlight(self, stream_id: str, start: float, end: float):
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
            priority="topic_first",
        )
        return s, e, tags

    
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
                    # Agentic refinement: compute boundaries once, then snap this highlight
                    await self._ensure_boundaries(stream_id, clip_scorer_event)
                    orig_start = scored_clips[l]["start_time"]
                    orig_end = scored_clips[r]["end_time"]
                    snapped_start, snapped_end, snap_tags = self._snap_highlight(stream_id, orig_start, orig_end)

                    # LLM agentic refinement (simple plan -> act -> verify)
                    chosen_start, chosen_end = snapped_start, snapped_end
                    snap_reason = None
                    if LLM_SNAP_ARBITRATE:
                        if self.edge_refiner is None:
                            self.edge_refiner = EdgeRefiner()
                        try:
                            plan = await self.edge_refiner.refine(
                                stream_id,
                                base_path=f"{BASE_DIR}/{stream_id}",
                                snapped_start=snapped_start,
                                snapped_end=snapped_end,
                                topic_boundaries=self._topic_boundaries.get(stream_id, []),
                                scene_boundaries=self._scene_boundaries.get(stream_id, []),
                                min_len=HIGHLIGHT_MIN_LEN,
                                max_len=HIGHLIGHT_MAX_LEN,
                            )
                            action = plan.get("action", "keep")
                            sd = float(plan.get("start_delta", 0.0))
                            ed = float(plan.get("end_delta", 0.0))
                            reason_txt = str(plan.get("reason", ""))

                            # Execute the plan deterministically
                            if action == "use_topic":
                                chosen_start, chosen_end, _ = self._snap_highlight(stream_id, orig_start, orig_end)
                            elif action == "use_scene":
                                # Force scene-first by swapping priority for this call
                                scenes = self._scene_boundaries.get(stream_id, [])
                                topics = self._topic_boundaries.get(stream_id, [])
                                from utils.boundary_snapper import snap_window
                                chosen_start, chosen_end, _ = snap_window(
                                    orig_start,
                                    orig_end,
                                    scene_boundaries=scenes,
                                    topic_boundaries=topics,
                                    max_shift_scene_start=SNAP_MAX_SHIFT_SCENE_START,
                                    max_shift_scene_end=SNAP_MAX_SHIFT_SCENE_END,
                                    max_shift_topic=SNAP_MAX_SHIFT_TOPIC,
                                    min_len=HIGHLIGHT_MIN_LEN,
                                    max_len=HIGHLIGHT_MAX_LEN,
                                    priority="scene_first",
                                )
                            elif action == "micro_adjust":
                                # Apply small deltas to the snapped baseline with guardrails
                                mid = (snapped_start + snapped_end) / 2.0
                                new_start = snapped_start + sd
                                new_end = snapped_end + ed
                                # midpoint safety
                                if new_start > mid:
                                    new_start = snapped_start
                                if new_end < mid:
                                    new_end = snapped_end
                                # duration guardrails
                                if (new_end - new_start) < HIGHLIGHT_MIN_LEN or (new_end - new_start) > HIGHLIGHT_MAX_LEN:
                                    new_start, new_end = snapped_start, snapped_end
                                chosen_start, chosen_end = new_start, new_end
                            else:
                                # keep
                                chosen_start, chosen_end = snapped_start, snapped_end

                            snap_reason = f"LLM plan={action}; applied deltas start {chosen_start-snapped_start:+.2f}s, end {chosen_end-snapped_end:+.2f}s; {reason_txt}"
                        except Exception as e:
                            logger.warning(f"[AssortClipsService] LLM EdgeRefiner failed: {e}")
                    if snap_reason is None and (snapped_start != orig_start or snapped_end != orig_end):
                        snap_reason = (
                            f"Snapped to {snap_tags.get('start_source','original')}/"
                            f"{snap_tags.get('end_source','original')} boundaries; "
                            f"shifts: start {snapped_start-orig_start:+.2f}s, end {snapped_end-orig_end:+.2f}s"
                        )

                    # Update thumbnail to chosen start frame
                    thumb_idx = int(chosen_start * VIDEO_FRAME_SAMPLE_RATE)
                    highlight = {
                        "start_time": chosen_start,
                        "end_time": chosen_end,
                        "caption": ' '.join([clip["caption"] for clip in scored_clips[l:r+1]]),
                        "thumbnail": get_video_frame_filename(thumb_idx),
                        "title": group["title"],
                        "snap_reason": snap_reason,
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
    
