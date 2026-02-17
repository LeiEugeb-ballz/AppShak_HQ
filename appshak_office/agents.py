"""
Office Agents — Specialized agents with desks, working on their tasks.

Authority Hierarchy:
- Chief Agent (Level 3): Highest authority; approves/rejects/escalates proposals
- Builder Agent (Level 2): Estimates complexity and executes approved tasks
- Scout Agent (Level 1): Proposes problems and opportunities

All agents publish events to the shared bus; direct communication is prohibited.
"""
from __future__ import annotations

import asyncio
import random
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from appshak_office import NORTH_STARS
from appshak_office.event_bus import Event, EventType
from appshak_office.memory import AgentMemory, OrganizationalMemory


# ── Simulated problem/opportunity pools ──────────────────────────────────────

PROBLEMS = [
    {"domain": "e-commerce", "problem": "Cart abandonment rate at 72%", "severity": "high", "opportunity_value": 0.85},
    {"domain": "healthcare", "problem": "Patient wait-time tracking is manual", "severity": "medium", "opportunity_value": 0.7},
    {"domain": "logistics", "problem": "Last-mile delivery cost optimization needed", "severity": "high", "opportunity_value": 0.9},
    {"domain": "education", "problem": "Student engagement drops after 15 min in online lectures", "severity": "medium", "opportunity_value": 0.65},
    {"domain": "fintech", "problem": "KYC onboarding takes 3+ days average", "severity": "high", "opportunity_value": 0.88},
    {"domain": "agriculture", "problem": "Crop disease detection relies on visual inspection", "severity": "medium", "opportunity_value": 0.72},
    {"domain": "real-estate", "problem": "Property valuation models are outdated by 6 months", "severity": "low", "opportunity_value": 0.5},
    {"domain": "energy", "problem": "Solar panel output prediction accuracy is 68%", "severity": "high", "opportunity_value": 0.82},
    {"domain": "retail", "problem": "Inventory forecasting error rate at 23%", "severity": "medium", "opportunity_value": 0.68},
    {"domain": "transport", "problem": "Fleet route optimization saves only 8% fuel", "severity": "high", "opportunity_value": 0.78},
    {"domain": "manufacturing", "problem": "Predictive maintenance false positive rate at 35%", "severity": "high", "opportunity_value": 0.8},
    {"domain": "insurance", "problem": "Claims processing takes 14 days average", "severity": "medium", "opportunity_value": 0.75},
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
    "Implement computer vision classifier",
    "Deploy NLP document processor",
]

SKILLS = [
    "machine_learning", "data_engineering", "api_development", "frontend_design",
    "system_architecture", "nlp", "computer_vision", "optimization", "analytics",
]

WATER_COOLER_TOPICS = [
    "What's the most interesting problem you've seen lately?",
    "Any lessons learned from recent tasks?",
    "How's your confidence level on current projects?",
    "What skill would you like to develop next?",
    "Any patterns you've noticed across domains?",
    "What's working well in our collaboration?",
    "Any blockers we should escalate?",
    "Ideas for improving our workflow?",
]


