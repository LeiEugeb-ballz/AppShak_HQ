"""Live agents with simulated autonomous behavior."""
from __future__ import annotations

import asyncio
import random
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union

from appshak_live.event_bus import Event, EventType


# ── Simulated problem/opportunity pools ──────────────────────────────────────

PROBLEMS = [
    {"domain": "e-commerce", "problem": "Cart abandonment rate at 72%", "severity": "high"},
    {"domain": "healthcare", "problem": "Patient wait-time tracking is manual", "severity": "medium"},
    {"domain": "logistics", "problem": "Last-mile delivery cost optimization needed", "severity": "high"},
    {"domain": "education", "problem": "Student engagement drops after 15 min in online lectures", "severity": "medium"},
    {"domain": "fintech", "problem": "KYC onboarding takes 3+ days average", "severity": "high"},
    {"domain": "agriculture", "problem": "Crop disease detection relies on visual inspection", "severity": "medium"},
    {"domain": "real-estate", "problem": "Property valuation models are outdated by 6 months", "severity": "low"},
    {"domain": "energy", "problem": "Solar panel output prediction accuracy is 68%", "severity": "high"},
    {"domain": "retail", "problem": "Inventory forecasting error rate at 23%", "severity": "medium"},
    {"domain": "transport", "problem": "Fleet route optimization saves only 8% fuel", "severity": "high"},
]

SOLUTIONS = [
    "Build ML-powered prediction API",
    "Deploy real-time monitoring dashboard",
    "Create automated data pipeline",
    "Implement recommendation engine",
    "Build conversational AI assistant",
    "Deploy anomaly detection system",
    "Create optimization microservice",
    "Build automated reporting tool",
]

ENDPOINTS = [
    "https://api.appshak.io/v1/deploy",
    "https://api.appshak.io/v1/analyze",
    "https://api.appshak.io/v1/monitor",
    "https://api.appshak.io/v1/predict",
]


class BaseAgent(ABC):
    agent_id: Optional[str] = None
    authority_level: Optional[int] = None

    def __init__(self, kernel: Any) -> None:
        self.kernel = kernel
        self.event_bus = kernel.event_bus
        self.prime_directive = kernel.PRIME_DIRECTIVE
        self._cycle_count = 0

    @abstractmethod
    async def run(self) -> None:
        pass

    async def publish(self, event: Union[Event, Dict[str, Any]]) -> Event:
        return await self.event_bus.publish(event)

    def build_event(
        self,
        event_type: Union[EventType, str],
        payload: Optional[Dict[str, Any]] = None,
        *,
        justification: Optional[str] = None,
    ) -> Event:
        event_payload = dict(payload or {})
        event_payload["prime_directive_justification"] = (
            justification
            or event_payload.get("prime_directive_justification")
            or self.justify_action("autonomous_action", "advancing operational continuity")
        )
        normalized_type = event_type if isinstance(event_type, EventType) else EventType(str(event_type))
        return Event(
            type=normalized_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            origin_id=self.agent_id or "unknown_agent",
            payload=event_payload,
        )

    def justify_action(self, action: str, impact: str) -> str:
        return f"{action} advances the Prime Directive by {impact}"


class ScoutAgent(BaseAgent):
    """Level 1: Autonomous problem discovery — scans and reports opportunities."""

    agent_id = "recon"
    authority_level = 1

    async def run(self) -> None:
        while self.kernel.running:
            await asyncio.sleep(random.uniform(3, 7))
            if not self.kernel.running:
                break
            await self.search_for_problems()

    async def search_for_problems(self) -> None:
        self._cycle_count += 1
        problem = random.choice(PROBLEMS)

        # First emit a status event
        status_event = self.build_event(
            EventType.AGENT_STATUS,
            {
                "action": "scanning",
                "status": "active_scan",
                "agent": self.agent_id,
                "cycle": self._cycle_count,
                "scanning_domain": problem["domain"],
            },
            justification=self.justify_action(
                "domain_scan", f"discovering opportunities in {problem['domain']}"
            ),
        )
        await self.publish(status_event)

        await asyncio.sleep(random.uniform(1, 2))

        # Then emit the discovered problem
        discovery_event = self.build_event(
            EventType.PROBLEM_DISCOVERED,
            {
                "action": "problem_discovered",
                "problem": problem,
                "confidence": round(random.uniform(0.6, 0.98), 2),
                "cycle": self._cycle_count,
            },
            justification=self.justify_action(
                "problem_discovery",
                f"identifying real-world problem: {problem['problem']}",
            ),
        )
        await self.publish(discovery_event)


