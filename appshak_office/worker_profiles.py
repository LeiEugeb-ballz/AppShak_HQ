from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Dict


@dataclass(frozen=True)
class WorkerProfile:
    """Fixed stochastic worker behavior model (environment physics, non-evolving)."""

    name: str
    success_rate: float
    delay_probability: float
    rework_probability: float
    consistency_variance: float

    def sample_outcome(
        self,
        *,
        base_effort_hours: float,
        task_complexity: int,
        task_risk_score: float,
        rng: Random,
    ) -> Dict[str, float | bool]:
        """Sample a bounded task outcome for one worker-task interaction."""
        complexity_factor = 1.0 + (max(1, task_complexity) - 1) * 0.08
        variance = rng.uniform(-self.consistency_variance, self.consistency_variance)
        risk_penalty = min(0.4, task_risk_score * 0.25)
        success_probability = max(0.05, min(0.98, self.success_rate - risk_penalty))

        was_delayed = rng.random() < self.delay_probability
        delay_hours = rng.uniform(0.25, 2.5) if was_delayed else 0.0

        needs_rework = rng.random() < self.rework_probability
        rework_hours = base_effort_hours * rng.uniform(0.15, 0.45) if needs_rework else 0.0

        completed = rng.random() < success_probability
        if not completed:
            # Failed tasks still consume effort and usually trigger rework follow-up cost.
            rework_hours += base_effort_hours * rng.uniform(0.2, 0.5)

        completion_hours = max(
            0.1,
            base_effort_hours * complexity_factor * (1.0 + variance) + delay_hours + rework_hours,
        )

        return {
            "completed": completed,
            "delay_applied": was_delayed,
            "delay_hours": delay_hours,
            "needs_rework": needs_rework,
            "rework_hours": rework_hours,
            "completion_hours": completion_hours,
            "success_probability": success_probability,
        }

