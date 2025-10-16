# Agentic Highlighting (MVP)

This document explains the first agentic step added to the pipeline: boundary‑aware snapping of highlight windows using scene and topic boundaries. It is written for someone new to the repo who wants to understand what changed, why, and how to work with it.

## TL;DR

- We still ingest exactly the same way: demux → frames to disk → audio chunks → ASR → score + caption.
- We now “observe” extra signals:
  - Scene cuts (shot boundaries) from the video.
  - Topic boundaries from the transcript (TextTiling).
- For each candidate 5‑second window, we “plan” and “act” by aligning (snapping) the window’s start/end to these boundaries within small limits. Then we score/caption that snapped window.
- Guardrails ensure the window stays between 4–12 seconds, and we never cross the window midpoint when snapping a single edge. If we can’t snap, we keep the original edges.

This agentic system Observes → Plan → Act and chooses boundary‑aware actions per window based on observations

## What’s New

### Modules

- `detectors/scene_detector.py`
  - `detect_scene_boundaries(video_path, threshold=27.0, min_scene_len_sec=1.0)`
  - Uses PySceneDetect ContentDetector to return shot/scene cut timestamps in seconds.

- `nlp/text_tiling.py`
  - `text_tiling_boundaries(words, block_size=20, step=10, smoothing_width=2, cutoff_std=0.5)`
  - Lightweight TextTiling‑like topic segmentation over ASR words (pronunciations only). Returns topic boundary timestamps in seconds.

- `utils/boundary_snapper.py`
  - `snap_window(start, end, scene_boundaries, topic_boundaries, *, max_shift_scene_start, max_shift_scene_end, max_shift_topic, min_len, max_len)`
  - Aligns each edge to the nearest boundary within allowed shifts using priority: scene > topic > original. Enforces min/max duration, avoids crossing the window midpoint, and returns the snapped start/end and source tags (`scene|topic|original`).

### Config knobs (config.py)

- Snapping shifts:
  - `SNAP_MAX_SHIFT_SCENE_START = 1.0`, `SNAP_MAX_SHIFT_SCENE_END = 2.0`, `SNAP_MAX_SHIFT_TOPIC = 1.0`
- Duration bounds: `HIGHLIGHT_MIN_LEN = 4.0`, `HIGHLIGHT_MAX_LEN = 12.0`
- TextTiling: `TEXT_TILING_BLOCK = 20`, `TEXT_TILING_STEP = 10`, `TEXT_TILING_SMOOTH = 2`, `TEXT_TILING_CUTOFF_STD = 0.5`

### Scoring path changes (clip_scorer_service.py)

We added a small agentic layer inside `ClipScorerService`:

- Caches per stream: `scene_boundaries`, `topic_boundaries`.
- Observe
  - Scene: computed once if a local video path is available (`VIDEO_PATH` env var). If not, scenes are skipped.
  - Topic: computed once we have enough ASR words (≥ 2 × `TEXT_TILING_BLOCK`) by flattening `audio_metadata.transcript` items (pronunciations only) to a global word list and running TextTiling.
- Plan
  - For each candidate grid window `[start, end]` (current 5s, step‑back 2s), choose snapped edges using `snap_window` with priority scene > topic and constraints from config.
- Act
  - Rebuild `CandidateClip` with snapped `[s, e]` and run saliency + caption on the snapped interval. We insert the highlight with `[s, e]` as the official bounds.
- Reflect
  - If snapping would violate constraints, we back off (expand/trim/fallback) inside `snap_window`. We log which source each edge used.

## Concrete Example

- Initial window: `[60.0, 65.0]`
- Observed boundaries: scene cuts at `59.7`, `75.2`; topic boundary at `65.2`.
- Plan
  - Start: nearest scene within 1.0s → `59.7` (scene).
  - End: no scene within 2.0s; nearest topic within 1.0s → `65.2` (topic).
  - Duration `65.2 − 59.7 = 5.5s` within `[4, 12]`.
- Act
  - Use `CandidateClip(base_path, 59.7, 65.2)`; load frames/audio for that span; compute saliency + caption; store.
- Reflect
  - Log sources: `start_source=scene`, `end_source=topic`.

### If the snapped duration is out of bounds

- Too short (< 4s): expand conservatively (prefer expanding edges that remained original) to reach 4s; if both edges snapped, expand symmetrically. If expansion would cross the midpoint or exceed 12s, relax the lower‑priority snap first (topic before scene). In the worst case, keep the original edges.
- Too long (> 12s): trim to 12s, preferring to trim from original edges first; otherwise trim symmetrically around the midpoint.

## Operational Notes

- Scene detection requires a local file path. Set `VIDEO_PATH` env var if available; otherwise scene snapping is skipped and topic snapping still applies.
- Topic boundaries rely on ASR transcripts stored in `audio_metadata.transcript`. Only items with `type == 'pronunciation'` and valid `start_time` are used. We map chunk‑relative times to global times via each row’s `start_timestamp`.
- We do not alter how audio chunks or frames are stored. Snapping only changes the time bounds used when extracting frames/audio for scoring/captioning.
- No DB schema changes in this pass. Boundary source tags are logged; adding them to `score_metadata` can be a later enhancement.

## What Makes This Agentic

- Perception: The system derives scene and topic boundaries (observations) from the environment.
- Planning: For each window, it decides *which boundaries to use* for snapping under explicit constraints, rather than always using fixed edges.
- Action: It changes the time span it scores/captions (the actual data it processes) based on the plan.
- Reflection: It enforces bounds and falls back when evidence conflicts or is insufficient, and records decisions in logs.

## Extending Next

- Persist boundaries (`stream_boundaries` table) for audit/iteration.
- Add speech (VAD) and scene‑change confidence to boundary selection.
- Re‑transcribe low‑confidence spans that intersect final windows.
- Adaptive peak detection (saliency prominence) to hit soft targets for the number of highlights.

