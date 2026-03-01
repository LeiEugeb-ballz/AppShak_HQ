from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence

from .constants import (
    REGISTRY_EPOCH_TIMESTAMP,
    REGISTRY_INITIAL_VERSION,
    REGISTRY_SCHEMA_VERSION,
    REPUTATION_MAX,
    REPUTATION_MIN,
    TRUST_MAX,
    TRUST_MIN,
)
from .utils import as_float, as_int, atomic_write_text, clamp, normalize_agent_id


@dataclass(frozen=True)
class AgentDefinition:
    agent_id: str
    role: str
    authority_level: float


def _normalize_trust_weights(
    value: Any,
    *,
    all_agent_ids: Sequence[str],
) -> Dict[str, float]:
    weights_raw = value if isinstance(value, Mapping) else {}
    normalized: Dict[str, float] = {}
    for peer_id in sorted(all_agent_ids):
        weight_raw = weights_raw.get(peer_id, 0.5)
        normalized[peer_id] = clamp(as_float(weight_raw, default=0.5), TRUST_MIN, TRUST_MAX)
    return normalized


def _normalize_agent_state(
    agent_id: str,
    value: Any,
    *,
    all_agent_ids: Sequence[str],
) -> Dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    return {
        "agent_id": agent_id,
        "role": str(source.get("role", "worker")).strip() or "worker",
        "authority_level": clamp(as_float(source.get("authority_level"), default=0.0), 0.0, 1.0),
        "reputation_score": clamp(as_float(source.get("reputation_score"), default=0.5), REPUTATION_MIN, REPUTATION_MAX),
        "trust_weights": _normalize_trust_weights(source.get("trust_weights"), all_agent_ids=all_agent_ids),
        "knowledge_lessons": _normalize_knowledge_refs(source.get("knowledge_lessons")),
    }


