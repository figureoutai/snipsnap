from __future__ import annotations

import math
from typing import List, Optional

from utils.logger import app_logger as logger


def _frames_from_seconds(seconds: float, fps: float) -> int:
    return max(1, int(round(seconds * fps)))


def detect_scene_boundaries(
    video_path: str,
    threshold: float = 27.0,
    min_scene_len_sec: float = 1.0,
    downscale_factor: int = 2,
) -> List[float]:
    """
    Detect shot/scene boundaries using PySceneDetect's ContentDetector.

    Returns a sorted list of boundary timestamps (in seconds). These are the
    scene cut points (i.e., the start time of each scene after the first).

    Notes:
    - Requires the `scenedetect` package at runtime.
    - Works with local file paths. If your input is a stream, run detection on
      a downloaded file or an exported copy.
    """
    try:
        from scenedetect import SceneManager, ContentDetector, VideoManager
    except Exception as e:  # pragma: no cover - optional dependency
        logger.error("PySceneDetect not available. Install `scenedetect`. Error: %s", e)
        raise

    video_manager = VideoManager([video_path])
    scene_manager = SceneManager()

    # Start video manager to query fps for min_scene_len in frames.
    video_manager.set_downscale_factor(downscale_factor)
    try:
        video_manager.start()
    except Exception as e:
        logger.error("Failed to open video for scene detection: %s", e)
        raise

    fps = float(video_manager.get_framerate()) if video_manager.get_framerate() else 30.0
    min_scene_len_frames = _frames_from_seconds(min_scene_len_sec, fps)

    scene_manager.add_detector(ContentDetector(threshold=threshold, min_scene_len=min_scene_len_frames))
    scene_manager.detect_scenes(video_manager)

    scene_list = scene_manager.get_scene_list()

    # scene_list is a list of (start_timecode, end_timecode)
    # Boundaries are the start of each scene after the first (skip t=0).
    boundaries: List[float] = []
    for i, (start_tc, _end_tc) in enumerate(scene_list):
        if i == 0:
            continue
        try:
            boundaries.append(start_tc.get_seconds())
        except Exception:
            # Older versions expose .get_timecode() returning a string; best effort parse.
            try:
                h, m, s = str(start_tc).split(":")
                boundaries.append(int(h) * 3600 + int(m) * 60 + float(s))
            except Exception:
                # Ignore unparsable entries but log them.
                logger.warning("Unable to parse scene boundary timecode: %s", start_tc)

    # Ensure strictly increasing order & uniqueness within 0.1s tolerance.
    boundaries = sorted(boundaries)
    deduped: List[float] = []
    last: Optional[float] = None
    for b in boundaries:
        if last is None or abs(b - last) > 0.1:
            deduped.append(round(b, 3))
            last = b
    return deduped

