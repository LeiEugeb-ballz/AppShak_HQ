from __future__ import annotations

import json
from pathlib import Path
from statistics import mean, stdev
from typing import Any, Dict, List


class DashboardDataAdapter:
    """Read-only adapter that consumes exported Phase 2A JSON results."""

    def __init__(self, results_path: str | Path) -> None:
        self.results_path = Path(results_path)

    def load_baseline(self, rolling_window: int = 10) -> Dict[str, Any]:
        payload = self._read_payload()
        if not payload:
            return {
                "available": False,
                "message": f"Results file not found or invalid: {self.results_path}",
                "config": {},
                "summary": {},
                "reliability_series": [],
                "variance_series": [],
                "rolling_reliability": [],
            }

        per_sprint = payload.get("per_sprint", [])
        if not isinstance(per_sprint, list):
            per_sprint = []

        reliability_series = [self._to_float(row.get("reliability")) for row in per_sprint if isinstance(row, dict)]
        variance_series = [self._to_float(row.get("variance")) for row in per_sprint if isinstance(row, dict)]
        sprint_labels = [str(row.get("sprint_id", i + 1)) for i, row in enumerate(per_sprint) if isinstance(row, dict)]
        rolling_reliability = self._rolling_mean(reliability_series, window=max(1, int(rolling_window)))

        summary_block = payload.get("summary", {})
        if not isinstance(summary_block, dict):
            summary_block = {}

        reliability_mean = self._summary_or_calc(summary_block.get("reliability_mean"), reliability_series)
        reliability_std = self._summary_or_calc(
            summary_block.get("reliability_std_dev"),
            reliability_series,
            use_stdev=True,
        )
        variance_mean = self._summary_or_calc(summary_block.get("variance_mean"), variance_series)
        variance_std = self._summary_or_calc(summary_block.get("variance_std_dev"), variance_series, use_stdev=True)
        reliability_p05 = self._percentile(reliability_series, 0.05)
        reliability_p95 = self._percentile(reliability_series, 0.95)
        collapse_count = sum(1 for score in reliability_series if score < 40.0)
        collapse_rate = (collapse_count / len(reliability_series) * 100.0) if reliability_series else 0.0

        config_in = payload.get("pm_config", {})
        if not isinstance(config_in, dict):
            config_in = {}
        config = {
            "planning_granularity": config_in.get("planning_granularity"),
            "escalation_threshold": config_in.get("escalation_threshold"),
            "buffer_ratio": config_in.get("buffer_ratio"),
            "sprint_count": payload.get("sprint_count", len(reliability_series)),
            "base_seed": payload.get("base_seed"),
        }

        summary = {
            "reliability_mean": round(reliability_mean, 4),
            "reliability_std_dev": round(reliability_std, 4),
            "variance_mean": round(variance_mean, 4),
            "variance_std_dev": round(variance_std, 4),
            "reliability_p05": round(reliability_p05, 4),
            "reliability_p95": round(reliability_p95, 4),
            "collapse_count_lt_40": collapse_count,
            "collapse_rate_pct": round(collapse_rate, 4),
        }

        return {
            "available": True,
            "config": config,
            "summary": summary,
            "reliability_series": reliability_series,
            "variance_series": variance_series,
            "rolling_reliability": rolling_reliability,
            "sprint_labels": sprint_labels,
        }

    def _read_payload(self) -> Dict[str, Any]:
        try:
            parsed = json.loads(self.results_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

        if not isinstance(parsed, dict):
            return {}

        if parsed.get("schema_version") == "phase2A_v1_collection":
            runs = parsed.get("runs", [])
            if isinstance(runs, list) and runs:
                latest = runs[-1]
                return latest if isinstance(latest, dict) else {}
            return {}
        return parsed

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _rolling_mean(values: List[float], window: int) -> List[float]:
        if not values:
            return []
        output: List[float] = []
        for idx in range(len(values)):
            start = max(0, idx - window + 1)
            chunk = values[start : idx + 1]
            output.append(round(mean(chunk), 4))
        return output

    @staticmethod
    def _percentile(values: List[float], fraction: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        if len(ordered) == 1:
            return ordered[0]
        pos = (len(ordered) - 1) * max(0.0, min(1.0, fraction))
        low = int(pos)
        high = min(low + 1, len(ordered) - 1)
        alpha = pos - low
        return ordered[low] * (1.0 - alpha) + ordered[high] * alpha

    @staticmethod
    def _summary_or_calc(source_value: Any, series: List[float], use_stdev: bool = False) -> float:
        try:
            return float(source_value)
        except (TypeError, ValueError):
            if not series:
                return 0.0
            if use_stdev:
                return stdev(series) if len(series) > 1 else 0.0
            return mean(series)