class BaseAgent(ABC):
    """Base class for all office agents."""
    
    agent_id: Optional[str] = None
    authority_level: Optional[int] = None
    role_description: str = ""
    desk_position: Dict[str, int] = {"x": 0, "y": 0}
    
    def __init__(self, kernel: Any) -> None:
        self.kernel = kernel
        self.event_bus = kernel.event_bus
        self.org_memory: OrganizationalMemory = kernel.org_memory
        self._cycle_count = 0
        self._current_task: Optional[Dict[str, Any]] = None
        self._location = "desk"  # desk, water_cooler, boardroom
        self._status = "idle"
        self._last_activity = datetime.now(timezone.utc).isoformat()
    
    @property
    def memory(self) -> AgentMemory:
        return self.org_memory.get_agent_memory(self.agent_id)
    
    @abstractmethod
    async def run(self) -> None:
        """Main agent loop."""
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
        event_payload["north_star_alignment"] = random.choice(NORTH_STARS)
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
        return f"{action} advances the North Stars by {impact}"
    
    def move_to(self, location: str) -> None:
        self._location = location
        self._last_activity = datetime.now(timezone.utc).isoformat()
    
    def get_state(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "authority_level": self.authority_level,
            "role": self.role_description,
            "location": self._location,
            "status": self._status,
            "cycle_count": self._cycle_count,
            "current_task": self._current_task,
            "desk_position": self.desk_position,
            "memory_summary": {
                "confidence": self.memory.confidence_score,
                "success_rate": self.memory.success_rate,
                "skills": self.memory.skills,
                "autonomy_level": self.memory.autonomy_level,
            },
            "last_activity": self._last_activity,
        }
    
    async def participate_water_cooler(self, partner: "BaseAgent") -> Dict[str, Any]:
        """Participate in a water cooler exchange with another agent."""
        self.move_to("water_cooler")
        topic = random.choice(WATER_COOLER_TOPICS)
        
        # Generate a response based on agent's memory
        my_insight = self._generate_insight(topic)
        
        # Update relationship
        relationship = self.org_memory.get_relationship(self.agent_id, partner.agent_id)
        relationship.update_after_interaction(positive=True)
        
        # Record collaboration
        self.memory.record_collaboration(partner.agent_id, "water_cooler", 0.8)
        
        return {
            "topic": topic,
            "my_insight": my_insight,
            "partner": partner.agent_id,
        }
    
    def _generate_insight(self, topic: str) -> str:
        """Generate an insight based on agent's experience."""
        if "problem" in topic.lower():
            if self.memory.lessons_learned:
                lesson = random.choice(self.memory.lessons_learned)
                return f"Recently learned: {lesson.get('lesson', 'interesting patterns in data')}"
            return f"I've been exploring {random.choice([p['domain'] for p in PROBLEMS])} domain"
        
        if "skill" in topic.lower():
            if self.memory.skills:
                skill = max(self.memory.skills.items(), key=lambda x: x[1], default=("general", 0.5))
                return f"I'm strongest in {skill[0]} ({skill[1]:.0%} proficiency)"
            return f"I'd like to develop {random.choice(SKILLS)}"
        
        if "confidence" in topic.lower():
            return f"My confidence is at {self.memory.confidence_score:.0%}, success rate {self.memory.success_rate:.0%}"
        
        return f"Interesting perspective on {topic.split()[0].lower()}"
    
    async def participate_boardroom(self, agenda: Dict[str, Any]) -> Dict[str, Any]:
        """Participate in a boardroom session."""
        self.move_to("boardroom")
        
        agenda_type = agenda.get("type", "discussion")
        
        if agenda_type == "project_launch":
            return await self._boardroom_project_launch(agenda)
        elif agenda_type == "upskill":
            return await self._boardroom_upskill(agenda)
        else:
            return await self._boardroom_discussion(agenda)
    
    async def _boardroom_discussion(self, agenda: Dict[str, Any]) -> Dict[str, Any]:
        topic = agenda.get("topic", "general progress")
        return {
            "contribution": f"{self.agent_id} perspective on {topic}",
            "vote": random.choice(["approve", "approve", "abstain", "reject"]),
            "confidence": self.memory.confidence_score,
        }
    
    async def _boardroom_project_launch(self, agenda: Dict[str, Any]) -> Dict[str, Any]:
        project = agenda.get("project", {})
        return {
            "commitment": "ready" if self.memory.confidence_score > 0.4 else "cautious",
            "estimated_contribution": random.choice(["lead", "support", "review"]),
            "skills_offered": list(self.memory.skills.keys())[:3] if self.memory.skills else [random.choice(SKILLS)],
        }
    
    async def _boardroom_upskill(self, agenda: Dict[str, Any]) -> Dict[str, Any]:
        skill = agenda.get("skill", random.choice(SKILLS))
        # Learn the skill
        self.memory.update_skill(skill, random.uniform(0.05, 0.15))
        return {
            "skill_learned": skill,
            "new_proficiency": self.memory.skills.get(skill, 0.1),
            "insight_shared": f"Key insight about {skill}: {random.choice(['patterns', 'best practices', 'common pitfalls'])}",
        }


