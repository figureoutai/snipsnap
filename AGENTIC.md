# Agentic Highlighting (MVP)

This document describes the current agentic refinement at the end of the pipeline (assort stage), the inputs the LLM sees, how its plan is executed/verified, a full end‑to‑end flow diagram, and known issues.

## TL;DR

- Ingestion unchanged: demux → frames → 5s audio → ASR → 5s scored clips.
- Assort (final highlights): we Observe (topic+scene boundaries, transcript, frames) → Plan (single LLM call) → Act (snap/micro‑adjust) → Verify (guardrails). The final highlight includes a short `snap_reason` explaining what changed and why.

## Modules Involved

- `detectors/scene_detector.py` — scene cuts from frames only.
- `nlp/text_tiling.py` — topic boundaries from transcript words.
- `utils/boundary_snapper.py` — safe snapping with priority and duration/midpoint guardrails.
- `evaluators/edge_refiner.py` — one LLM call returns an action: `keep | use_topic | use_scene | micro_adjust`.

## What the LLM Receives

- JSON context:
  - `snapped_start`, `snapped_end`, `duration`, `min_len`, `max_len`, `fps`.
  - Nearest topic/scene candidates at each edge with deltas (seconds).
  - Allowed delta ranges for micro‑adjust (start ±1.0s, end ±1.5s).
- Transcript text inside the window (trimmed; pronunciations only).
- Edge/mid frames: pre‑start, start, mids, last‑in‑window, post‑end (base64 JPEGs).
- Strict JSON output schema only: `{action, start_delta, end_delta, reason, confidence}`.

## Plan → Act → Verify (assort stage)

- Plan (LLM): choose `keep | use_topic | use_scene | micro_adjust`.
- Act: execute deterministically with existing tools.
  - `use_topic` → `snap_window(..., priority='topic_first')`.
  - `use_scene` → `snap_window(..., priority='scene_first')`.
  - `micro_adjust` → apply small deltas to the snapped baseline.
- Verify: enforce midpoint safety and clamp each edge to `±MAX_EDGE_SHIFT_SECONDS` relative to the original grouped span; optionally apply `HIGHLIGHT_MIN_LEN/MAX_LEN` as sanity. If invalid after clamping, fall back to baseline.
- Reason: compose `snap_reason` from plan + applied deltas and/or boundary sources.

## Config Knobs (config.py)

- Master toggle:
  - `AGENTIC_REFINEMENT_ENABLED` — when False, the assort stage returns grouped highlights without boundary snapping or LLM refinement.

- Edge budget & duration sanity:
  - `MAX_EDGE_SHIFT_SECONDS` — per-edge clamp after refinement.
  - `HIGHLIGHT_MIN_LEN`, `HIGHLIGHT_MAX_LEN` — optional sanity bounds.
- TextTiling parameters: `TEXT_TILING_BLOCK`, `TEXT_TILING_STEP`, `TEXT_TILING_SMOOTH`, `TEXT_TILING_CUTOFF_STD`.
```
