"""
Office Spaces — Water Cooler and Boardroom implementations.

Water Cooler: Random idle agent pairs sharing summaries/questions (every 20-40 min)
Boardroom: All agents come together for project discussions, launches, upskills
"""
from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, TYPE_CHECKING

from appshak_office.event_bus import EventType

if TYPE_CHECKING:
    from appshak_office.agents import BaseAgent
    from appshak_office.kernel import OfficeKernel


class WaterCooler:
    """
    Water Cooler — Random idle agent pairs sharing summaries/questions.
    Activates every 20-40 minutes after system stability.
    """
    
    def __init__(self, kernel: "OfficeKernel"):
        self.kernel = kernel
        self.exchange_count = 0
        self.last_exchange: str | None = None
        self._running = False
        self._min_interval = 60  # 1 minute for demo (spec says 20-40 min)
        self._max_interval = 120  # 2 minutes for demo
    
    async def run(self) -> None:
        """Main water cooler loop."""
        self._running = True
        # Wait for initial stability
        await asyncio.sleep(30)
        
        while self._running and self.kernel.running:
            interval = random.uniform(self._min_interval, self._max_interval)
            await asyncio.sleep(interval)
            
            if not self.kernel.running:
                break
            
            await self.initiate_exchange()
    
    async def initiate_exchange(self) -> None:
        """Initiate a water cooler exchange between two random agents."""
        agents = list(self.kernel.agents.values())
        if len(agents) < 2:
            return
        
        # Pick two random agents
        pair = random.sample(agents, 2)
        agent_a, agent_b = pair
        
        self.exchange_count += 1
        self.last_exchange = datetime.now(timezone.utc).isoformat()
        
        # Emit start event
        start_event = {
            "type": EventType.WATER_COOLER_START,
            "origin_id": "water_cooler",
            "payload": {
                "action": "water_cooler_start",
                "participants": [agent_a.agent_id, agent_b.agent_id],
                "exchange_number": self.exchange_count,
                "prime_directive_justification": "Fostering knowledge propagation and relationship building",
            },
        }
        await self.kernel.event_bus.publish(start_event)
        
        # Move agents to water cooler
        agent_a.move_to("water_cooler")
        agent_b.move_to("water_cooler")
        
        # Conduct exchange
        exchange_a = await agent_a.participate_water_cooler(agent_b)
        exchange_b = await agent_b.participate_water_cooler(agent_a)
        
        # Emit exchange event
        exchange_event = {
            "type": EventType.WATER_COOLER_EXCHANGE,
            "origin_id": "water_cooler",
            "payload": {
                "action": "water_cooler_exchange",
                "exchange_number": self.exchange_count,
                "topic": exchange_a["topic"],
                "exchanges": [
                    {"agent": agent_a.agent_id, "insight": exchange_a["my_insight"]},
                    {"agent": agent_b.agent_id, "insight": exchange_b["my_insight"]},
                ],
                "relationship_updated": True,
                "prime_directive_justification": "Sharing knowledge and strengthening collaboration",
            },
        }
        await self.kernel.event_bus.publish(exchange_event)
        
        await asyncio.sleep(3)  # Exchange duration
        
        # Emit end event
        end_event = {
            "type": EventType.WATER_COOLER_END,
            "origin_id": "water_cooler",
            "payload": {
                "action": "water_cooler_end",
                "participants": [agent_a.agent_id, agent_b.agent_id],
                "exchange_number": self.exchange_count,
                "prime_directive_justification": "Concluding knowledge exchange session",
            },
        }
        await self.kernel.event_bus.publish(end_event)
        
        # Move agents back to desks
        agent_a.move_to("desk")
        agent_b.move_to("desk")
        
        # Update organizational metrics
        self.kernel.org_memory.global_metrics["water_cooler_exchanges"] += 1
    
    def stop(self) -> None:
        self._running = False
    
    def get_state(self) -> Dict[str, Any]:
        return {
            "exchange_count": self.exchange_count,
            "last_exchange": self.last_exchange,
            "running": self._running,
        }


