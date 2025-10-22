from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
import os
import cv2
import numpy as np
from typing import Any, Dict, List, Tuple


INSTRUCTION = (
    "You are an expert highlight refiner.\n"
    "Decide using tools only: call exactly one of choose_keep | choose_topic | choose_scene | choose_micro_adjust, then call emit_plan.\n"
    "Do not perform snapping/clamping; emit only the final plan."
)


@dataclass
class Scenario:
    name: str
    snapped: Tuple[float, float]
    min_len: float
    max_len: float
    start_delta_range: Tuple[float, float]
    end_delta_range: Tuple[float, float]
    topic_boundaries: List[float]
    scene_boundaries: List[float]
    transcript: str


def build_ctx(s: Scenario) -> Dict[str, Any]:
    start, end = s.snapped
    def nearest(t: float, arr: List[float]) -> Tuple[float | None, float | None]:
        if not arr:
            return None, None
        best = min(arr, key=lambda x: abs(x - t))
        return best, best - t

    ts_start_topic, d_start_topic = nearest(start, s.topic_boundaries)
    ts_start_scene, d_start_scene = nearest(start, s.scene_boundaries)
    ts_end_topic, d_end_topic = nearest(end, s.topic_boundaries)
    ts_end_scene, d_end_scene = nearest(end, s.scene_boundaries)

    return {
        "window": {
            "snapped_start": round(start, 3),
            "snapped_end": round(end, 3),
            "duration": round(end - start, 3),
            "min_len": s.min_len,
            "max_len": s.max_len,
        },
        "boundaries": {
            "start": {
                "topic_candidate_sec": None if ts_start_topic is None else round(ts_start_topic, 3),
                "topic_delta_sec": None if d_start_topic is None else round(d_start_topic, 3),
                "scene_candidate_sec": None if ts_start_scene is None else round(ts_start_scene, 3),
                "scene_delta_sec": None if d_start_scene is None else round(d_start_scene, 3),
            },
            "end": {
                "topic_candidate_sec": None if ts_end_topic is None else round(ts_end_topic, 3),
                "topic_delta_sec": None if d_end_topic is None else round(d_end_topic, 3),
                "scene_candidate_sec": None if ts_end_scene is None else round(ts_end_scene, 3),
                "scene_delta_sec": None if d_end_scene is None else round(d_end_scene, 3),
            },
        },
        "limits": {
            "start_delta_range_sec": list(s.start_delta_range),
            "end_delta_range_sec": list(s.end_delta_range),
        },
    }


def validate_plan(plan: Dict[str, Any], s: Scenario) -> None:
    assert isinstance(plan, dict), "plan must be a dict"
    assert plan.get("action") in {"keep", "use_topic", "use_scene", "micro_adjust"}, "invalid action"
    assert isinstance(plan.get("reason"), str), "reason must be str"
    assert isinstance(plan.get("confidence"), (int, float)), "confidence must be number"
    if plan.get("action") == "micro_adjust":
        sd = float(plan.get("start_delta", 0.0))
        ed = float(plan.get("end_delta", 0.0))
        assert s.start_delta_range[0] <= sd <= s.start_delta_range[1], "start_delta out of range"
        assert s.end_delta_range[0] <= ed <= s.end_delta_range[1], "end_delta out of range"


