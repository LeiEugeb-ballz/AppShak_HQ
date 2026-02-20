from __future__ import annotations

import asyncio
import json
from pathlib import Path
from statistics import mean, stdev
from typing import Any, Dict, List, Optional

from .sprint_arena import PMConfig, SprintArena
from .worker_profiles import WorkerProfile


class StatisticalCharacterizer:
    """
    Phase 2A baseline characterization for a fixed PM configuration.
    Runs deterministic seed progression across independent sprint simulations.
    """

    SCHEMA_VERSION = "phase2A_v1"

    def __init__(
        self,
        *,
        kernel: Any | None = None,
        base_seed: int,
        pm_config: Dict[str, Any],
        sprint_count: int,
        worker_profiles: Optional[List[WorkerProfile]] = None,
    ) -> None:
        if sprint_count <= 0:
            raise ValueError("sprint_count must be > 0")

        required = {"planning_granularity", "escalation_threshold", "buffer_ratio"}
        missing = required.difference(pm_config.keys())
        if missing:
            raise ValueError(f"pm_config missing keys: {sorted(missing)}")

        self.kernel = kernel
        self.base_seed = int(base_seed)
        self.pm_config: Dict[str, Any] = {
            "planning_granularity": int(pm_config["planning_granularity"]),
            "escalation_threshold": float(pm_config["escalation_threshold"]),
            "buffer_ratio": float(pm_config["buffer_ratio"]),
        }
        self.sprint_count = int(sprint_count)
        self.worker_profiles = list(worker_profiles) if worker_profiles is not None else None

        self.per_sprint: List[Dict[str, Any]] = []
        self.summary: Dict[str, float] = {}

    async def run(self) -> Dict[str, Any]:
        self.per_sprint = []
        self.summary = {}

        for i in range(self.sprint_count):
            seed = self.base_seed + i
            sprint_id = f"{i + 1:03d}"

            arena = SprintArena(
                kernel=self.kernel,
                seed=seed,
                workers=self.worker_profiles,
            )
            arena.pm_config = PMConfig(
                planning_granularity=self.pm_config["planning_granularity"],
                escalation_threshold=self.pm_config["escalation_threshold"],
                buffer_ratio=self.pm_config["buffer_ratio"],
            )

            sprint_result = await arena.run_sprint_cycle(sprint_id=sprint_id, seed=seed)
            record = sprint_result.get("record", {})
            task_summary = record.get("task_summary", {})
            total_tasks = int(task_summary.get("total_tasks", 0))
            tasks_completed = int(task_summary.get("completed_tasks", 0))
            deadline_misses = int(task_summary.get("deadline_misses", 0))
            rework_events = int(task_summary.get("rework_events", 0))
            urgent_success = self._urgent_success(sprint_result.get("task_results", []))
            completion_rate = (tasks_completed / total_tasks * 100.0) if total_tasks else 0.0

            self.per_sprint.append(
                {
                    "sprint_id": sprint_id,
                    "seed": seed,
                    "reliability": float(record.get("reliability_score", 0.0)),
                    "variance": float(record.get("variance_score", 0.0)),
                    "tasks_completed": tasks_completed,
                    "deadline_misses": deadline_misses,
                    "rework_events": rework_events,
                    "urgent_success": urgent_success,
                    "completion_rate": completion_rate,
                }
            )
            await asyncio.sleep(0)

        self.summary = self._compute_summary()
        self._print_console_summary()
        return self.results_dict()

    def export_results(self, path: str, *, append: bool = False, overwrite: bool = True) -> Path:
        payload = self.results_dict()
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if append:
            existing_runs: List[Dict[str, Any]] = []
            if output_path.exists():
                existing_payload = self._read_json(output_path)
                if isinstance(existing_payload, dict) and isinstance(existing_payload.get("runs"), list):
                    existing_runs = list(existing_payload["runs"])
                elif isinstance(existing_payload, dict):
                    existing_runs = [existing_payload]
                elif isinstance(existing_payload, list):
                    existing_runs = [r for r in existing_payload if isinstance(r, dict)]
            existing_runs.append(payload)
            output_payload: Dict[str, Any] = {
                "schema_version": "phase2A_v1_collection",
                "runs": existing_runs,
            }
            output_path.write_text(json.dumps(output_payload, indent=2, ensure_ascii=True), encoding="utf-8")
            return output_path

        if output_path.exists() and not overwrite:
            raise FileExistsError(f"Refusing to overwrite existing file: {output_path}")
        output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        return output_path

    def results_dict(self) -> Dict[str, Any]:
        if not self.summary and self.per_sprint:
            self.summary = self._compute_summary()

        return {
            "schema_version": self.SCHEMA_VERSION,
            "pm_config": dict(self.pm_config),
            "sprint_count": self.sprint_count,
            "base_seed": self.base_seed,
            "summary": dict(self.summary),
            "per_sprint": [
                {
                    "sprint_id": item["sprint_id"],
                    "seed": item["seed"],
                    "reliability": item["reliability"],
                    "variance": item["variance"],
                    "tasks_completed": item["tasks_completed"],
                    "deadline_misses": item["deadline_misses"],
                    "rework_events": item["rework_events"],
                    "urgent_success": item["urgent_success"],
                }
                for item in self.per_sprint
            ],
        }

    def _compute_summary(self) -> Dict[str, float]:
        if not self.per_sprint:
            return {
                "reliability_mean": 0.0,
                "reliability_std_dev": 0.0,
                "variance_mean": 0.0,
                "variance_std_dev": 0.0,
                "reliability_min": 0.0,
                "reliability_max": 0.0,
                "variance_min": 0.0,
                "variance_max": 0.0,
                "completion_rate_mean": 0.0,
                "deadline_miss_mean": 0.0,
                "rework_mean": 0.0,
                "urgent_success_rate": 0.0,
            }

        reliability_values = [float(item["reliability"]) for item in self.per_sprint]
        variance_values = [float(item["variance"]) for item in self.per_sprint]
        completion_values = [float(item["completion_rate"]) for item in self.per_sprint]
        deadline_values = [float(item["deadline_misses"]) for item in self.per_sprint]
        rework_values = [float(item["rework_events"]) for item in self.per_sprint]
        urgent_values = [1.0 if bool(item["urgent_success"]) else 0.0 for item in self.per_sprint]

        return {
            "reliability_mean": round(mean(reliability_values), 4),
            "reliability_std_dev": round(self._safe_stdev(reliability_values), 4),
            "variance_mean": round(mean(variance_values), 4),
            "variance_std_dev": round(self._safe_stdev(variance_values), 4),
            "reliability_min": round(min(reliability_values), 4),
            "reliability_max": round(max(reliability_values), 4),
            "variance_min": round(min(variance_values), 4),
            "variance_max": round(max(variance_values), 4),
            "completion_rate_mean": round(mean(completion_values), 4),
            "deadline_miss_mean": round(mean(deadline_values), 4),
            "rework_mean": round(mean(rework_values), 4),
            "urgent_success_rate": round(mean(urgent_values) * 100.0, 4),
        }

    def _print_console_summary(self) -> None:
        s = self.summary
        print(
            "Phase 2A Statistical Characterization Results\n"
            f"PM Config: {self.pm_config}\n"
            f"Sprints Run: {self.sprint_count}\n\n"
            "Reliability:\n"
            f"Mean: {s.get('reliability_mean', 0.0):.2f}\n"
            f"Std Dev: {s.get('reliability_std_dev', 0.0):.2f}\n"
            f"Min: {s.get('reliability_min', 0.0):.2f}\n"
            f"Max: {s.get('reliability_max', 0.0):.2f}\n\n"
            "Variance:\n"
            f"Mean: {s.get('variance_mean', 0.0):.2f}\n"
            f"Std Dev: {s.get('variance_std_dev', 0.0):.2f}\n"
            f"Min: {s.get('variance_min', 0.0):.2f}\n"
            f"Max: {s.get('variance_max', 0.0):.2f}\n\n"
            f"Completion Mean: {s.get('completion_rate_mean', 0.0):.2f}\n"
            f"Deadline Miss Mean: {s.get('deadline_miss_mean', 0.0):.2f}\n"
            f"Rework Mean: {s.get('rework_mean', 0.0):.2f}\n"
            f"Urgent Success Rate: {s.get('urgent_success_rate', 0.0):.2f}"
        )

    @staticmethod
    def _safe_stdev(values: List[float]) -> float:
        if len(values) < 2:
            return 0.0
        return stdev(values)

    @staticmethod
    def _urgent_success(task_results: Any) -> bool:
        if not isinstance(task_results, list):
            return False
        urgent_tasks = [row for row in task_results if isinstance(row, dict) and bool(row.get("is_urgent"))]
        if not urgent_tasks:
            return False
        return all(bool(row.get("completed")) for row in urgent_tasks)

    @staticmethod
    def _read_json(path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None


async def main() -> None:
    from appshak import AppShakKernel

    kernel = AppShakKernel({"memory_root": "appshak_state"})
    pm_config = {
        "planning_granularity": 3,
        "escalation_threshold": 0.4,
        "buffer_ratio": 0.2,
    }

    characterizer = StatisticalCharacterizer(
        kernel=kernel,
        base_seed=1000,
        pm_config=pm_config,
        sprint_count=100,
    )

    await characterizer.run()
    characterizer.export_results("appshak_state/phase2A_results.json")


if __name__ == "__main__":
    asyncio.run(main())