class BuilderAgent(BaseAgent):
    """Level 2: Converts discovered problems into proposals and action plans."""

    agent_id = "forge"
    authority_level = 2

    async def run(self) -> None:
        while self.kernel.running:
            await asyncio.sleep(random.uniform(5, 10))
            if not self.kernel.running:
                break
            await self._check_for_work()

    async def _check_for_work(self) -> None:
        self._cycle_count += 1
        problem = random.choice(PROBLEMS)
        solution = random.choice(SOLUTIONS)

        # Emit plan creation
        plan_event = self.build_event(
            EventType.PLAN_CREATED,
            {
                "action": "create_plan",
                "plan_id": f"plan-{self._cycle_count:04d}",
                "problem": problem,
                "solution": solution,
                "steps": [
                    "validate_inputs",
                    "prepare_external_request_payload",
                    "submit_external_action_request",
                ],
                "estimated_impact": random.choice(["high", "medium", "low"]),
            },
            justification=self.justify_action(
                "plan_creation",
                f"constructing solution: {solution} for {problem['domain']}",
            ),
        )
        await self.publish(plan_event)

        await asyncio.sleep(random.uniform(1, 3))

        # Submit as proposal
        proposal_event = self.build_event(
            EventType.PROPOSAL,
            {
                "action": solution,
                "plan_id": f"plan-{self._cycle_count:04d}",
                "domain": problem["domain"],
                "problem_summary": problem["problem"],
                "endpoint": random.choice(ENDPOINTS),
            },
            justification=self.justify_action(
                "submit_proposal",
                f"proposing {solution} to address {problem['problem']}",
            ),
        )
        await self.publish(proposal_event)


class ChiefAgent(BaseAgent):
    """Level 3: Sole authority — arbitrates proposals, approves/denies external actions."""

    agent_id = "command"
    authority_level = 3

    def __init__(self, kernel: Any) -> None:
        super().__init__(kernel)
        self._approved = 0
        self._denied = 0

    async def run(self) -> None:
        while self.kernel.running:
            await asyncio.sleep(0.25)

    async def arbitrate(self, event: Any) -> Dict[str, Any]:
        payload = self._extract_payload(event)
        proposal_action = payload.get("action")
        # Simulate decision-making with weighted approval
        approved = bool(proposal_action) and random.random() < 0.7

        if approved:
            self._approved += 1
        else:
            self._denied += 1

        decision_reason = (
            f"Approved: '{proposal_action}' aligns with Prime Directive. ({self._approved} approved total)"
            if approved
            else f"Denied: '{proposal_action}' — insufficient strategic alignment or resource constraints. ({self._denied} denied total)"
        )
        return {
            "type": EventType.PROPOSAL_DECISION,
            "origin_id": self.agent_id,
            "payload": {
                "action": "arbitrate_proposal",
                "proposal": event.to_dict() if hasattr(event, "to_dict") else event,
                "approved": approved,
                "decision_reason": decision_reason,
                "stats": {"approved": self._approved, "denied": self._denied},
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
                "enforcing final authority over external actions.",
            ),
        )
        await self.publish(decision_event)

    async def approve_external_action(self, event: Any) -> Dict[str, Any]:
        payload = self._extract_payload(event)
        action = payload.get("action")
        endpoint = payload.get("endpoint") or payload.get("url")
        has_justification = bool(
            isinstance(payload.get("prime_directive_justification"), str)
            and payload["prime_directive_justification"].strip()
        )
        approved = bool(action and endpoint and has_justification) and random.random() < 0.6
        reason = (
            "Approved: explicit action/endpoint with Prime Directive justification."
            if approved
            else "Denied: missing requirements or strategic review failed."
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
