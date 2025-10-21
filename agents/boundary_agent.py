from __future__ import annotations

import json
from typing import Dict, List

from strands import Agent, tool

from nlp.text_tiling import text_tiling_boundaries
from detectors.scene_detector import detect_scene_boundaries
from config import VIDEO_FRAME_SAMPLE_RATE


@tool
def text_tiling_topics(
    words: List[Dict],
    block_size: int = 20,
    step: int = 10,
    smoothing_width: int = 2,
    cutoff_std: float = 0.5,
) -> List[float]:
    """Compute topic boundaries using a lightweight TextTiling over ASR words."""
    return text_tiling_boundaries(
        words=words,
        block_size=block_size,
        step=step,
        smoothing_width=smoothing_width,
        cutoff_std=cutoff_std,
    )


@tool
def scene_detection(
    base_path: str,
    fps: float = float(VIDEO_FRAME_SAMPLE_RATE),
    threshold: float = 0.5,
    min_scene_len_sec: float = 1.0,
) -> List[float]:
    """Detect scene/shot boundaries using pre-sampled frames at base_path/frames."""
    frames_dir = f"{base_path}/frames"
    return detect_scene_boundaries(
        frames_dir=frames_dir,
        fps=fps,
        threshold=threshold,
        min_scene_len_sec=min_scene_len_sec,
    )


class BoundaryAgent:
    """Strands Agent that exposes only text_tiling and scene_detection as tools.

    It returns strict JSON with {"topic_boundaries": [...], "scene_boundaries": [...]}.
    All snapping/clamping/execution remains deterministic downstream.
    """

    def __init__(self) -> None:
        self.agent = Agent(tools=[text_tiling_topics, scene_detection])

    async def get_boundaries(self, *, base_path: str, words: List[Dict], fps: float) -> Dict[str, List[float]]:
        instruction = (
            "You are a boundary discovery assistant.\n"
            "Call text_tiling_topics(words) to compute topic boundaries, and call scene_detection(base_path, fps) to compute scene cuts.\n"
            "Return only strict JSON: {\"topic_boundaries\": [...], \"scene_boundaries\": [...]}"
        )
        ctx = {
            "base_path": base_path,
            "fps": fps,
            "words": words,
        }
        prompt = f"{instruction}\n\nContext JSON:\n{json.dumps(ctx) }"
        output = await self.agent.invoke_async(prompt)
        try:
            parsed = json.loads(output) if isinstance(output, str) else output
        except Exception:
            parsed = {}
        topics = parsed.get("topic_boundaries", []) or []
        scenes = parsed.get("scene_boundaries", []) or []
        return {"topic_boundaries": topics, "scene_boundaries": scenes}
