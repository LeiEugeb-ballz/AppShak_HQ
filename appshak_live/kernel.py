"""Live AppShak Kernel — root orchestrator with metrics broadcasting."""
from __future__ import annotations

import asyncio
import inspect
import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from appshak_live.agents import BuilderAgent, ChiefAgent, ScoutAgent
from appshak_live.event_bus import EventBus, EventType
from appshak_live.safeguards import SafeguardMonitor


class AppShakKernel:
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
        self.heartbeat_interval = float(config.get("heartbeat_interval", 5))
        self.idle_poll_timeout = float(config.get("event_poll_timeout", 1.0))

        self.event_bus = EventBus()
        self.safeguards = SafeguardMonitor(config)

        self.agents = {
            "recon": ScoutAgent(self),
            "forge": BuilderAgent(self),
            "command": ChiefAgent(self),
        }

        self._agent_tasks: List[asyncio.Task[Any]] = []
        self._heartbeat_task: Optional[asyncio.Task[Any]] = None
        self._metrics_task: Optional[asyncio.Task[Any]] = None
        self._external_pipeline_lock = asyncio.Lock()
        self._heartbeat_failures = 0
        self._heartbeat_count = 0
        self._events_routed = 0
        self._violations = 0

    async def heartbeat(self) -> None:
        while self.running:
            try:
                self._heartbeat_count += 1
                event = await self.event_bus.get_next(timeout=self.idle_poll_timeout)

                if event is None:
                    await self.agents["recon"].search_for_problems()
                else:
                    self._events_routed += 1
                    await self._route_event(event)

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._heartbeat_failures += 1

            await asyncio.sleep(self.heartbeat_interval)

    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        await self._publish_system_event(EventType.KERNEL_START.value, {"started_at": self._iso_now()})

        self._agent_tasks = [
            asyncio.create_task(self._run_agent(agent_id), name=f"agent-{agent_id}")
            for agent_id in self.agents
        ]
        self._heartbeat_task = asyncio.create_task(self.heartbeat(), name="kernel-heartbeat")
        self._metrics_task = asyncio.create_task(self._broadcast_metrics_loop(), name="metrics-broadcast")

    async def shutdown(self) -> None:
        if not self.running:
            return
        self.running = False
        await self._publish_system_event(EventType.KERNEL_SHUTDOWN.value, {"stopped_at": self._iso_now()})

        tasks = [t for t in self._agent_tasks if not t.done()]
        if self._heartbeat_task and not self._heartbeat_task.done():
            tasks.append(self._heartbeat_task)
        if self._metrics_task and not self._metrics_task.done():
            tasks.append(self._metrics_task)

        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self._agent_tasks = []
        self._heartbeat_task = None
        self._metrics_task = None

    async def _broadcast_metrics_loop(self) -> None:
        """Periodically broadcast system metrics to all WS clients."""
        while self.running:
            await asyncio.sleep(2)
            metrics = self.get_metrics()
            msg = json.dumps({"type": "metrics", "data": metrics})
            dead = []
            for ws in list(self.event_bus._ws_clients):
                try:
                    await ws.send_text(msg)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.event_bus._ws_clients.discard(ws)

    def get_metrics(self) -> Dict[str, Any]:
        chief = self.agents["command"]
        return {
            "kernel": {
                "running": self.running,
                "heartbeat_count": self._heartbeat_count,
                "heartbeat_failures": self._heartbeat_failures,
                "events_routed": self._events_routed,
                "violations": self._violations,
                "event_queue_size": self.event_bus.qsize(),
                "total_events_logged": len(self.event_bus._event_log),
                "uptime_since": getattr(self, "_start_time", None),
            },
            "agents": {
                "recon": {
                    "status": "active" if self.running else "stopped",
                    "cycles": self.agents["recon"]._cycle_count,
                },
                "forge": {
                    "status": "active" if self.running else "stopped",
                    "cycles": self.agents["forge"]._cycle_count,
                },
                "command": {
                    "status": "active" if self.running else "stopped",
                    "approved": chief._approved,
                    "denied": chief._denied,
                },
            },
            "safeguards": self.safeguards.stats,
            "timestamp": self._iso_now(),
        }

    async def _route_event(self, event: Any) -> None:
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

    async def _process_external_action_pipeline(self, event: Any) -> None:
        async with self._external_pipeline_lock:
            request = self._event_to_dict(event)
            origin_id = self._event_origin(event)

            approval = await self.agents["command"].approve_external_action(event)
            if not bool(isinstance(approval, dict) and approval.get("approved")):
                result_payload = {"status": "denied_by_chief", "request": request, "approval": approval}
                await self.agents["command"].handle_external_action(result_payload)
                return

            safeguard_check = await self.safeguards.check_request(event, origin_id=origin_id)
            if not bool(safeguard_check.get("allowed")):
                await self.safeguards.record_attempt(event, origin_id=origin_id, success=False)
                self._violations += 1
                await self._publish_system_event(
                    self.CONSTITUTION_VIOLATION_EVENT,
                    {"reason": "Safeguard blocked external action.", "origin_id": origin_id},
                )
                result_payload = {"status": "blocked_by_safeguard", "request": request, "safeguard_check": safeguard_check}
                await self.agents["command"].handle_external_action(result_payload)
                return

            execution = await self.safeguards.execute_in_sandbox(event, origin_id=origin_id)
            await self.safeguards.record_attempt(event, origin_id=origin_id, success=bool(execution.get("success")))
            result_payload = {
                "status": "executed" if execution.get("success") else "execution_denied",
                "request": request,
                "execution": execution,
            }
            await self.agents["command"].handle_external_action(result_payload)

    async def _event_is_compliant(self, event: Any) -> bool:
        payload = self._event_payload(event)
        justification = payload.get("prime_directive_justification") if isinstance(payload, dict) else None
        if isinstance(justification, str) and justification.strip():
            return True
        self._violations += 1
        await self._publish_system_event(
            self.CONSTITUTION_VIOLATION_EVENT,
            {"reason": "Missing Prime Directive justification", "event_type": self._event_type_value(event)},
        )
        return False

    async def _publish_system_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        system_payload = dict(payload)
        system_payload.setdefault(
            "prime_directive_justification",
            "Kernel governance action preserves safe, continuous operation under the Prime Directive.",
        )
        event = {"type": event_type, "origin_id": "kernel", "timestamp": self._iso_now(), "payload": system_payload}
        await self.event_bus.publish(event)

    async def _run_agent(self, agent_id: str) -> None:
        agent = self.agents[agent_id]
        while self.running:
            try:
                await agent.run()
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(2)

    def _event_to_dict(self, event: Any) -> Dict[str, Any]:
        return event.to_dict() if hasattr(event, "to_dict") else dict(event)

    def _event_payload(self, event: Any) -> Dict[str, Any]:
        return self._event_to_dict(event).get("payload", {})

    def _event_type_value(self, event: Any) -> str:
        return str(self._event_to_dict(event).get("type", ""))

    def _event_origin(self, event: Any) -> str:
        return str(self._event_to_dict(event).get("origin_id", "unknown"))

    def _iso_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
