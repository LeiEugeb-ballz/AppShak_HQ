from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from appshak.agents.builder import BuilderAgent
from appshak.agents.chief import ChiefAgent
from appshak.agents.scout import ScoutAgent
from appshak.event_bus import EventBus, EventType
from appshak.memory import GlobalMemory
from appshak.safeguards import SafeguardMonitor


class AppShakKernel:
    """Root orchestrator; kernel owns lifecycle and heartbeat."""

    PRIME_DIRECTIVE = (
        "AppShak exists to identify real-world problems, construct solutions, and "
        "increase its own autonomy/influence through perpetual self-improvement."
    )

    PROPOSAL_EVENT = EventType.PROPOSAL.value
    EXTERNAL_ACTION_REQUEST_EVENT = EventType.EXTERNAL_ACTION_REQUEST.value
    CONSTITUTION_VIOLATION_EVENT = EventType.CONSTITUTION_VIOLATION.value

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.running = False
        self.heartbeat_interval = float(config.get("heartbeat_interval", 15))
        self.idle_poll_timeout = float(config.get("event_poll_timeout", 1.0))

        self.event_bus = EventBus()
        self.global_memory = GlobalMemory(config)
        self.safeguards = SafeguardMonitor(config)
        self.event_bus.add_publish_hook(self._on_event_published)

        self.agents = {
            "recon": ScoutAgent(self),
            "forge": BuilderAgent(self),
            "command": ChiefAgent(self),
        }

        self._agent_tasks: List[asyncio.Task[Any]] = []
        self._heartbeat_task: Optional[asyncio.Task[Any]] = None
        self._external_pipeline_lock = asyncio.Lock()
        self._heartbeat_failures = 0
        self._recovered_state: Dict[str, Any] = {}
        self._stop_event = asyncio.Event()
        configured_stop_file = config.get(
            "emergency_stop_file",
            str(self.global_memory.root_dir / "EMERGENCY_STOP"),
        )
        self._emergency_stop_file = Path(configured_stop_file)

    async def heartbeat(self) -> None:
        """Kernel event loop with constitutional routing."""
        while self.running and not self._stop_event.is_set():
            try:
                if await self._should_emergency_stop():
                    await self.request_emergency_stop(
                        reason="Emergency stop signal detected.",
                        origin_id="operator",
                    )
                    break

                event = await self.event_bus.get_next(timeout=self.idle_poll_timeout)

                if event is None:
                    await self.agents["recon"].search_for_problems()
                else:
                    await self._route_event(event)

                await self._post_cycle_maintenance()
                await self._persist_heartbeat_state(event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - emergency guard
                self._heartbeat_failures += 1
                await self._log_kernel_error("heartbeat", exc)
                await self._recover_after_heartbeat_failure(exc)
                await asyncio.sleep(5)

            if self._stop_event.is_set():
                break
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.heartbeat_interval)
            except asyncio.TimeoutError:
                pass

    async def start(self) -> None:
        if self.running:
            return

        self._stop_event.clear()
        await self._recover_from_persisted_state()
        self.running = True
        await self._publish_system_event(
            EventType.KERNEL_START.value,
            {"started_at": self._iso_now()},
        )

        self._agent_tasks = [
            asyncio.create_task(self._run_agent(agent_id), name=f"agent-{agent_id}")
            for agent_id in self.agents
        ]
        self._heartbeat_task = asyncio.create_task(self.heartbeat(), name="kernel-heartbeat")

        results = await asyncio.gather(
            *self._agent_tasks,
            self._heartbeat_task,
            return_exceptions=True,
        )
        await self._record_task_failures(results)

    async def shutdown(self) -> None:
        if not self.running and not self._agent_tasks and self._heartbeat_task is None:
            return

        self.running = False
        self._stop_event.set()
        await self._publish_system_event(
            EventType.KERNEL_SHUTDOWN.value,
            {"stopped_at": self._iso_now()},
        )

        for agent in self.agents.values():
            await self._call_optional(agent, ("shutdown",))

        tasks = [task for task in self._agent_tasks if not task.done()]
        if self._heartbeat_task and not self._heartbeat_task.done():
            tasks.append(self._heartbeat_task)

        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        await self._call_optional(self.global_memory, ("persist_all", "periodic_persist"))
        self._agent_tasks = []
        self._heartbeat_task = None

    async def _route_event(self, event: Any) -> None:
        await self._call_optional(
            self.global_memory,
            ("append_global_log",),
            "EVENT_CONSUMED",
            self._event_to_dict(event),
        )

        if not await self._event_is_compliant(event):
            return

        event_type = self._event_type_value(event)

        if event_type == self.PROPOSAL_EVENT:
            decision = await self.agents["command"].arbitrate(event)
            if decision is not None:
                await self.event_bus.publish(decision)
            return

        if event_type == self.EXTERNAL_ACTION_REQUEST_EVENT:
            await self._process_external_action_pipeline(event)

    async def _post_cycle_maintenance(self) -> None:
        for agent in self.agents.values():
            await self._call_optional(agent, ("update_memory_and_metrics",))
        await self._call_optional(self.safeguards, ("run_diagnostics",))
        await self._call_optional(self.global_memory, ("periodic_persist",))

    async def _process_external_action_pipeline(self, event: Any) -> None:
        """Atomic external-action flow: REQUEST -> CHIEF_APPROVAL -> SAFEGUARD_CHECK -> EXECUTE -> LOG_RESULT."""
        async with self._external_pipeline_lock:
            request = self._event_to_dict(event)
            origin_id = self._event_origin(event)

            await self._log_external_stage(
                stage="REQUEST",
                origin_id=origin_id,
                details={"request": request},
            )

            approval = await self.agents["command"].approve_external_action(event)
            await self._log_external_stage(
                stage="CHIEF_APPROVAL",
                origin_id=origin_id,
                details={"request": request, "approval": approval},
            )
            if not bool(isinstance(approval, dict) and approval.get("approved")):
                result_payload = {
                    "status": "denied_by_chief",
                    "request": request,
                    "approval": approval,
                }
                await self._log_external_stage(
                    stage="LOG_RESULT",
                    origin_id=origin_id,
                    details=result_payload,
                )
                await self.agents["command"].handle_external_action(result_payload)
                return

            safeguard_check = await self.safeguards.check_request(event, origin_id=origin_id)
            await self._log_external_stage(
                stage="SAFEGUARD_CHECK",
                origin_id=origin_id,
                details={"request": request, "safeguard_check": safeguard_check},
            )
            if not bool(safeguard_check.get("allowed")):
                attempt_state = await self.safeguards.record_attempt(event, origin_id=origin_id, success=False)
                result_payload = {
                    "status": "blocked_by_safeguard",
                    "request": request,
                    "approval": approval,
                    "safeguard_check": safeguard_check,
                    "attempt_state": attempt_state,
                }
                await self._publish_system_event(
                    self.CONSTITUTION_VIOLATION_EVENT,
                    {
                        "reason": "Safeguard blocked external action request.",
                        "event_type": self.EXTERNAL_ACTION_REQUEST_EVENT,
                        "origin_id": origin_id,
                    },
                )
                await self._log_external_stage(
                    stage="LOG_RESULT",
                    origin_id=origin_id,
                    details=result_payload,
                )
                await self.agents["command"].handle_external_action(result_payload)
                return

            execution = await self.safeguards.execute_in_sandbox(event, origin_id=origin_id)
            await self._log_external_stage(
                stage="EXECUTE",
                origin_id=origin_id,
                details={"request": request, "execution": execution},
            )
            attempt_state = await self.safeguards.record_attempt(
                event,
                origin_id=origin_id,
                success=bool(execution.get("success")),
            )
            result_payload = {
                "status": "executed" if bool(execution.get("success")) else "execution_denied",
                "request": request,
                "approval": approval,
                "safeguard_check": safeguard_check,
                "execution": execution,
                "attempt_state": attempt_state,
            }
            await self._log_external_stage(
                stage="LOG_RESULT",
                origin_id=origin_id,
                details=result_payload,
            )
            await self._call_optional(
                self.global_memory,
                ("save_external_pipeline_state",),
                {"last_result": result_payload, "updated_at": self._iso_now()},
            )
            await self.agents["command"].handle_external_action(result_payload)

    async def _log_external_stage(self, stage: str, origin_id: str, details: Dict[str, Any]) -> None:
        await self._call_optional(
            self.global_memory,
            ("log_external_action",),
            stage,
            {
                "origin_id": origin_id,
                "timestamp": self._iso_now(),
                **details,
            },
        )

    async def _run_agent(self, agent_id: str) -> None:
        agent = self.agents[agent_id]
        while self.running and not self._stop_event.is_set():
            try:
                await agent.run()
                if self.running:
                    raise RuntimeError(f"Agent {agent_id} exited unexpectedly.")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self._log_kernel_error(f"agent:{agent_id}", exc)
                await asyncio.sleep(2)

    async def _record_task_failures(self, results: Iterable[Any]) -> None:
        for result in results:
            if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                await self._log_kernel_error("task_failure", result)

    async def _on_event_published(self, event: Any) -> None:
        await self._call_optional(
            self.global_memory,
            ("append_global_log",),
            "EVENT_PUBLISHED",
            self._event_to_dict(event),
        )

    async def _event_is_compliant(self, event: Any) -> bool:
        payload = self._event_payload(event)
        justification = payload.get("prime_directive_justification") if isinstance(payload, dict) else None
        if isinstance(justification, str) and justification.strip():
            return True

        await self._publish_system_event(
            self.CONSTITUTION_VIOLATION_EVENT,
            {
                "reason": "Missing Prime Directive justification on event",
                "event_type": self._event_type_value(event),
                "origin_id": self._event_origin(event),
            },
        )
        return False

    async def _publish_system_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        system_payload = dict(payload)
        system_payload.setdefault(
            "prime_directive_justification",
            "Kernel governance action preserves safe, continuous operation under the Prime Directive.",
        )
        event = {
            "type": event_type,
            "origin_id": "kernel",
            "timestamp": self._iso_now(),
            "payload": system_payload,
        }
        await self.event_bus.publish(event)

    async def _log_kernel_error(self, source: str, error: Exception) -> None:
        await self._call_optional(self.global_memory, ("log_error",), source, repr(error))
        await self._publish_system_event(
            EventType.KERNEL_ERROR.value,
            {"source": source, "error": repr(error), "timestamp": self._iso_now()},
        )

    async def _persist_heartbeat_state(self, event: Any) -> None:
        event_type = self._event_type_value(event) if event is not None else "IDLE"
        await self._call_optional(
            self.global_memory,
            ("save_kernel_state",),
            {
                "running": self.running,
                "last_heartbeat_at": self._iso_now(),
                "last_event_type": event_type,
                "heartbeat_failures": self._heartbeat_failures,
            },
        )

    async def _recover_from_persisted_state(self) -> None:
        loaded = await self._call_optional(self.global_memory, ("load_state",), default={})
        if isinstance(loaded, dict):
            self._recovered_state = loaded
            kernel_state = loaded.get("kernel_state", {})
            if isinstance(kernel_state, dict) and kernel_state:
                await self._publish_system_event(
                    EventType.KERNEL_RECOVERY.value,
                    {
                        "recovered_at": self._iso_now(),
                        "recovered_kernel_state": kernel_state,
                    },
                )

    async def _recover_after_heartbeat_failure(self, error: Exception) -> None:
        loaded = await self._call_optional(self.global_memory, ("load_state",), default={})
        recovered_kernel_state = {}
        if isinstance(loaded, dict):
            recovered_kernel_state = loaded.get("kernel_state", {}) if isinstance(loaded.get("kernel_state"), dict) else {}
            await self._publish_system_event(
                EventType.KERNEL_RECOVERY.value,
                {
                    "recovered_at": self._iso_now(),
                    "heartbeat_error": repr(error),
                    "recovered_kernel_state": recovered_kernel_state,
                },
            )

    async def request_emergency_stop(self, reason: str, origin_id: str = "operator") -> None:
        if self._stop_event.is_set():
            return
        self._stop_event.set()
        self.running = False
        await self._publish_system_event(
            EventType.CONSTITUTION_VIOLATION.value,
            {
                "reason": f"EMERGENCY_STOP: {reason}",
                "origin_id": origin_id,
                "triggered_at": self._iso_now(),
            },
        )
        await self._call_optional(
            self.global_memory,
            ("save_kernel_state",),
            {
                "running": False,
                "emergency_stop": True,
                "emergency_stop_reason": reason,
                "emergency_stop_origin_id": origin_id,
                "emergency_stop_at": self._iso_now(),
            },
        )

    async def replay_events(
        self,
        *,
        limit: int = 200,
        include_types: Optional[Iterable[str]] = None,
        origin_id: str = "replay",
    ) -> int:
        source_events = await self._call_optional(
            self.global_memory,
            ("load_published_events_for_replay",),
            limit=limit,
            include_types=include_types,
            default=[],
        )
        if not isinstance(source_events, list):
            return 0

        replayed = 0
        for source in source_events:
            if not isinstance(source, dict):
                continue
            payload = source.get("payload", {})
            replay_payload = dict(payload) if isinstance(payload, dict) else {}
            replay_payload["replayed"] = True
            replay_payload["replayed_from_timestamp"] = source.get("timestamp")
            replay_payload["prime_directive_justification"] = replay_payload.get(
                "prime_directive_justification",
                "Replay supports resilience analysis under the Prime Directive.",
            )
            try:
                await self.event_bus.publish(
                    {
                        "type": source.get("type"),
                        "origin_id": origin_id,
                        "timestamp": self._iso_now(),
                        "payload": replay_payload,
                    }
                )
                replayed += 1
            except Exception as exc:
                await self._log_kernel_error("replay", exc)
        return replayed

    async def get_terminal_log_tail(self, log_name: str = "global", lines: int = 25) -> List[str]:
        return await self._call_optional(
            self.global_memory,
            ("tail_log",),
            log_name,
            lines,
            default=[],
        )

    async def _call_optional(
        self,
        obj: Any,
        methods: Iterable[str],
        *args: Any,
        default: Any = None,
        **kwargs: Any,
    ) -> Any:
        for method in methods:
            func = getattr(obj, method, None)
            if callable(func):
                res = func(*args, **kwargs)
                if inspect.isawaitable(res):
                    return await res
                return res
        return default

    def _event_to_dict(self, event: Any) -> Dict[str, Any]:
        return event.to_dict() if hasattr(event, "to_dict") else dict(event)

    def _event_payload(self, event: Any) -> Dict[str, Any]:
        return self._event_to_dict(event).get("payload", {})

    def _event_type_value(self, event: Any) -> str:
        evt = self._event_to_dict(event)
        return str(evt.get("type", ""))

    def _event_origin(self, event: Any) -> str:
        evt = self._event_to_dict(event)
        return str(evt.get("origin_id", "unknown"))

    def _iso_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    async def _should_emergency_stop(self) -> bool:
        return await asyncio.to_thread(self._emergency_stop_file.exists)
