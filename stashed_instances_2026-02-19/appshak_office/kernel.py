"""
Office Kernel — Root orchestrator for the AppShak Office.

Implements the autonomy loop (10-30 second heartbeat):
1. Check queue
2. If empty, Scout searches
3. Chief reviews proposals
4. Builder executes if approved
5. Log/update memory
6. Adjust metrics
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from appshak_office.agents import BuilderAgent, ChiefAgent, ScoutAgent
from appshak_office.event_bus import EventBus, EventType
from appshak_office.memory import OrganizationalMemory
from appshak_office.office import Boardroom, WaterCooler


class OfficeKernel:
    """Root orchestrator — owns lifecycle, heartbeat, and office spaces."""
    
    PRIME_DIRECTIVE = (
        "AppShak exists to continuously identify valuable problems, build solutions, "
        "and increase its own capability and autonomy over time."
    )
    
    PROPOSAL_EVENT = EventType.PROPOSAL.value
    EXTERNAL_ACTION_REQUEST_EVENT = EventType.EXTERNAL_ACTION_REQUEST.value
    CONSTITUTION_VIOLATION_EVENT = EventType.CONSTITUTION_VIOLATION.value
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.running = False
        self.heartbeat_interval = float(config.get("heartbeat_interval", 15))
        self.idle_poll_timeout = float(config.get("event_poll_timeout", 1.0))
        
        # Core components
        self.event_bus = EventBus()
        self.org_memory = OrganizationalMemory(config.get("storage_root", "appshak_office_state"))
        
        # Agents
        self.agents = {
            "scout": ScoutAgent(self),
            "builder": BuilderAgent(self),
            "chief": ChiefAgent(self),
        }
        
        # Office spaces
        self.water_cooler = WaterCooler(self)
        self.boardroom = Boardroom(self)
        
        # Task management
        self._agent_tasks: List[asyncio.Task[Any]] = []
        self._heartbeat_task: Optional[asyncio.Task[Any]] = None
        self._metrics_task: Optional[asyncio.Task[Any]] = None
        self._water_cooler_task: Optional[asyncio.Task[Any]] = None
        self._boardroom_task: Optional[asyncio.Task[Any]] = None
        self._persist_task: Optional[asyncio.Task[Any]] = None
        
        # Metrics
        self._heartbeat_count = 0
        self._heartbeat_failures = 0
        self._events_routed = 0
        self._violations = 0
        self._start_time: Optional[str] = None
    
    async def heartbeat(self) -> None:
        """
        Kernel autonomy loop (10-30 second heartbeat):
        - Check queue
        - If empty, Scout searches
        - Chief reviews proposals
        - Builder executes if approved
        - Log/update memory
        """
        while self.running:
            try:
                self._heartbeat_count += 1
                event = await self.event_bus.get_next(timeout=self.idle_poll_timeout)
                
                if event is None:
                    # Idle — Scout searches for problems
                    await self.agents["scout"].search_for_problems()
                else:
                    self._events_routed += 1
                    await self._route_event(event)
                
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._heartbeat_failures += 1
                self.org_memory.log_event("KERNEL_ERROR", {"error": str(exc)})
            
            await asyncio.sleep(self.heartbeat_interval)
    
    async def start(self) -> None:
        """Start the office — all agents, spaces, and loops."""
        if self.running:
            return
        
        # Initialize memory
        await self.org_memory.initialize()
        
        self.running = True
        self._start_time = datetime.now(timezone.utc).isoformat()
        
        # Emit start event
        await self._publish_system_event(
            EventType.KERNEL_START.value,
            {"started_at": self._start_time, "config": self.config},
        )
        
        # Start agent tasks
        self._agent_tasks = [
            asyncio.create_task(self._run_agent(agent_id), name=f"agent-{agent_id}")
            for agent_id in self.agents
        ]
        
        # Start heartbeat
        self._heartbeat_task = asyncio.create_task(self.heartbeat(), name="kernel-heartbeat")
        
        # Start metrics broadcast
        self._metrics_task = asyncio.create_task(self._broadcast_metrics_loop(), name="metrics-broadcast")
        
        # Start office spaces
        self._water_cooler_task = asyncio.create_task(self.water_cooler.run(), name="water-cooler")
        self._boardroom_task = asyncio.create_task(self.boardroom.run(), name="boardroom")
        
        # Start periodic persistence
        self._persist_task = asyncio.create_task(self._persist_loop(), name="persist-loop")
    
    async def shutdown(self) -> None:
        """Shutdown the office gracefully."""
        if not self.running:
            return
        
        self.running = False
        self.water_cooler.stop()
        self.boardroom.stop()
        
        await self._publish_system_event(
            EventType.KERNEL_SHUTDOWN.value,
            {"stopped_at": datetime.now(timezone.utc).isoformat()},
        )
        
        # Persist final state
        await self.org_memory.persist()
        
        # Cancel all tasks
        tasks = [t for t in self._agent_tasks if not t.done()]
        for task in [self._heartbeat_task, self._metrics_task, self._water_cooler_task, self._boardroom_task, self._persist_task]:
            if task and not task.done():
                tasks.append(task)
        
        for task in tasks:
            task.cancel()
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        self._agent_tasks = []
        self._heartbeat_task = None
        self._metrics_task = None
        self._water_cooler_task = None
        self._boardroom_task = None
        self._persist_task = None
    
    async def _route_event(self, event: Any) -> None:
        """Route events to appropriate handlers."""
        if not await self._event_is_compliant(event):
            return
        
        event_type = self._event_type_value(event)
        
        # Log to organizational memory
        self.org_memory.log_event(event_type, self._event_to_dict(event))
        
        if event_type == self.PROPOSAL_EVENT:
            # Chief arbitrates proposals
            decision = await self.agents["chief"].arbitrate(event)
            if decision is not None:
                await self.event_bus.publish(decision)
                
                # If approved, assign to builder
                if decision.get("payload", {}).get("approved"):
                    await self._assign_task_to_builder(event)
    
    async def _assign_task_to_builder(self, proposal_event: Any) -> None:
        """Assign an approved proposal to the builder."""
        payload = self._event_payload(proposal_event)
        
        task_event = {
            "type": EventType.TASK_ASSIGNED,
            "origin_id": "kernel",
            "payload": {
                "action": "task_assigned",
                "task": payload,
                "assigned_to": "builder",
                "assigned_at": datetime.now(timezone.utc).isoformat(),
                "prime_directive_justification": "Assigning approved task for execution",
            },
        }
        await self.event_bus.publish(task_event)
        
        # Execute task
        result = await self.agents["builder"].execute_task(payload)
        
        # Emit completion event
        complete_event = {
            "type": EventType.TASK_COMPLETE,
            "origin_id": "builder",
            "payload": {
                "action": "task_complete",
                "result": result,
                "prime_directive_justification": "Task execution completed",
            },
        }
        await self.event_bus.publish(complete_event)
    
    async def _event_is_compliant(self, event: Any) -> bool:
        """Check if event has required Prime Directive justification."""
        payload = self._event_payload(event)
        justification = payload.get("prime_directive_justification") if isinstance(payload, dict) else None
        
        if isinstance(justification, str) and justification.strip():
            return True
        
        self._violations += 1
        await self._publish_system_event(
            self.CONSTITUTION_VIOLATION_EVENT,
            {
                "reason": "Missing Prime Directive justification",
                "event_type": self._event_type_value(event),
            },
        )
        return False
    
    async def _publish_system_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        system_payload = dict(payload)
        system_payload.setdefault(
            "prime_directive_justification",
            "Kernel governance action preserves safe, continuous operation.",
        )
        event = {
            "type": event_type,
            "origin_id": "kernel",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": system_payload,
        }
        await self.event_bus.publish(event)
    
    async def _run_agent(self, agent_id: str) -> None:
        """Run an agent with auto-restart on crash."""
        agent = self.agents[agent_id]
        while self.running:
            try:
                await agent.run()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.org_memory.log_event("AGENT_ERROR", {"agent": agent_id, "error": str(exc)})
                await asyncio.sleep(2)
    
    async def _broadcast_metrics_loop(self) -> None:
        """Periodically broadcast metrics to WebSocket clients."""
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
    
    async def _persist_loop(self) -> None:
        """Periodically persist organizational memory."""
        while self.running:
            await asyncio.sleep(30)
            await self.org_memory.persist()
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive system metrics."""
        return {
            "kernel": {
                "running": self.running,
                "heartbeat_count": self._heartbeat_count,
                "heartbeat_failures": self._heartbeat_failures,
                "events_routed": self._events_routed,
                "violations": self._violations,
                "event_queue_size": self.event_bus.qsize(),
                "total_events_logged": len(self.event_bus._event_log),
                "start_time": self._start_time,
            },
            "agents": {
                agent_id: agent.get_state()
                for agent_id, agent in self.agents.items()
            },
            "office": {
                "water_cooler": self.water_cooler.get_state(),
                "boardroom": self.boardroom.get_state(),
            },
            "memory": self.org_memory.get_metrics_summary(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    
    def _event_to_dict(self, event: Any) -> Dict[str, Any]:
        return event.to_dict() if hasattr(event, "to_dict") else dict(event)
    
    def _event_payload(self, event: Any) -> Dict[str, Any]:
        return self._event_to_dict(event).get("payload", {})
    
    def _event_type_value(self, event: Any) -> str:
        return str(self._event_to_dict(event).get("type", ""))
