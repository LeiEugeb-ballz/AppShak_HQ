"""
Persistent Memory System — Per-Agent and Global stores that survive restarts.

Memory Structure:
- Organizational Memory (Global): Past projects, success rates, known domains/failures
- Agent Memory (Private): Lessons learned, collaboration history, confidence scores, skill evolution
- Relationship Weights: Updated via interactions; influence debate outcomes
- Performance Metrics: Task success, autonomy levels, evolution indices
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict


@dataclass
class AgentMemory:
    """Private memory for each agent."""
    agent_id: str
    lessons_learned: List[Dict[str, Any]] = field(default_factory=list)
    collaboration_history: List[Dict[str, Any]] = field(default_factory=list)
    confidence_score: float = 0.5
    skills: Dict[str, float] = field(default_factory=dict)  # skill_name -> proficiency
    task_success_count: int = 0
    task_failure_count: int = 0
    autonomy_level: float = 0.3
    evolution_index: float = 0.0
    working_memory: List[Dict[str, Any]] = field(default_factory=list)  # short-term
    
    def add_lesson(self, lesson: str, context: Dict[str, Any]) -> None:
        self.lessons_learned.append({
            "lesson": lesson,
            "context": context,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        # Keep last 100 lessons
        if len(self.lessons_learned) > 100:
            self.lessons_learned = self.lessons_learned[-100:]
    
    def record_collaboration(self, partner_id: str, outcome: str, quality: float) -> None:
        self.collaboration_history.append({
            "partner": partner_id,
            "outcome": outcome,
            "quality": quality,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        if len(self.collaboration_history) > 200:
            self.collaboration_history = self.collaboration_history[-200:]
    
    def update_skill(self, skill: str, delta: float) -> None:
        current = self.skills.get(skill, 0.0)
        self.skills[skill] = min(1.0, max(0.0, current + delta))
    
    def record_task_outcome(self, success: bool) -> None:
        if success:
            self.task_success_count += 1
            self.confidence_score = min(1.0, self.confidence_score + 0.02)
            self.evolution_index += 0.01
        else:
            self.task_failure_count += 1
            self.confidence_score = max(0.1, self.confidence_score - 0.01)
    
    @property
    def success_rate(self) -> float:
        total = self.task_success_count + self.task_failure_count
        return self.task_success_count / total if total > 0 else 0.5


@dataclass
class RelationshipWeight:
    """Dynamic relationship score between two agents."""
    agent_a: str
    agent_b: str
    trust_score: float = 0.5
    collaboration_count: int = 0
    last_interaction: Optional[str] = None
    
    def update_after_interaction(self, positive: bool) -> None:
        self.collaboration_count += 1
        self.last_interaction = datetime.now(timezone.utc).isoformat()
        if positive:
            self.trust_score = min(1.0, self.trust_score + 0.05)
        else:
            self.trust_score = max(0.1, self.trust_score - 0.03)


@dataclass
class Project:
    """A project tracked in organizational memory."""
    project_id: str
    name: str
    domain: str
    status: str  # proposed, active, completed, failed
    created_at: str
    updated_at: str
    assigned_agents: List[str] = field(default_factory=list)
    milestones: List[Dict[str, Any]] = field(default_factory=list)
    success_metrics: Dict[str, float] = field(default_factory=dict)


class OrganizationalMemory:
    """
    Global memory store for the entire organization.
    Persists to JSON files for survival across restarts.
    """
    
    def __init__(self, storage_root: str = "appshak_office_state"):
        self.storage_root = Path(storage_root)
        self.storage_root.mkdir(parents=True, exist_ok=True)
        
        self._lock = asyncio.Lock()
        
        # In-memory caches
        self.projects: Dict[str, Project] = {}
        self.agent_memories: Dict[str, AgentMemory] = {}
        self.relationships: Dict[str, RelationshipWeight] = {}  # "a:b" -> weight
        self.known_domains: Dict[str, Dict[str, Any]] = {}
        self.known_failures: List[Dict[str, Any]] = []
        self.global_metrics: Dict[str, Any] = {
            "total_tasks_completed": 0,
            "total_problems_discovered": 0,
            "total_proposals_approved": 0,
            "total_proposals_denied": 0,
            "water_cooler_exchanges": 0,
            "boardroom_sessions": 0,
            "upskills_completed": 0,
            "launches_completed": 0,
        }
        self.event_log: List[Dict[str, Any]] = []
        
    async def initialize(self) -> None:
        """Load persisted state from disk."""
        await self._load_state()
    
    async def persist(self) -> None:
        """Save current state to disk."""
        async with self._lock:
            state = {
                "projects": {k: asdict(v) for k, v in self.projects.items()},
                "agent_memories": {k: asdict(v) for k, v in self.agent_memories.items()},
                "relationships": {k: asdict(v) for k, v in self.relationships.items()},
                "known_domains": self.known_domains,
                "known_failures": self.known_failures[-500:],
                "global_metrics": self.global_metrics,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            state_path = self.storage_root / "organizational_memory.json"
            await asyncio.to_thread(
                state_path.write_text,
                json.dumps(state, indent=2, ensure_ascii=False),
                "utf-8"
            )
    
    async def _load_state(self) -> None:
        state_path = self.storage_root / "organizational_memory.json"
        if not state_path.exists():
            return
        
        try:
            raw = await asyncio.to_thread(state_path.read_text, "utf-8")
            state = json.loads(raw)
            
            for pid, pdata in state.get("projects", {}).items():
                self.projects[pid] = Project(**pdata)
            
            for aid, adata in state.get("agent_memories", {}).items():
                self.agent_memories[aid] = AgentMemory(**adata)
            
            for rkey, rdata in state.get("relationships", {}).items():
                self.relationships[rkey] = RelationshipWeight(**rdata)
            
            self.known_domains = state.get("known_domains", {})
            self.known_failures = state.get("known_failures", [])
            self.global_metrics = state.get("global_metrics", self.global_metrics)
        except Exception:
            pass  # Start fresh if corrupted
    
    def get_agent_memory(self, agent_id: str) -> AgentMemory:
        if agent_id not in self.agent_memories:
            self.agent_memories[agent_id] = AgentMemory(agent_id=agent_id)
        return self.agent_memories[agent_id]
    
    def get_relationship(self, agent_a: str, agent_b: str) -> RelationshipWeight:
        key = f"{min(agent_a, agent_b)}:{max(agent_a, agent_b)}"
        if key not in self.relationships:
            self.relationships[key] = RelationshipWeight(agent_a=agent_a, agent_b=agent_b)
        return self.relationships[key]
    
    def record_domain(self, domain: str, info: Dict[str, Any]) -> None:
        if domain not in self.known_domains:
            self.known_domains[domain] = {"first_seen": datetime.now(timezone.utc).isoformat(), "encounters": 0}
        self.known_domains[domain]["encounters"] += 1
        self.known_domains[domain].update(info)
    
    def record_failure(self, context: Dict[str, Any]) -> None:
        self.known_failures.append({
            **context,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        if len(self.known_failures) > 500:
            self.known_failures = self.known_failures[-500:]
    
    def log_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        self.event_log.append({
            "type": event_type,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        if len(self.event_log) > 1000:
            self.event_log = self.event_log[-1000:]
    
    def create_project(self, name: str, domain: str, assigned_agents: List[str]) -> Project:
        project_id = f"proj-{len(self.projects)+1:04d}"
        now = datetime.now(timezone.utc).isoformat()
        project = Project(
            project_id=project_id,
            name=name,
            domain=domain,
            status="proposed",
            created_at=now,
            updated_at=now,
            assigned_agents=assigned_agents,
        )
        self.projects[project_id] = project
        return project
    
    def get_active_projects(self) -> List[Project]:
        return [p for p in self.projects.values() if p.status == "active"]
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        return {
            **self.global_metrics,
            "total_projects": len(self.projects),
            "active_projects": len(self.get_active_projects()),
            "known_domains_count": len(self.known_domains),
            "known_failures_count": len(self.known_failures),
            "agent_count": len(self.agent_memories),
            "relationship_count": len(self.relationships),
        }
