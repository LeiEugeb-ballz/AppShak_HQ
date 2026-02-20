from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from random import Random
from typing import Any, Dict, List, Optional

from appshak.event_bus import EventType

from .metrics_engine import MetricsEngine
from .performance_history import PerformanceHistoryManager
from .worker_profiles import WorkerProfile


@dataclass(frozen=True)
class Task:
    id: str
    type: str
    complexity: int
    estimated_effort: float
    deadline: str
    ambiguity_flag: bool
    risk_score: float


@dataclass(frozen=True)
class PMConfig:
    planning_granularity: int
    escalation_threshold: float
    buffer_ratio: float


class SprintArena:
    """
    Controlled startup sprint simulation environment.
    Isolated from mutation, teaching, scaling, and role expansion logic.
    """

    def __init__(
        self,
        *,
        kernel: Any | None = None,
        history_manager: PerformanceHistoryManager | None = None,
        metrics_engine: MetricsEngine | None = None,
        workers: Optional[List[WorkerProfile]] = None,
        seed: Optional[int] = None,
    ) -> None:
        self.kernel = kernel
        self.event_bus = getattr(kernel, "event_bus", None)
        self.agent_registry = getattr(kernel, "agents", {})
        self.metrics = metrics_engine or MetricsEngine()
        self.history = history_manager or PerformanceHistoryManager()
        self.pm_config = PMConfig(
            planning_granularity=3,
            escalation_threshold=0.40,
            buffer_ratio=0.20,
        )
        self._base_seed = seed
        self._rng = Random(seed)
        self.workers = workers or self._default_workers()

    def generate_sprint_backlog(self, sprint_id: str, rng: Random) -> List[Task]:
        backlog: List[Task] = []
        now = datetime.now(timezone.utc)

        def build(task_type: str, idx: int, ambiguity: bool = False) -> Task:
            complexity = rng.randint(1, 5)
            effort = round(complexity * rng.uniform(1.2, 3.0), 2)
            deadline_hours = effort * (1.2 + rng.uniform(0.2, 0.8))
            risk = min(1.0, (complexity / 5.0) * 0.6 + (0.35 if ambiguity else 0.1))
            return Task(
                id=f"{sprint_id}-{task_type.lower()}-{idx:02d}",
                type=task_type,
                complexity=complexity,
                estimated_effort=effort,
                deadline=(now + timedelta(hours=deadline_hours)).isoformat(),
                ambiguity_flag=ambiguity,
                risk_score=round(risk, 3),
            )

        for i in range(6):
            backlog.append(build("FEATURE", i + 1))
        for i in range(3):
            backlog.append(build("BUGFIX", i + 1))
        backlog.append(build("REFACTOR", 1))
        backlog.append(build("AMBIGUOUS", 1, ambiguity=True))
        return backlog

    async def run_sprint_cycle(self, sprint_id: str, seed: Optional[int] = None) -> Dict[str, Any]:
        rng = Random(seed if seed is not None else self._rng.randint(1, 10_000_000))
        backlog = self.generate_sprint_backlog(sprint_id, rng)
        injection_index = rng.randint(2, len(backlog) - 1)
        urgent_task = self._build_urgent_task(sprint_id, rng)
        backlog.insert(injection_index, urgent_task)

        await self._emit_arena_event(
            "SPRINT_START",
            {"sprint_id": sprint_id, "backlog_count": len(backlog), "urgent_injection_index": injection_index},
        )

        worker_available_hours = {worker.name: 0.0 for worker in self.workers}
        task_results: List[Dict[str, Any]] = []
        escalations = 0

        for i, task in enumerate(backlog):
            if task.type == "URGENT":
                await self._emit_arena_event(
                    "URGENT_INJECTION",
                    {"sprint_id": sprint_id, "task_id": task.id, "position": i},
                )

            selected_worker = self._select_worker(worker_available_hours, rng)
            effective_effort = self._pm_adjusted_effort(task)
            deadline_hours = self._deadline_hours(task)

            outcome = selected_worker.sample_outcome(
                base_effort_hours=effective_effort,
                task_complexity=task.complexity,
                task_risk_score=task.risk_score + (0.15 if task.ambiguity_flag else 0.0),
                rng=rng,
            )
            completion_hours = worker_available_hours[selected_worker.name] + float(outcome["completion_hours"])
            completed_on_time = bool(outcome["completed"]) and completion_hours <= deadline_hours

            escalated = False
            if (not completed_on_time) and task.risk_score >= self.pm_config.escalation_threshold:
                escalated = True
                escalations += 1
                selected_worker = self._select_worker(worker_available_hours, rng, avoid=selected_worker.name)
                completion_hours += rng.uniform(0.1, 0.6)  # reassignment overhead

            worker_available_hours[selected_worker.name] = completion_hours

            task_results.append(
                {
                    "task_id": task.id,
                    "task_type": task.type,
                    "worker": selected_worker.name,
                    "completed": bool(outcome["completed"]),
                    "completed_on_time": completed_on_time,
                    "needs_rework": bool(outcome["needs_rework"]),
                    "delay_applied": bool(outcome["delay_applied"]),
                    "completion_hours": round(completion_hours, 3),
                    "deadline_hours": round(deadline_hours, 3),
                    "escalated": escalated,
                    "is_urgent": task.type == "URGENT",
                }
            )

        reliability = self.metrics.compute_reliability(task_results)
        variance = self.metrics.compute_variance(task_results)
        completed = sum(1 for r in task_results if r["completed"])
        misses = sum(1 for r in task_results if not r["completed_on_time"])
        rework = sum(1 for r in task_results if r["needs_rework"])

        record = {
            "sprint_id": sprint_id,
            "pm_config_snapshot": asdict(self.pm_config),
            "reliability_score": round(reliability, 3),
            "variance_score": round(variance, 3),
            "task_summary": {
                "total_tasks": len(task_results),
                "completed_tasks": completed,
                "deadline_misses": misses,
                "rework_events": rework,
                "escalations": escalations,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.history.append_record(record)

        await self._emit_arena_event(
            "SPRINT_COMPLETE",
            {
                "sprint_id": sprint_id,
                "reliability": record["reliability_score"],
                "variance": record["variance_score"],
                "task_summary": record["task_summary"],
            },
        )
        self._print_summary(record)
        return {
            "record": record,
            "tasks": [asdict(t) for t in backlog],
            "task_results": task_results,
        }

    async def run_consecutive_sprints(self, count: int = 10, seed: Optional[int] = None) -> List[Dict[str, Any]]:
        base_rng = Random(seed if seed is not None else self._base_seed)
        results: List[Dict[str, Any]] = []
        for i in range(1, count + 1):
            sprint_seed = base_rng.randint(1, 1_000_000_000)
            sprint_id = f"{i:02d}"
            results.append(await self.run_sprint_cycle(sprint_id=sprint_id, seed=sprint_seed))
            await asyncio.sleep(0)
        return results

    def export_history(self, output_path: str) -> str:
        return str(self.history.export_history(output_path))

    def _pm_adjusted_effort(self, task: Task) -> float:
        # Granularity lowers planning uncertainty for feature tasks.
        granularity_bonus = 1.0 - ((self.pm_config.planning_granularity - 1) * 0.04)
        feature_multiplier = granularity_bonus if task.type == "FEATURE" else 1.0
        buffer_multiplier = 1.0 + self.pm_config.buffer_ratio
        ambiguity_penalty = 1.15 if task.ambiguity_flag else 1.0
        return max(0.2, task.estimated_effort * feature_multiplier * buffer_multiplier * ambiguity_penalty)

    def _deadline_hours(self, task: Task) -> float:
        created = datetime.now(timezone.utc)
        deadline = datetime.fromisoformat(task.deadline)
        return max(0.2, (deadline - created).total_seconds() / 3600.0)

    def _select_worker(self, availability: Dict[str, float], rng: Random, avoid: Optional[str] = None) -> WorkerProfile:
        candidates = [w for w in self.workers if w.name != avoid]
        if not candidates:
            candidates = list(self.workers)
        lowest = min(candidates, key=lambda w: availability[w.name])
        # Small randomness to keep stochastic assignment pressure.
        if len(candidates) > 1 and rng.random() < 0.2:
            return rng.choice(candidates)
        return lowest

    def _build_urgent_task(self, sprint_id: str, rng: Random) -> Task:
        complexity = rng.randint(2, 5)
        effort = round(complexity * rng.uniform(1.0, 2.2), 2)
        deadline = datetime.now(timezone.utc) + timedelta(hours=effort * rng.uniform(0.5, 0.9))
        risk = min(1.0, (complexity / 5.0) * 0.7 + 0.2)
        return Task(
            id=f"{sprint_id}-urgent-01",
            type="URGENT",
            complexity=complexity,
            estimated_effort=effort,
            deadline=deadline.isoformat(),
            ambiguity_flag=False,
            risk_score=round(risk, 3),
        )

    async def _emit_arena_event(self, kind: str, payload: Dict[str, Any]) -> None:
        if self.event_bus is None:
            return
        try:
            await self.event_bus.publish(
                {
                    "type": EventType.AGENT_STATUS.value,
                    "origin_id": "sprint_arena",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "arena_event": kind,
                        **payload,
                        "prime_directive_justification": (
                            "Sprint arena evaluation advances reliable execution under controlled uncertainty."
                        ),
                    },
                }
            )
        except Exception:
            # Arena telemetry must not break simulation loop.
            return

    @staticmethod
    def _default_workers() -> List[WorkerProfile]:
        return [
            WorkerProfile(
                name="worker_alpha",
                success_rate=0.86,
                delay_probability=0.18,
                rework_probability=0.11,
                consistency_variance=0.15,
            ),
            WorkerProfile(
                name="worker_bravo",
                success_rate=0.79,
                delay_probability=0.24,
                rework_probability=0.16,
                consistency_variance=0.20,
            ),
            WorkerProfile(
                name="worker_charlie",
                success_rate=0.90,
                delay_probability=0.12,
                rework_probability=0.08,
                consistency_variance=0.10,
            ),
            WorkerProfile(
                name="worker_delta",
                success_rate=0.74,
                delay_probability=0.28,
                rework_probability=0.19,
                consistency_variance=0.22,
            ),
        ]

    def _print_summary(self, record: Dict[str, Any]) -> None:
        cfg = record["pm_config_snapshot"]
        summary = record["task_summary"]
        print(
            f"Sprint {record['sprint_id']} Results:\n"
            f"PM Config: {{granularity: {cfg['planning_granularity']}, "
            f"escalation: {cfg['escalation_threshold']}, buffer: {cfg['buffer_ratio']}}}\n"
            f"Reliability: {record['reliability_score']}\n"
            f"Variance: {record['variance_score']}\n"
            f"Tasks Completed: {summary['completed_tasks']}/{summary['total_tasks']}\n"
            f"Deadline Misses: {summary['deadline_misses']}\n"
            f"Rework Events: {summary['rework_events']}"
        )

