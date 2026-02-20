from __future__ import annotations

from statistics import mean, pstdev
from typing import Dict, List


class MetricsEngine:
    """Computes reliability and variance metrics for sprint outcomes."""

    @staticmethod
    def compute_reliability(task_results: List[Dict[str, object]]) -> float:
        if not task_results:
            return 0.0

        total = len(task_results)
        completed = sum(1 for t in task_results if bool(t.get("completed")))
        on_time = sum(1 for t in task_results if bool(t.get("completed")) and bool(t.get("completed_on_time")))
        rework = sum(1 for t in task_results if bool(t.get("needs_rework")))

        urgent_tasks = [t for t in task_results if bool(t.get("is_urgent"))]
        urgent_success = 1.0
        if urgent_tasks:
            urgent_success = sum(1 for t in urgent_tasks if bool(t.get("completed"))) / len(urgent_tasks)

        completion_ratio = completed / total
        on_time_ratio = on_time / total
        rework_inverse = 1.0 - (rework / total)

        score = (
            completion_ratio * 40.0
            + on_time_ratio * 30.0
            + rework_inverse * 20.0
            + urgent_success * 10.0
        )
        return max(0.0, min(100.0, score))

    @staticmethod
    def compute_variance(task_results: List[Dict[str, object]]) -> float:
        if len(task_results) < 2:
            return 0.0

        completion_times = [float(t.get("completion_hours", 0.0)) for t in task_results]
        completion_std = pstdev(completion_times)

        lateness = [max(0.0, float(t.get("completion_hours", 0.0)) - float(t.get("deadline_hours", 0.0))) for t in task_results]
        lateness_std = pstdev(lateness)

        escalation_flags = [1.0 if bool(t.get("escalated")) else 0.0 for t in task_results]
        escalation_std = pstdev(escalation_flags)

        baseline = max(1.0, mean(completion_times))
        normalized_completion = min(1.0, completion_std / baseline)
        normalized_lateness = min(1.0, lateness_std / max(1.0, mean(lateness) + 0.1))
        normalized_escalation = min(1.0, escalation_std / 0.5)

        score = (
            normalized_completion * 45.0
            + normalized_lateness * 35.0
            + normalized_escalation * 20.0
        )
        return max(0.0, min(100.0, score))

