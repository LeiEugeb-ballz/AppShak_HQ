from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict

from appshak.agents.base import BaseAgent
from appshak.event_bus import EventType


class ChiefAgent(BaseAgent):
    """Level 3: sole authority for external actions and final decisions."""

    agent_id = "command"
    authority_level = 3

    async def run(self) -> None:
        while self.kernel.running:
            await asyncio.sleep(0.25)

    async def arbitrate(self, event: Any) -> Dict[str, Any]:
        payload = self._extract_payload(event)
        proposal_action = payload.get("action")
        approved = bool(proposal_action)
        decision_reason = (
            "Approved proposal: action is defined and reviewable."
            if approved
            else "Denied proposal: missing actionable proposal content."
        )
        return {
            "type": EventType.PROPOSAL_DECISION,
            "origin_id": self.agent_id,
            "payload": {
                "action": "arbitrate_proposal",
                "proposal": event.to_dict() if hasattr(event, "to_dict") else event,
                "approved": approved,
                "decision_reason": decision_reason,
                "prime_directive_justification": self.justify_action(
                    "arbitrate_proposal",
                    "maintaining centralized control while advancing safe, continuous execution.",
                ),
            },
        }

    async def handle_external_action(self, event: Any) -> None:
        payload = event if isinstance(event, dict) else self._extract_payload(event)
        decision_event = self.build_event(
            EventType.EXTERNAL_ACTION_RESULT,
            {
                "action": "chief_external_decision",
                "result": payload,
                "decided_by": self.agent_id,
            },
            justification=self.justify_action(
                "chief_external_decision",
                "enforcing final authority over external actions with explicit constitutional rationale.",
            ),
        )
        await self.publish(decision_event)

    async def approve_external_action(self, event: Any) -> Dict[str, Any]:
        payload = self._extract_payload(event)
        action = payload.get("action")
        endpoint = payload.get("endpoint") or payload.get("url")
        has_justification = bool(
            isinstance(payload.get("prime_directive_justification"), str)
            and payload.get("prime_directive_justification").strip()
        )

        approved = bool(action and endpoint and has_justification)
        reason = (
            "Approved: explicit action/endpoint with Prime Directive justification."
            if approved
            else "Denied: missing action, endpoint, or Prime Directive justification."
        )

        return {
            "approved": approved,
            "reason": reason,
            "reviewed_by": self.agent_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "prime_directive_justification": self.justify_action(
                "approve_external_action",
                "preserving centralized authority and safe external governance.",
            ),
        }

    @staticmethod
    def _extract_payload(event: Any) -> Dict[str, Any]:
        if isinstance(event, dict):
            payload = event.get("payload", {})
            return payload if isinstance(payload, dict) else {}
        payload = getattr(event, "payload", {})
        return payload if isinstance(payload, dict) else {}
