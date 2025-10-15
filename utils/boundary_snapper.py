from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple


def _nearest(
    t: float,
    candidates: Iterable[float],
    max_shift: float,
    forbid_cross: Optional[float] = None,
    prefer_direction: Optional[str] = None,  # 'past' or 'future'
) -> Optional[float]:
    """
    Find nearest candidate to time t within max_shift seconds.

    - If forbid_cross is provided, reject candidates that would move t across that
      time (e.g., the clip midpoint).
    - If prefer_direction is provided, tie-break by preferring candidates in that
      temporal direction when distances are very similar (~10ms).
    """
    best = None
    best_d = None
    for c in candidates:
        d = abs(c - t)
        if d > max_shift:
            continue
        if forbid_cross is not None:
            if t <= forbid_cross < c:
                # moving start past midpoint
                continue
            if c < forbid_cross <= t:
                # moving end past midpoint
                continue
        if best is None or d < best_d - 1e-2:
            best, best_d = c, d
        elif best is not None and abs(d - best_d) <= 1e-2 and prefer_direction:
            if prefer_direction == "past" and c <= t and best > t:
                best, best_d = c, d
            elif prefer_direction == "future" and c >= t and best < t:
                best, best_d = c, d
    return best


def snap_window(
    start: float,
    end: float,
    scene_boundaries: Iterable[float] = (),
    topic_boundaries: Iterable[float] = (),
    *,
    max_shift_scene_start: float = 1.0,
    max_shift_scene_end: float = 2.0,
    max_shift_topic: float = 1.0,
    min_len: float = 4.0,
    max_len: float = 12.0,
) -> Tuple[float, float, Dict[str, str]]:
    """
    Snap [start, end] to nearest boundaries with priority: scene > topic.

    Returns: (new_start, new_end, sources)
      where sources = { 'start_source': 'scene|topic|original',
                        'end_source':   'scene|topic|original' }

    Invariants:
      - Does not let start cross the midpoint towards the end (and vice versa).
      - Maintains min_len/max_len by expanding/contracting conservatively.
    """
    if end <= start:
        raise ValueError("end must be greater than start")

    mid = (start + end) / 2.0
    s_src = "original"
    e_src = "original"

    # Try snapping start then end, with priority to scene cuts.
    s_candidate = _nearest(start, scene_boundaries, max_shift_scene_start, forbid_cross=mid, prefer_direction="past")
    if s_candidate is None:
        s_candidate = _nearest(start, topic_boundaries, max_shift_topic, forbid_cross=mid, prefer_direction="past")
        if s_candidate is not None:
            s_src = "topic"
    else:
        s_src = "scene"

    if s_candidate is not None:
        start = s_candidate

    # End edge snapping
    e_candidate = _nearest(end, scene_boundaries, max_shift_scene_end, forbid_cross=mid, prefer_direction="future")
    if e_candidate is None:
        e_candidate = _nearest(end, topic_boundaries, max_shift_topic, forbid_cross=mid, prefer_direction="future")
        if e_candidate is not None:
            e_src = "topic"
    else:
        e_src = "scene"

    if e_candidate is not None:
        end = e_candidate

    # Enforce duration constraints.
    dur = end - start
    if dur < min_len:
        # Try expanding end first, then start, up to max_len.
        need = min_len - dur
        if e_src == "original":
            end = min(end + need, start + max_len)
        elif s_src == "original":
            start = max(start - need, end - max_len)
        else:
            # If both were snapped, split expansion.
            half = need / 2.0
            end = min(end + half, start + max_len)
            start = max(start - (need - (end - (start + dur))), end - max_len)
    elif dur > max_len:
        # Prefer trimming equally around midpoint when possible.
        excess = dur - max_len
        trim_s = trim_e = excess / 2.0
        # Avoid undoing recent snaps: favor trimming the "original" side first.
        if s_src != "original" and e_src == "original":
            trim_s = 0.0
            trim_e = excess
        elif e_src != "original" and s_src == "original":
            trim_s = excess
            trim_e = 0.0
        start += trim_s
        end -= trim_e

    return round(start, 3), round(end, 3), {"start_source": s_src, "end_source": e_src}

