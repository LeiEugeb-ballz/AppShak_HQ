from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Mapping

from .stability import StabilityRecoveryWrapper


class SelfOptimizationHook:
    def __init__(self, stability_wrapper: StabilityRecoveryWrapper) -> None:
        self._stability = stability_wrapper

    def record(self, runtime_context: Mapping[str, Any]) -> Dict[str, Any]:
        memory = self._stability.load_memory()
        cycle_summaries = memory.get("cycle_summaries", [])
        weekly = memory.get("weekly_summaries", {})
        if not isinstance(cycle_summaries, list):
            cycle_summaries = []
        if not isinstance(weekly, Mapping):
            weekly = {}

        cycle_id = str(_read(runtime_context, "autonomy", "cycle_id") or "")
        timestamp = str(_read(runtime_context, "autonomy", "timestamp") or "")
        approved = bool(_read(runtime_context, "boardroom", "decision", "approved"))
        action_status = str(_read(runtime_context, "external_action", "status") or "")
        anomaly_count = int(_read(runtime_context, "inspection_record", "coverage", "anomaly_count") or 0)
        consistency_score = float(_read(runtime_context, "integrity_record", "consistency_score") or 0.0)
        week_key = _iso_to_week(timestamp)

        cycle_summary = {
            "cycle_id": cycle_id,
            "timestamp": timestamp,
            "approved": approved,
            "action_status": action_status,
            "anomaly_count": anomaly_count,
            "consistency_score": consistency_score,
        }
        cycle_summaries.append(cycle_summary)
        cycle_summaries = cycle_summaries[-2000:]

        weekly_summary = dict(weekly.get(week_key, {})) if isinstance(weekly, Mapping) else {}
        weekly_summary["cycles"] = int(weekly_summary.get("cycles", 0)) + 1
        weekly_summary["approved"] = int(weekly_summary.get("approved", 0)) + (1 if approved else 0)
        weekly_summary["denied"] = int(weekly_summary.get("denied", 0)) + (0 if approved else 1)
        weekly_summary["executed"] = int(weekly_summary.get("executed", 0)) + (1 if action_status == "executed" else 0)
        weekly_summary["avg_consistency_score"] = _update_running_average(
            current_average=float(weekly_summary.get("avg_consistency_score", 0.0)),
            previous_count=max(0, int(weekly_summary["cycles"]) - 1),
            incoming_value=consistency_score,
        )

        updated_weekly = dict(weekly)
        updated_weekly[week_key] = weekly_summary
        memory_payload = {
            "cycle_summaries": cycle_summaries,
            "weekly_summaries": updated_weekly,
        }
        self._stability.save_memory(memory_payload)
        return {
            "current_cycle_summary": cycle_summary,
            "weekly_summary": weekly_summary,
            "week_key": week_key,
        }


def _iso_to_week(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return "unknown_week"
    iso = parsed.isocalendar()
    return f"{iso.year:04d}-W{iso.week:02d}"


def _update_running_average(*, current_average: float, previous_count: int, incoming_value: float) -> float:
    if previous_count <= 0:
        return float(incoming_value)
    total = (float(current_average) * float(previous_count)) + float(incoming_value)
    return total / float(previous_count + 1)


def _read(payload: Mapping[str, Any], *keys: str) -> Any:
    value: Any = payload
    for key in keys:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value