class ScoutAgent(BaseAgent):
    """Level 1: Discovery-only — scans domains for real-world problems."""
    
    agent_id = "scout"
    authority_level = 1
    role_description = "Discovery Agent — Proposes problems and opportunities"
    desk_position = {"x": 100, "y": 200}
    
    def __init__(self, kernel: Any) -> None:
        super().__init__(kernel)
        self._domains_scanned: List[str] = []
    
    async def run(self) -> None:
        while self.kernel.running:
            await asyncio.sleep(random.uniform(4, 8))
            if not self.kernel.running:
                break
            await self.search_for_problems()
    
    async def search_for_problems(self) -> None:
        self._cycle_count += 1
        self._status = "scanning"
        self.move_to("desk")
        
        problem = random.choice(PROBLEMS)
        self._domains_scanned.append(problem["domain"])
        
        # Record domain in organizational memory
        self.org_memory.record_domain(problem["domain"], {
            "last_scanned": datetime.now(timezone.utc).isoformat(),
            "problems_found": 1,
        })
        
        # Emit scanning status
        status_event = self.build_event(
            EventType.AGENT_STATUS,
            {
                "action": "scanning",
                "status": "active_scan",
                "agent": self.agent_id,
                "cycle": self._cycle_count,
                "scanning_domain": problem["domain"],
                "location": self._location,
            },
            justification=self.justify_action("domain_scan", f"discovering opportunities in {problem['domain']}"),
        )
        await self.publish(status_event)
        
        await asyncio.sleep(random.uniform(1, 2))
        
        # Emit discovered problem
        confidence = round(random.uniform(0.6, 0.98), 2)
        discovery_event = self.build_event(
            EventType.PROBLEM_DISCOVERED,
            {
                "action": "problem_discovered",
                "problem": problem,
                "confidence": confidence,
                "cycle": self._cycle_count,
                "domains_scanned_total": len(set(self._domains_scanned)),
            },
            justification=self.justify_action("problem_discovery", f"identifying: {problem['problem']}"),
        )
        await self.publish(discovery_event)
        
        # Update memory
        self.memory.update_skill("problem_discovery", 0.01)
        self.memory.add_lesson(f"Found {problem['severity']} severity issue in {problem['domain']}", problem)
        self.org_memory.global_metrics["total_problems_discovered"] += 1
        
        self._status = "idle"
        self._last_activity = datetime.now(timezone.utc).isoformat()


