from __future__ import annotations

import asyncio

from appshak.agents.base import BaseAgent
from appshak.event_bus import EventType


class ScoutAgent(BaseAgent):
    """Level 1: discovery-only role. Execution is explicitly forbidden."""

    agent_id = "recon"
    authority_level = 1

    async def run(self) -> None:
        while self.kernel.running:
            await asyncio.sleep(0.25)

    async def search_for_problems(self) -> None:
        event = self.build_event(
            EventType.AGENT_STATUS,
            {
                "action": "search_for_problems",
                "status": "idle_scan_complete",
                "agent": self.agent_id,
            },
            justification=self.justify_action(
                "search_for_problems",
                "continuously discovering valuable real-world opportunities to solve.",
            ),
        )
        await self.publish(event)

    async def attempt_execution(self, *_: object, **__: object) -> None:
        raise PermissionError("ScoutAgent is discovery-only and cannot execute actions.")
