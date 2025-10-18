from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List, Tuple

from utils.logger import app_logger as logger


def _normalize_token(tok: str) -> str:
    tok = tok.lower()
    tok = re.sub(r"[^a-z0-9']+", "", tok)
    return tok


def _cosine_sim(c1: Counter, c2: Counter) -> float:
    if not c1 or not c2:
        return 0.0
    keys = set(c1) | set(c2)
    dot = sum(c1[k] * c2[k] for k in keys)
    n1 = math.sqrt(sum(v * v for v in c1.values()))
    n2 = math.sqrt(sum(v * v for v in c2.values()))
    if n1 == 0.0 or n2 == 0.0:
        return 0.0
    return float(dot / (n1 * n2))


def text_tiling_boundaries(
    words: List[Dict],
    block_size: int = 20,
    step: int = 10,
    smoothing_width: int = 2,
    cutoff_std: float = 0.5,
) -> List[float]:
    """
    Lightweight TextTiling-like topic segmentation over word-timestamp stream.

    Inputs:
      - words: list of dicts with at least {'content', 'start_time', 'type'} where
               type is 'pronunciation' for spoken words.
    Returns:
      - List of boundary timestamps (float seconds), based on similarity valleys
        between adjacent token blocks. Boundaries are placed at the token index
        where a valley occurs, mapped to that token's start_time.

    This implementation avoids heavy deps and is robust to ASR noise. It uses
    cosine similarity between bag-of-words of left/right windows, optional
    moving-average smoothing, then selects minima below (mean - cutoff_std*std).
    """
    # Filter to spoken words with usable timestamps.
    toks: List[str] = []
    times: List[float] = []
    for w in words:
        if w is None:
            continue
        if w.get("type") and w.get("type") != "pronunciation":
            continue
        content = str(w.get("content", "")).strip()
        if not content:
            continue
        t = w.get("start_time")
        if t is None:
            continue
        norm = _normalize_token(content)
        if not norm:
            continue
        toks.append(norm)
        times.append(float(t))

    n = len(toks)
    if n < 2 * block_size:
        return []

    # Precompute cumulative counts for fast window vectors.
    vocab_index: Dict[str, int] = {}
    vectors: List[List[int]] = [[0] * 0]
    # We'll build a rolling Counter for windows using prefix technique.
    # For simplicity and small block sizes, compute Counters on the fly.

    def window_counter(start: int, end: int) -> Counter:
        c = Counter()
        for i in range(start, end):
            c[toks[i]] += 1
        return c

    sims: List[float] = []
    centers: List[int] = []
    i = block_size
    while i + block_size <= n:
        left = window_counter(i - block_size, i)
        right = window_counter(i, i + block_size)
        sims.append(_cosine_sim(left, right))
        centers.append(i)
        i += step

    # Optional smoothing (moving average over similarity curve).
    if smoothing_width > 1 and len(sims) >= 2:
        smoothed: List[float] = []
        w = smoothing_width
        for j in range(len(sims)):
            lo = max(0, j - w)
            hi = min(len(sims), j + w + 1)
            smoothed.append(sum(sims[lo:hi]) / (hi - lo))
        sims = smoothed

    # Compute global mean/std then select local minima below mean - k*std.
    mean = sum(sims) / len(sims)
    var = sum((x - mean) ** 2 for x in sims) / max(1, len(sims) - 1)
    std = math.sqrt(var)
    cutoff = mean - cutoff_std * std

    boundaries: List[float] = []
    for j in range(1, len(sims) - 1):
        if sims[j] <= sims[j - 1] and sims[j] <= sims[j + 1] and sims[j] < cutoff:
            idx = centers[j]
            # Map token index to timestamp (start time of token at idx).
            if 0 <= idx < len(times):
                boundaries.append(round(float(times[idx]), 3))

    # Deduplicate boundaries closer than 0.5s.
    boundaries = sorted(boundaries)
    deduped: List[float] = []
    last = None
    for b in boundaries:
        if last is None or abs(b - last) > 0.5:
            deduped.append(b)
            last = b
    return deduped