class BuilderAgent(BaseAgent):
    """Level 2: Converts discovered problems into proposals and executes approved tasks."""
    
    agent_id = "builder"
    authority_level = 2
    role_description = "Builder Agent — Estimates complexity and executes approved tasks"
    desk_position = {"x": 400, "y": 200}
    
    def __init__(self, kernel: Any) -> None:
        super().__init__(kernel)
        self._plans_created = 0
        self._tasks_executed = 0
    
    async def run(self) -> None:
        while self.kernel.running:
            await asyncio.sleep(random.uniform(6, 12))
            if not self.kernel.running:
                break
            await self._work_cycle()
    
    async def _work_cycle(self) -> None:
        self._cycle_count += 1
        self._status = "planning"
        self.move_to("desk")
        
        problem = random.choice(PROBLEMS)
        solution = random.choice(SOLUTIONS)
        
        # Create a plan
        self._plans_created += 1
        complexity = random.choice(["low", "medium", "high"])
        estimated_hours = {"low": 4, "medium": 16, "high": 40}[complexity]
        
        plan_event = self.build_event(
            EventType.PLAN_CREATED,
            {
                "action": "create_plan",
                "plan_id": f"plan-{self._plans_created:04d}",
                "problem": problem,
                "solution": solution,
                "complexity": complexity,
                "estimated_hours": estimated_hours,
                "steps": [
                    "validate_inputs",
                    "design_architecture",
                    "implement_core_logic",
                    "test_and_validate",
                    "prepare_deployment",
                ],
                "skills_required": random.sample(SKILLS, k=min(3, len(SKILLS))),
            },
            justification=self.justify_action("plan_creation", f"constructing solution: {solution}"),
        )
        await self.publish(plan_event)
        
        await asyncio.sleep(random.uniform(2, 4))
        
        # Submit as proposal
        proposal_event = self.build_event(
            EventType.PROPOSAL,
            {
                "action": solution,
                "plan_id": f"plan-{self._plans_created:04d}",
                "domain": problem["domain"],
                "problem_summary": problem["problem"],
                "complexity": complexity,
                "estimated_hours": estimated_hours,
                "opportunity_value": problem.get("opportunity_value", 0.5),
            },
            justification=self.justify_action("submit_proposal", f"proposing {solution} for {problem['domain']}"),
        )
        await self.publish(proposal_event)
        
        # Update memory
        self.memory.update_skill("solution_design", 0.01)
        self.memory.update_skill(random.choice(SKILLS), 0.005)
        
        self._status = "idle"
        self._last_activity = datetime.now(timezone.utc).isoformat()
    
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an approved task."""
        self._status = "executing"
        self._current_task = task
        self._tasks_executed += 1
        
        # Simulate execution time based on complexity
        complexity = task.get("complexity", "medium")
        exec_time = {"low": 2, "medium": 4, "high": 6}.get(complexity, 3)
        await asyncio.sleep(exec_time)
        
        # Determine success based on skills and confidence
        success_chance = 0.6 + (self.memory.confidence_score * 0.3)
        success = random.random() < success_chance
        
        self.memory.record_task_outcome(success)
        self.org_memory.global_metrics["total_tasks_completed"] += 1
        
        self._current_task = None
        self._status = "idle"
        
        return {
            "task_id": task.get("plan_id", "unknown"),
            "success": success,
            "execution_time": exec_time,
            "outcome": "completed" if success else "failed",
        }


class ChiefAgent(BaseAgent):
    """Level 3: Sole authority — arbitrates proposals, approves/denies external actions."""
    
    agent_id = "chief"
    authority_level = 3
    role_description = "Chief Agent — Highest authority; approves/rejects/escalates proposals"
    desk_position = {"x": 250, "y": 100}
    
    def __init__(self, kernel: Any) -> None:
        super().__init__(kernel)
        self._approved = 0
        self._denied = 0
        self._escalated = 0
    
    async def run(self) -> None:
        while self.kernel.running:
            await asyncio.sleep(0.5)
    
    async def arbitrate(self, event: Any) -> Dict[str, Any]:
        """Arbitrate a proposal using weighted consensus logic."""
        self._cycle_count += 1
        self._status = "arbitrating"
        self.move_to("desk")
        
        payload = self._extract_payload(event)
        proposal_action = payload.get("action")
        opportunity_value = payload.get("opportunity_value", 0.5)
        complexity = payload.get("complexity", "medium")
        
        # Decision factors
        complexity_penalty = {"low": 0, "medium": 0.1, "high": 0.25}.get(complexity, 0.1)
        confidence_bonus = self.memory.confidence_score * 0.2
        
        # Calculate approval probability
        approval_prob = 0.5 + opportunity_value * 0.3 - complexity_penalty + confidence_bonus
        approved = bool(proposal_action) and random.random() < approval_prob
        
        if approved:
            self._approved += 1
            self.org_memory.global_metrics["total_proposals_approved"] += 1
            decision_reason = f"Approved: '{proposal_action}' — high opportunity value ({opportunity_value:.0%}), acceptable complexity"
        else:
            self._denied += 1
            self.org_memory.global_metrics["total_proposals_denied"] += 1
            decision_reason = f"Denied: '{proposal_action}' — insufficient strategic alignment or resource constraints"
        
        self.memory.record_task_outcome(True)  # Chief always succeeds at arbitration
        self._status = "idle"
        self._last_activity = datetime.now(timezone.utc).isoformat()
        
        return {
            "type": EventType.PROPOSAL_DECISION,
            "origin_id": self.agent_id,
            "payload": {
                "action": "arbitrate_proposal",
                "proposal": event.to_dict() if hasattr(event, "to_dict") else event,
                "approved": approved,
                "decision_reason": decision_reason,
                "stats": {"approved": self._approved, "denied": self._denied, "escalated": self._escalated},
                "prime_directive_justification": self.justify_action(
                    "arbitrate_proposal",
                    "maintaining centralized control while advancing safe, continuous execution.",
                ),
            },
        }
    
    async def convene_boardroom(self, agenda: Dict[str, Any]) -> None:
        """Convene a boardroom session."""
        self._status = "convening_boardroom"
        self.move_to("boardroom")
        
        convene_event = self.build_event(
            EventType.BOARDROOM_CONVENE,
            {
                "action": "convene_boardroom",
                "agenda": agenda,
                "convened_by": self.agent_id,
            },
            justification=self.justify_action("boardroom_convene", "facilitating collective decision-making"),
        )
        await self.publish(convene_event)
    
    async def adjourn_boardroom(self, decisions: List[Dict[str, Any]]) -> None:
        """Adjourn a boardroom session."""
        adjourn_event = self.build_event(
            EventType.BOARDROOM_ADJOURN,
            {
                "action": "adjourn_boardroom",
                "decisions": decisions,
                "adjourned_by": self.agent_id,
            },
            justification=self.justify_action("boardroom_adjourn", "concluding collective session"),
        )
        await self.publish(adjourn_event)
        self._status = "idle"
        self.move_to("desk")
    
    @staticmethod
    def _extract_payload(event: Any) -> Dict[str, Any]:
        if isinstance(event, dict):
            payload = event.get("payload", {})
            return payload if isinstance(payload, dict) else {}
        payload = getattr(event, "payload", {})
        return payload if isinstance(payload, dict) else {}