class Boardroom:
    """
    Boardroom — All agents come together for project discussions, launches, upskills.
    Convened by Chief for major decisions.
    """
    
    def __init__(self, kernel: "OfficeKernel"):
        self.kernel = kernel
        self.session_count = 0
        self.last_session: str | None = None
        self._in_session = False
        self._current_agenda: Dict[str, Any] | None = None
        self._running = False
        self._session_interval = 180  # 3 minutes for demo
    
    async def run(self) -> None:
        """Main boardroom loop — periodic sessions."""
        self._running = True
        # Wait for initial stability
        await asyncio.sleep(60)
        
        while self._running and self.kernel.running:
            await asyncio.sleep(self._session_interval)
            
            if not self.kernel.running:
                break
            
            # Randomly choose session type
            session_type = random.choice(["discussion", "project_launch", "upskill"])
            await self.convene_session(session_type)
    
    async def convene_session(self, session_type: str) -> None:
        """Convene a boardroom session."""
        if self._in_session:
            return
        
        self._in_session = True
        self.session_count += 1
        self.last_session = datetime.now(timezone.utc).isoformat()
        
        # Build agenda
        if session_type == "project_launch":
            agenda = await self._build_project_launch_agenda()
        elif session_type == "upskill":
            agenda = await self._build_upskill_agenda()
        else:
            agenda = await self._build_discussion_agenda()
        
        self._current_agenda = agenda
        
        # Move all agents to boardroom
        for agent in self.kernel.agents.values():
            agent.move_to("boardroom")
        
        # Emit convene event
        convene_event = {
            "type": EventType.BOARDROOM_CONVENE,
            "origin_id": "boardroom",
            "payload": {
                "action": "boardroom_convene",
                "session_number": self.session_count,
                "session_type": session_type,
                "agenda": agenda,
                "participants": list(self.kernel.agents.keys()),
                "prime_directive_justification": "Convening collective decision-making session",
            },
        }
        await self.kernel.event_bus.publish(convene_event)
        
        await asyncio.sleep(2)
        
        # Collect contributions from all agents
        contributions = []
        for agent in self.kernel.agents.values():
            contribution = await agent.participate_boardroom(agenda)
            contributions.append({
                "agent": agent.agent_id,
                "contribution": contribution,
            })
            
            # Emit discussion event
            discussion_event = {
                "type": EventType.BOARDROOM_DISCUSSION,
                "origin_id": agent.agent_id,
                "payload": {
                    "action": "boardroom_contribution",
                    "session_number": self.session_count,
                    "agent": agent.agent_id,
                    "contribution": contribution,
                    "prime_directive_justification": f"{agent.agent_id} contributing to collective decision",
                },
            }
            await self.kernel.event_bus.publish(discussion_event)
            await asyncio.sleep(1)
        
        # Make decision based on contributions
        decision = await self._make_decision(session_type, agenda, contributions)
        
        # Emit decision event
        decision_event = {
            "type": EventType.BOARDROOM_DECISION,
            "origin_id": "boardroom",
            "payload": {
                "action": "boardroom_decision",
                "session_number": self.session_count,
                "session_type": session_type,
                "decision": decision,
                "contributions_count": len(contributions),
                "prime_directive_justification": "Collective decision reached through consensus",
            },
        }
        await self.kernel.event_bus.publish(decision_event)
        
        # Handle specific session outcomes
        if session_type == "project_launch" and decision.get("approved"):
            await self._launch_project(agenda, contributions)
        elif session_type == "upskill":
            await self._complete_upskill(agenda, contributions)
        
        await asyncio.sleep(2)
        
        # Adjourn
        adjourn_event = {
            "type": EventType.BOARDROOM_ADJOURN,
            "origin_id": "boardroom",
            "payload": {
                "action": "boardroom_adjourn",
                "session_number": self.session_count,
                "session_type": session_type,
                "outcome": decision,
                "prime_directive_justification": "Concluding boardroom session",
            },
        }
        await self.kernel.event_bus.publish(adjourn_event)
        
        # Move agents back to desks
        for agent in self.kernel.agents.values():
            agent.move_to("desk")
        
        self._in_session = False
        self._current_agenda = None
        self.kernel.org_memory.global_metrics["boardroom_sessions"] += 1
    
    async def _build_discussion_agenda(self) -> Dict[str, Any]:
        topics = [
            "Review current project progress",
            "Discuss emerging opportunities",
            "Evaluate team performance metrics",
            "Plan next sprint priorities",
            "Address blockers and escalations",
        ]
        return {
            "type": "discussion",
            "topic": random.choice(topics),
            "duration_estimate": "15 minutes",
        }
    
    async def _build_project_launch_agenda(self) -> Dict[str, Any]:
        from appshak_office.agents import PROBLEMS, SOLUTIONS
        problem = random.choice(PROBLEMS)
        solution = random.choice(SOLUTIONS)
        return {
            "type": "project_launch",
            "project_name": f"{solution} for {problem['domain']}",
            "problem": problem,
            "proposed_solution": solution,
            "estimated_complexity": random.choice(["low", "medium", "high"]),
            "duration_estimate": "30 minutes",
        }
    
    async def _build_upskill_agenda(self) -> Dict[str, Any]:
        from appshak_office.agents import SKILLS
        skill = random.choice(SKILLS)
        return {
            "type": "upskill",
            "skill": skill,
            "topic": f"Advanced {skill.replace('_', ' ').title()} Techniques",
            "duration_estimate": "20 minutes",
        }
    
    async def _make_decision(
        self,
        session_type: str,
        agenda: Dict[str, Any],
        contributions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if session_type == "project_launch":
            # Count votes
            votes = [c["contribution"].get("commitment", "cautious") for c in contributions]
            ready_count = sum(1 for v in votes if v == "ready")
            approved = ready_count >= len(votes) / 2
            return {
                "approved": approved,
                "ready_count": ready_count,
                "total_votes": len(votes),
                "outcome": "Project approved for launch" if approved else "Project deferred",
            }
        
        elif session_type == "upskill":
            return {
                "approved": True,
                "skill": agenda.get("skill"),
                "participants_trained": len(contributions),
                "outcome": "Upskill session completed successfully",
            }
        
        else:
            # Discussion — summarize
            return {
                "approved": True,
                "topic": agenda.get("topic"),
                "contributions_received": len(contributions),
                "outcome": "Discussion concluded with action items",
            }
    
    async def _launch_project(
        self,
        agenda: Dict[str, Any],
        contributions: List[Dict[str, Any]],
    ) -> None:
        # Create project in organizational memory
        assigned = [c["agent"] for c in contributions if c["contribution"].get("commitment") == "ready"]
        project = self.kernel.org_memory.create_project(
            name=agenda.get("project_name", "New Project"),
            domain=agenda.get("problem", {}).get("domain", "general"),
            assigned_agents=assigned,
        )
        project.status = "active"
        
        # Emit launch event
        launch_event = {
            "type": EventType.PROJECT_LAUNCH,
            "origin_id": "boardroom",
            "payload": {
                "action": "project_launch",
                "project_id": project.project_id,
                "project_name": project.name,
                "domain": project.domain,
                "assigned_agents": assigned,
                "prime_directive_justification": "Launching new project to solve real-world problem",
            },
        }
        await self.kernel.event_bus.publish(launch_event)
        self.kernel.org_memory.global_metrics["launches_completed"] += 1
    
    async def _complete_upskill(
        self,
        agenda: Dict[str, Any],
        contributions: List[Dict[str, Any]],
    ) -> None:
        skill = agenda.get("skill", "general")
        
        # Emit upskill event
        upskill_event = {
            "type": EventType.UPSKILL_SESSION,
            "origin_id": "boardroom",
            "payload": {
                "action": "upskill_complete",
                "skill": skill,
                "participants": [c["agent"] for c in contributions],
                "proficiency_gains": {
                    c["agent"]: c["contribution"].get("new_proficiency", 0.1)
                    for c in contributions
                },
                "prime_directive_justification": "Enhancing collective competence through skill development",
            },
        }
        await self.kernel.event_bus.publish(upskill_event)
        self.kernel.org_memory.global_metrics["upskills_completed"] += 1
    
    def stop(self) -> None:
        self._running = False
    
    def get_state(self) -> Dict[str, Any]:
        return {
            "session_count": self.session_count,
            "last_session": self.last_session,
            "in_session": self._in_session,
            "current_agenda": self._current_agenda,
            "running": self._running,
        }