def _normalize_knowledge_refs(value: Any) -> List[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    refs = []
    for item in value:
        if isinstance(item, str) and item.strip():
            refs.append(item.strip())
    refs.sort()
    return refs


def default_registry_state(agent_definitions: Sequence[AgentDefinition]) -> Dict[str, Any]:
    agent_ids = sorted({normalize_agent_id(spec.agent_id) for spec in agent_definitions if normalize_agent_id(spec.agent_id)})
    agents: Dict[str, Dict[str, Any]] = {}
    history: Dict[str, List[float]] = {}
    for spec in sorted(agent_definitions, key=lambda item: normalize_agent_id(item.agent_id)):
        agent_id = normalize_agent_id(spec.agent_id)
        if not agent_id:
            continue
        agents[agent_id] = {
            "agent_id": agent_id,
            "role": str(spec.role).strip() or "worker",
            "authority_level": clamp(as_float(spec.authority_level, default=0.0), 0.0, 1.0),
            "reputation_score": 0.5,
            "trust_weights": {peer_id: 0.5 for peer_id in agent_ids},
            "knowledge_lessons": [],
        }
        history[agent_id] = [0.5]

    return {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "version": REGISTRY_INITIAL_VERSION,
        "last_updated": REGISTRY_EPOCH_TIMESTAMP,
        "agents": agents,
        "history": history,
    }


def normalize_registry_state(value: Any) -> Dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    agents_raw = source.get("agents")
    agents_input = agents_raw if isinstance(agents_raw, Mapping) else {}
    agent_ids = sorted([agent_id for agent_id in (normalize_agent_id(key) for key in agents_input.keys()) if agent_id])
    agents: Dict[str, Dict[str, Any]] = {}
    for agent_id in agent_ids:
        agents[agent_id] = _normalize_agent_state(agent_id, agents_input.get(agent_id), all_agent_ids=agent_ids)

    history_raw = source.get("history")
    history_input = history_raw if isinstance(history_raw, Mapping) else {}
    history: Dict[str, List[float]] = {}
    for agent_id in agent_ids:
        raw_series = history_input.get(agent_id, [agents[agent_id]["reputation_score"]])
        if isinstance(raw_series, Sequence) and not isinstance(raw_series, (str, bytes)):
            series = [
                clamp(as_float(item, default=agents[agent_id]["reputation_score"]), REPUTATION_MIN, REPUTATION_MAX)
                for item in raw_series
            ]
            history[agent_id] = series or [agents[agent_id]["reputation_score"]]
        else:
            history[agent_id] = [agents[agent_id]["reputation_score"]]

    version = max(REGISTRY_INITIAL_VERSION, as_int(source.get("version"), default=REGISTRY_INITIAL_VERSION))
    last_updated_raw = source.get("last_updated")
    last_updated = str(last_updated_raw).strip() if isinstance(last_updated_raw, str) and last_updated_raw.strip() else REGISTRY_EPOCH_TIMESTAMP

    return {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "version": version,
        "last_updated": last_updated,
        "agents": agents,
        "history": history,
    }


class AgentRegistry:
    def __init__(self, state: Mapping[str, Any]) -> None:
        self._state = normalize_registry_state(state)

    @classmethod
    def from_definitions(cls, definitions: Sequence[AgentDefinition | Mapping[str, Any]]) -> "AgentRegistry":
        normalized: List[AgentDefinition] = []
        for value in definitions:
            if isinstance(value, AgentDefinition):
                candidate = value
            elif isinstance(value, Mapping):
                candidate = AgentDefinition(
                    agent_id=str(value.get("agent_id", "")),
                    role=str(value.get("role", "worker")),
                    authority_level=as_float(value.get("authority_level"), default=0.0),
                )
            else:
                continue
            agent_id = normalize_agent_id(candidate.agent_id)
            if not agent_id:
                continue
            normalized.append(
                AgentDefinition(
                    agent_id=agent_id,
                    role=str(candidate.role).strip() or "worker",
                    authority_level=clamp(as_float(candidate.authority_level, default=0.0), 0.0, 1.0),
                )
            )
        return cls(default_registry_state(normalized))

    @property
    def version(self) -> int:
        return int(self._state["version"])

    @property
    def last_updated(self) -> str:
        return str(self._state["last_updated"])

    @property
    def agent_ids(self) -> List[str]:
        return sorted(self._state["agents"].keys())

    def has_agent(self, agent_id: str) -> bool:
        return normalize_agent_id(agent_id) in self._state["agents"]

    def authority_level(self, agent_id: str) -> float:
        normalized = normalize_agent_id(agent_id)
        agent = self._state["agents"].get(normalized, {})
        return float(agent.get("authority_level", 0.0))

    def reputation_score(self, agent_id: str) -> float:
        normalized = normalize_agent_id(agent_id)
        agent = self._state["agents"].get(normalized, {})
        return float(agent.get("reputation_score", 0.0))

    def trust_weight(self, observer_id: str, subject_id: str) -> float:
        observer = self._state["agents"].get(normalize_agent_id(observer_id), {})
        weights = observer.get("trust_weights", {}) if isinstance(observer, Mapping) else {}
        return float(weights.get(normalize_agent_id(subject_id), 0.5))

    def add_lesson_reference(self, agent_id: str, lesson_id: str) -> None:
        normalized_id = normalize_agent_id(agent_id)
        if normalized_id not in self._state["agents"]:
            return
        lessons = self._state["agents"][normalized_id].setdefault("knowledge_lessons", [])
        if lesson_id not in lessons:
            lessons.append(lesson_id)
            lessons.sort()

    def apply_outcome_update(
        self,
        *,
        subject_id: str,
        reputation_delta: float,
        observer_trust_deltas: Mapping[str, float],
        updated_at: str,
    ) -> None:
        normalized_subject = normalize_agent_id(subject_id)
        if normalized_subject not in self._state["agents"]:
            return

        subject = self._state["agents"][normalized_subject]
        current_reputation = as_float(subject.get("reputation_score"), default=0.5)
        subject["reputation_score"] = clamp(current_reputation + reputation_delta, REPUTATION_MIN, REPUTATION_MAX)

        for observer_id in self.agent_ids:
            observer = self._state["agents"][observer_id]
            weights = observer.get("trust_weights", {})
            if not isinstance(weights, MutableMapping):
                weights = {}
                observer["trust_weights"] = weights
            current_weight = as_float(weights.get(normalized_subject), default=0.5)
            delta = as_float(observer_trust_deltas.get(observer_id), default=0.0)
            weights[normalized_subject] = clamp(current_weight + delta, TRUST_MIN, TRUST_MAX)

        self._bump_version(updated_at=updated_at)

    def record_noop_update(self, *, updated_at: str) -> None:
        self._bump_version(updated_at=updated_at)

    def _bump_version(self, *, updated_at: str) -> None:
        self._state["version"] = int(self._state["version"]) + 1
        self._state["last_updated"] = updated_at
        history = self._state.setdefault("history", {})
        for agent_id in self.agent_ids:
            series = history.setdefault(agent_id, [])
            series.append(self.reputation_score(agent_id))

    def snapshot(self) -> Dict[str, Any]:
        return normalize_registry_state(self._state)


class AgentRegistryStore:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> Dict[str, Any]:
        if not self._path.exists():
            return normalize_registry_state({})
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return normalize_registry_state({})
        return normalize_registry_state(raw)

    def save_atomic(self, state: Mapping[str, Any]) -> Dict[str, Any]:
        normalized = normalize_registry_state(state)
        atomic_write_text(self._path, json.dumps(normalized, ensure_ascii=True, sort_keys=True, indent=2))
        return normalized