async def run_scenarios() -> None:
    try:
        from agents.edge_refiner_agent import StrandsEdgeRefinerAgent  # type: ignore
    except Exception as e:
        raise SystemExit(f"StrandsEdgeRefinerAgent import failed; ensure strands-agents is installed. Error: {e}")


    scenarios: List[Scenario] = [
        Scenario(
            name="topic-leaning",
            snapped=(10.0, 20.0),
            min_len=4.0,
            max_len=12.0,
            start_delta_range=(-1.0, 1.0),
            end_delta_range=(-1.5, 1.5),
            topic_boundaries=[9.9, 20.3],
            scene_boundaries=[9.0, 18.6],
            transcript="... play-by-play words here ...",
        ),
        Scenario(
            name="scene-leaning",
            snapped=(30.0, 42.0),
            min_len=4.0,
            max_len=12.0,
            start_delta_range=(-1.0, 1.0),
            end_delta_range=(-1.5, 1.5),
            topic_boundaries=[27.8, 45.5],
            scene_boundaries=[29.2, 42.8],
            transcript="... cut between shots ...",
        ),
        Scenario(
            name="micro-adjustable",
            snapped=(50.0, 58.0),
            min_len=4.0,
            max_len=12.0,
            start_delta_range=(-1.0, 1.0),
            end_delta_range=(-1.5, 1.5),
            topic_boundaries=[49.5, 58.7],
            scene_boundaries=[],
            transcript="... sentence slightly clipped ...",
        ),
        Scenario(
            name="keep-baseline",
            snapped=(70.0, 78.0),
            min_len=4.0,
            max_len=12.0,
            start_delta_range=(-1.0, 1.0),
            end_delta_range=(-1.5, 1.5),
            topic_boundaries=[],
            scene_boundaries=[],
            transcript="... no cues ...",
        ),
    ]

    failures = 0
    def extract_plan(out: Any) -> Dict[str, Any]:
        if isinstance(out, dict):
            return out
        if isinstance(out, str):
            return json.loads(out)
        # Try common attributes that may carry final tool output
        for attr in ("output", "result", "final", "data", "content", "text"):
            if hasattr(out, attr):
                val = getattr(out, attr)
                if isinstance(val, dict):
                    return val
                if isinstance(val, str):
                    try:
                        return json.loads(val)
                    except Exception:
                        pass
        # Try model_dump/json-like helpers
        for attr in ("model_dump", "to_dict"):
            if hasattr(out, attr):
                try:
                    d = getattr(out, attr)()
                    if isinstance(d, dict):
                        return d
                except Exception:
                    pass
        for attr in ("model_dump_json", "to_json", "json"):
            if hasattr(out, attr):
                try:
                    s = getattr(out, attr)()
                    if isinstance(s, str):
                        return json.loads(s)
                except Exception:
                    pass
        # Look into known containers (e.g., tool results)
        for attr in ("tool_results", "tools", "events", "messages"):
            if hasattr(out, attr):
                seq = getattr(out, attr)
                try:
                    for item in (seq or []):
                        try:
                            d = extract_plan(item)  # recurse
                            if isinstance(d, dict) and d.get("action"):
                                return d
                        except Exception:
                            continue
                except Exception:
                    pass
        # Walk __dict__ recursively to find a dict with an 'action'
        visited: set[int] = set()

        def walk(obj: Any) -> Dict[str, Any] | None:
            oid = id(obj)
            if oid in visited:
                return None
            visited.add(oid)
            if isinstance(obj, dict):
                if obj.get("action") in {"keep", "use_topic", "use_scene", "micro_adjust"}:
                    return obj
                for v in obj.values():
                    res = walk(v)
                    if res is not None:
                        return res
                return None
            if isinstance(obj, (list, tuple, set)):
                for v in obj:
                    res = walk(v)
                    if res is not None:
                        return res
                return None
            # object with attributes
            for attr in ("__dict__",):
                if hasattr(obj, attr):
                    d = getattr(obj, attr)
                    res = walk(d)
                    if res is not None:
                        return res
            return None

        found = walk(out)
        if found is not None:
            return found
        # As a last resort, try to find the last JSON object substring
        try:
            s = str(out)
            last_l = s.rfind("{")
            last_r = s.rfind("}")
            if last_l != -1 and last_r != -1 and last_r > last_l:
                return json.loads(s[last_l:last_r+1])
        except Exception:
            pass
        raise ValueError(f"Unrecognized agent output type: {type(out)}")

    for sc in scenarios:
        ctx = build_ctx(sc)
        text_block = (
            f"{INSTRUCTION}\n\n"
            f"orig_start={sc.snapped[0]:.3f}; orig_end={sc.snapped[1]:.3f};\n"
            f"min_len={sc.min_len:.2f}; max_len={sc.max_len:.2f};\n"
            f"start_delta_range={list(sc.start_delta_range)}; end_delta_range={list(sc.end_delta_range)};\n"
            f"topics={sc.topic_boundaries}; scenes={sc.scene_boundaries};\n\n"
            f"Context JSON:\n{json.dumps(ctx)}\n\n"
            f"Transcript (inside window):\n{sc.transcript}"
        )
        # Load a few frames from a test video if available; otherwise generate dummy JPEGs
        images: List[bytes] = []
        video_candidates = [
            os.path.join("data", "test_videos", "apple.mp4"),
            os.path.join("data", "test_videos", "news.mp4"),
            os.path.join("data", "test_videos", "football-trimmed.mp4"),
        ]
        vid_path = next((p for p in video_candidates if os.path.exists(p)), None)
        if vid_path:
            cap = cv2.VideoCapture(vid_path)
            if cap and cap.isOpened():
                fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
                # sample around start/mid/end of the window if within video duration
                sample_ts = [sc.snapped[0], (sc.snapped[0]+sc.snapped[1])/2.0, sc.snapped[1]]
                for t in sample_ts:
                    frame_idx = int(t * fps)
                    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, frame_idx))
                    ok, frame = cap.read()
                    if ok and frame is not None:
                        ok2, buf = cv2.imencode('.jpg', frame)
                        if ok2:
                            images.append(buf.tobytes())
                cap.release()
        if not images:
            # fallback: generate simple colored JPEGs
            for color in [(255,0,0), (0,255,0), (0,0,255)]:
                img = np.zeros((64, 64, 3), dtype=np.uint8)
                img[:] = color
                ok2, buf = cv2.imencode('.jpg', img)
                if ok2:
                    images.append(buf.tobytes())

        content: List[Dict[str, Any]] = [{"text": text_block}]
        for b in images[:6]:
            content.append({"image": {"format": "jpeg", "source": {"bytes": b}}})

        print(f"\n=== Scenario: {sc.name} ===")
        # Fresh agent per scenario to avoid history accumulation across runs
        agent = StrandsEdgeRefinerAgent()
        out = await agent.invoke_async_content(content)
        try:
            plan = extract_plan(out)
            validate_plan(plan, sc)
            print(json.dumps(plan, indent=2))
        except Exception as e:
            failures += 1
            print(f"Failed to parse/validate plan. Error: {e}. Type: {type(out)}. Raw snippet: {str(out)[:200]}")

    if failures:
        raise SystemExit(f"Test completed with {failures} failing scenario(s)")
    print("\nAll scenarios produced valid plans.")


if __name__ == "__main__":
    asyncio.run(run_scenarios())
