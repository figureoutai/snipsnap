from __future__ import annotations

from typing import Dict

from strands import Agent, tool


@tool
def choose_keep(reason: str, confidence: float) -> Dict:
    """Keep the current snapped window unchanged."""
    return {"action": "keep", "reason": reason, "confidence": confidence}


@tool
def choose_topic(reason: str, confidence: float) -> Dict:
    """Use transcript/topic boundaries for both edges."""
    return {"action": "use_topic", "reason": reason, "confidence": confidence}


@tool
def choose_scene(reason: str, confidence: float) -> Dict:
    """Use scene cut boundaries for both edges."""
    return {"action": "use_scene", "reason": reason, "confidence": confidence}


@tool
def choose_micro_adjust(start_delta: float, end_delta: float, reason: str, confidence: float) -> Dict:
    """Apply small deltas to the snapped baseline."""
    return {
        "action": "micro_adjust",
        "start_delta": float(start_delta),
        "end_delta": float(end_delta),
        "reason": reason,
        "confidence": confidence,
    }




@tool
def emit_plan(action: str, start_delta: float, end_delta: float, reason: str, confidence: float) -> Dict:
    """Emit the final plan object for logging and parsing."""
    return {
        "action": action,
        "start_delta": float(start_delta),
        "end_delta": float(end_delta),
        "reason": reason,
        "confidence": float(confidence),
    }


class StrandsEdgeRefinerAgent:
    def __init__(self) -> None:
        # Use default provider configured by Strands (per project env)
        self.agent = Agent(tools=[
            choose_keep,
            choose_topic,
            choose_scene,
            choose_micro_adjust,
            emit_plan,
        ])

    async def invoke_async(self, prompt: str) -> str:
        return await self.agent.invoke_async(prompt)
