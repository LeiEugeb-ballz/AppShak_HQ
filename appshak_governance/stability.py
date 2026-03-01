from __future__ import annotations

from statistics import pvariance
from typing import Dict, List

from .constants import STABILITY_ROLLING_WINDOW
from .registry import AgentRegistry


class TrustStabilityMetric:
    def __init__(self, *, window_size: int = STABILITY_ROLLING_WINDOW) -> None:
        self._window_size = max(2, int(window_size))

    @property
    def window_size(self) -> int:
        return self._window_size

    def compute(self, *, registry: AgentRegistry) -> Dict[str, object]:
        snapshot = registry.snapshot()
        history = snapshot.get("history", {})
        per_agent: Dict[str, float] = {}
        all_values: List[float] = []
        for agent_id in registry.agent_ids:
            series = history.get(agent_id, [])
            if isinstance(series, list):
                window = [float(value) for value in series[-self._window_size :]]
            else:
                window = []
            variance = float(pvariance(window)) if len(window) > 1 else 0.0
            per_agent[agent_id] = variance
            all_values.append(variance)

        global_variance = sum(all_values) / float(len(all_values)) if all_values else 0.0
        return {
            "window_size": self._window_size,
            "per_agent_variance": per_agent,
            "global_variance": global_variance,
            "recorded_version": registry.version,
        }
