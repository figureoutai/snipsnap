from __future__ import annotations

import os
import re
import math
from typing import List, Optional, Tuple

import cv2

from utils.logger import app_logger as logger


_FNAME_RE = re.compile(r"frame_(\d+)\.jpg$")


def _sorted_frame_files(frames_dir: str) -> List[Tuple[int, str]]:
    files = []
    try:
        for name in os.listdir(frames_dir):
            m = _FNAME_RE.match(name)
            if not m:
                continue
            idx = int(m.group(1))
            files.append((idx, os.path.join(frames_dir, name)))
    except FileNotFoundError:
        return []
    files.sort(key=lambda x: x[0])
    return files


def _hist_hs(img_bgr, bins_h=32, bins_s=32, downscale: Optional[Tuple[int, int]] = (160, 90)):
    if downscale is not None:
        img_bgr = cv2.resize(img_bgr, downscale, interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [bins_h, bins_s], [0, 180, 0, 256])
    hist = cv2.normalize(hist, None).flatten()
    return hist


def detect_scene_boundaries(
    frames_dir: str,
    fps: float,
    threshold: float = 0.5,
    min_scene_len_sec: float = 1.0,
    downscale: Optional[Tuple[int, int]] = (160, 90),
) -> List[float]:
    """
    Detect scene/shot boundaries using saved frames instead of opening the video.

    Args:
        frames_dir: Folder containing sampled frames named like 'frame_000000123.jpg'.
        fps: Sampling rate of frames in frames/sec (e.g., VIDEO_FRAME_SAMPLE_RATE).
        threshold: Bhattacharyya distance threshold to declare a cut (> threshold → cut).
        min_scene_len_sec: Minimum time between cuts to avoid over-segmentation.
        downscale: Optional (width, height) to downscale frames for faster histograms.

    Returns:
        Sorted list of boundary timestamps (seconds), deduplicated.
    """
    pairs = _sorted_frame_files(frames_dir)
    if len(pairs) < 2:
        return []

    min_gap_frames = max(1, int(math.ceil(min_scene_len_sec * fps)))

    prev_idx, prev_path = pairs[0]
    prev_img = cv2.imread(prev_path)
    if prev_img is None:
        logger.warning("[SceneDetector] unable to read first frame: %s", prev_path)
        return []
    prev_hist = _hist_hs(prev_img, downscale=downscale)

    boundaries: List[float] = []
    last_cut_idx = prev_idx

    for idx, path in pairs[1:]:
        img = cv2.imread(path)
        if img is None:
            continue
        hist = _hist_hs(img, downscale=downscale)

        # Bhattacharyya distance: 0 = identical, higher = more different
        dist = cv2.compareHist(prev_hist.astype('float32'), hist.astype('float32'), cv2.HISTCMP_BHATTACHARYYA)

        if dist > threshold and (idx - last_cut_idx) >= min_gap_frames:
            # Boundary time at current frame index
            t = idx / float(fps)
            boundaries.append(round(t, 3))
            last_cut_idx = idx

        prev_hist = hist

    return boundaries

