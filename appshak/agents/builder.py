from __future__ import annotations

import asyncio
from typing import Any, Dict

from appshak.agents.base import BaseAgent
from appshak.event_bus import EventType


class BuilderAgent(BaseAgent):
    """Level 2: convert approved proposals into executable request plans."""

    agent_id = "forge"
    authority_level = 2

    async def run(self) -> None:
        while self.kernel.running:
            await asyncio.sleep(0.25)

    async def translate_proposal_to_plan(self, proposal_event: Any) -> Dict[str, Any]:
        proposal = proposal_event.to_dict() if hasattr(proposal_event, "to_dict") else proposal_event
        payload = proposal.get("payload", {}) if isinstance(proposal, dict) else {}
        target_action = payload.get("action", "unspecified_action")
        return {
            "plan_id": f"plan:{target_action}",
            "source_event_type": EventType.PROPOSAL.value,
            "target_action": target_action,
            "steps": [
                "validate_inputs",
                "prepare_external_request_payload",
                "submit_external_action_request",
            ],
        }

    async def prepare_external_action_request(self, plan: Dict[str, Any]) -> None:
        event = self.build_event(
            EventType.EXTERNAL_ACTION_REQUEST,
            {
                "action": plan.get("target_action", "unspecified_action"),
                "plan": plan,
            },
            justification=self.justify_action(
                "prepare_external_action_request",
                "converting approved solutions into controlled requests for chief review.",
            ),
        )
        await self.publish(event)
