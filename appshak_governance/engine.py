from __future__ import annotations

from dataclasses import dataclass
from statistics import pvariance
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


_TARGET_AGENT_KEYS = ("target_agent", "agent_id", "worker")
_DEFAULT_TRUST_WEIGHT = 0.5

_EVENT_OUTCOME_SCORES = {
    "SUPERVISOR_START": 0.7,
    "SUPERVISOR_STOP": -0.7,
    "INTENT_DISPATCH": 0.6,
    "PROPOSAL_INVALID": -0.8,
    "WORKER_STARTED": 0.6,
    "WORKER_RESTART_SCHEDULED": -0.4,
    "WORKER_RESTARTED": 0.7,
    "WORKER_EXITED": -0.9,
    "WORKER_HEARTBEAT_MISSED": -0.6,
}


def _coerce_agent_id(raw: Any) -> Optional[str]:
    if isinstance(raw, str):
        value = raw.strip().lower()
        if value:
            return value
    return None


def _clamp(value: float, *, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _safe_int(raw: Any, *, default: int = 0) -> int:
    try:
        return int(raw)
    except Exception:
        return default


def _safe_float(raw: Any, *, default: float = 0.0) -> float:
    try:
        return float(raw)
    except Exception:
        return default


@dataclass(frozen=True)
class AgentConfig:
    agent_id: str
    role: str
    authority_level: float


@dataclass
class OutcomeObservation:
    agent_id: str
    outcome_score: float
    source: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "outcome_score": self.outcome_score,
            "source": self.source,
        }


class AgentRegistry:
    """Versioned registry of governance agent trust and reputation state."""

    def __init__(self, configs: Sequence[AgentConfig | Mapping[str, Any]]) -> None:
        normalized_configs = self._normalize_configs(configs)
        if not normalized_configs:
            raise ValueError("AgentRegistry requires at least one agent config.")

        self._agent_ids: List[str] = [cfg.agent_id for cfg in normalized_configs]
        self._max_authority = max(cfg.authority_level for cfg in normalized_configs)
        self._version = 1
        self._agents: Dict[str, Dict[str, Any]] = {}
        self._trust_history: Dict[str, List[float]] = {}

        for cfg in normalized_configs:
            trust_weights = {peer_id: _DEFAULT_TRUST_WEIGHT for peer_id in self._agent_ids}
            self._agents[cfg.agent_id] = {
                "agent_id": cfg.agent_id,
                "role": cfg.role,
                "authority_level": cfg.authority_level,
                "trust_weights": trust_weights,
                "reputation_score": _DEFAULT_TRUST_WEIGHT,
            }
            self._trust_history[cfg.agent_id] = [_DEFAULT_TRUST_WEIGHT]

    @property
    def version(self) -> int:
        return self._version

    @property
    def max_authority_level(self) -> float:
        return self._max_authority

    @property
    def agent_ids(self) -> List[str]:
        return list(self._agent_ids)

    @property
    def trust_history(self) -> Dict[str, List[float]]:
        return {agent_id: list(series) for agent_id, series in self._trust_history.items()}

    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        normalized = _coerce_agent_id(agent_id)
        if normalized is None:
            return None
        payload = self._agents.get(normalized)
        if payload is None:
            return None
        return {
            "agent_id": payload["agent_id"],
            "role": payload["role"],
            "authority_level": payload["authority_level"],
            "trust_weights": dict(payload["trust_weights"]),
            "reputation_score": payload["reputation_score"],
        }

    def has_agent(self, agent_id: str) -> bool:
        normalized = _coerce_agent_id(agent_id)
        if normalized is None:
            return False
        return normalized in self._agents

    def record_version(self) -> None:
        self._version += 1
        for agent_id in self._agent_ids:
            trust_weights = self._agents[agent_id]["trust_weights"]
            mean_trust = sum(float(value) for value in trust_weights.values()) / float(len(trust_weights))
            self._trust_history[agent_id].append(_clamp(mean_trust, low=0.0, high=1.0))

    def to_dict(self) -> Dict[str, Any]:
        agents_payload: Dict[str, Any] = {}
        for agent_id in self._agent_ids:
            state = self._agents[agent_id]
            agents_payload[agent_id] = {
                "agent_id": state["agent_id"],
                "role": state["role"],
                "authority_level": state["authority_level"],
                "trust_weights": dict(state["trust_weights"]),
                "reputation_score": state["reputation_score"],
            }
        return {
            "version": self._version,
            "agents": agents_payload,
        }

    def _mutable_agent_state(self, agent_id: str) -> Dict[str, Any]:
        return self._agents[agent_id]

    @staticmethod
    def _normalize_configs(configs: Sequence[AgentConfig | Mapping[str, Any]]) -> List[AgentConfig]:
        normalized: List[AgentConfig] = []
        seen_ids: set[str] = set()

        for raw_cfg in configs:
            if isinstance(raw_cfg, AgentConfig):
                candidate = raw_cfg
            elif isinstance(raw_cfg, Mapping):
                candidate = AgentConfig(
                    agent_id=str(raw_cfg.get("agent_id", "")).strip().lower(),
                    role=str(raw_cfg.get("role", "")).strip() or "worker",
                    authority_level=_clamp(_safe_float(raw_cfg.get("authority_level"), default=0.0), low=0.0, high=1.0),
                )
            else:
                continue

            agent_id = _coerce_agent_id(candidate.agent_id)
            if agent_id is None or agent_id in seen_ids:
                continue

            role = str(candidate.role).strip() or "worker"
            authority_level = _clamp(_safe_float(candidate.authority_level, default=0.0), low=0.0, high=1.0)

            normalized.append(
                AgentConfig(
                    agent_id=agent_id,
                    role=role,
                    authority_level=authority_level,
                )
            )
            seen_ids.add(agent_id)

        return normalized


class RelationshipWeightEngine:
    """Deterministic trust and reputation updates from observable outcomes."""

    def __init__(
        self,
        *,
        positive_step: float = 0.08,
        negative_step: float = 0.1,
        peer_influence_floor: float = 0.6,
    ) -> None:
        self._positive_step = _clamp(positive_step, low=0.0, high=1.0)
        self._negative_step = _clamp(negative_step, low=0.0, high=1.0)
        self._peer_influence_floor = _clamp(peer_influence_floor, low=0.0, high=1.0)

    def apply_observations(
        self,
        registry: AgentRegistry,
        observations: Iterable[OutcomeObservation],
    ) -> bool:
        changed = False
        for observation in observations:
            agent_id = _coerce_agent_id(observation.agent_id)
            if agent_id is None or not registry.has_agent(agent_id):
                continue

            outcome_score = _clamp(observation.outcome_score, low=-1.0, high=1.0)
            if outcome_score == 0.0:
                continue

            step = self._positive_step if outcome_score >= 0.0 else self._negative_step
            delta = outcome_score * step

            target_state = registry._mutable_agent_state(agent_id)
            target_state["reputation_score"] = _clamp(
                target_state["reputation_score"] + delta,
                low=0.0,
                high=1.0,
            )

            for observer_id in registry.agent_ids:
                observer_state = registry._mutable_agent_state(observer_id)
                authority = _clamp(
                    observer_state["authority_level"] / max(registry.max_authority_level, 1e-9),
                    low=0.0,
                    high=1.0,
                )
                influence = self._peer_influence_floor + (1.0 - self._peer_influence_floor) * authority
                current_weight = _safe_float(
                    observer_state["trust_weights"].get(agent_id, _DEFAULT_TRUST_WEIGHT),
                    default=_DEFAULT_TRUST_WEIGHT,
                )
                observer_state["trust_weights"][agent_id] = _clamp(
                    current_weight + (delta * influence),
                    low=0.0,
                    high=1.0,
                )

            changed = True

        if changed:
            registry.record_version()
        return changed


class ProjectionOutcomeAdapter:
    """Translate projection deltas into deterministic governance outcomes."""

    def derive_observations(
        self,
        *,
        previous_view: Mapping[str, Any] | None,
        current_view: Mapping[str, Any] | None,
        known_agents: Sequence[str],
    ) -> List[OutcomeObservation]:
        previous = previous_view if isinstance(previous_view, Mapping) else {}
        current = current_view if isinstance(current_view, Mapping) else {}
        known = [agent_id for agent_id in (_coerce_agent_id(value) for value in known_agents) if agent_id is not None]
        known_set = set(known)

        observations: List[OutcomeObservation] = []
        prev_event_id = _safe_int(previous.get("last_seen_event_id"), default=0)
        curr_event_id = _safe_int(current.get("last_seen_event_id"), default=0)
        if curr_event_id > prev_event_id:
            current_event = current.get("current_event")
            if isinstance(current_event, Mapping):
                event_type = str(current_event.get("type", "")).strip().upper()
                target_agent = self._extract_target_agent(current_event, known_set)
                if event_type and target_agent is not None:
                    outcome_score = _EVENT_OUTCOME_SCORES.get(event_type, 0.0)
                    if outcome_score != 0.0:
                        observations.append(
                            OutcomeObservation(
                                agent_id=target_agent,
                                outcome_score=outcome_score,
                                source=event_type,
                            )
                        )

        prev_allowed, prev_denied = self._tool_counts(previous)
        curr_allowed, curr_denied = self._tool_counts(current)
        allowed_delta = max(0, curr_allowed - prev_allowed)
        denied_delta = max(0, curr_denied - prev_denied)

        impacted_agents = self._active_agents_from_workers(current, known_set)
        if not impacted_agents:
            impacted_agents = sorted(known_set)

        if allowed_delta > 0:
            score = _clamp(0.2 * float(allowed_delta), low=0.0, high=1.0)
            for agent_id in impacted_agents:
                observations.append(
                    OutcomeObservation(
                        agent_id=agent_id,
                        outcome_score=score,
                        source="TOOL_AUDIT_ALLOWED_DELTA",
                    )
                )

        if denied_delta > 0:
            score = _clamp(-0.25 * float(denied_delta), low=-1.0, high=0.0)
            for agent_id in impacted_agents:
                observations.append(
                    OutcomeObservation(
                        agent_id=agent_id,
                        outcome_score=score,
                        source="TOOL_AUDIT_DENIED_DELTA",
                    )
                )

        return observations

    @staticmethod
    def _extract_target_agent(event: Mapping[str, Any], known_agents: set[str]) -> Optional[str]:
        payload = event.get("payload")
        if isinstance(payload, Mapping):
            for key in _TARGET_AGENT_KEYS:
                target_agent = _coerce_agent_id(payload.get(key))
                if target_agent is not None and target_agent in known_agents:
                    return target_agent

        origin_id = _coerce_agent_id(event.get("origin_id"))
        if origin_id is not None and origin_id in known_agents:
            return origin_id
        return None

    @staticmethod
    def _tool_counts(view: Mapping[str, Any]) -> tuple[int, int]:
        counts = view.get("tool_audit_counts")
        if not isinstance(counts, Mapping):
            return (0, 0)
        return (
            max(0, _safe_int(counts.get("allowed"), default=0)),
            max(0, _safe_int(counts.get("denied"), default=0)),
        )

    @staticmethod
    def _active_agents_from_workers(view: Mapping[str, Any], known_agents: set[str]) -> List[str]:
        workers = view.get("workers")
        if not isinstance(workers, Mapping):
            return []

        active: List[str] = []
        for worker_id_raw, worker_state_raw in workers.items():
            worker_id = _coerce_agent_id(worker_id_raw)
            if worker_id is None or worker_id not in known_agents:
                continue
            if not isinstance(worker_state_raw, Mapping):
                continue
            present = bool(worker_state_raw.get("present", False))
            state = str(worker_state_raw.get("state", "")).strip().upper()
            if present or state in {"ACTIVE", "RESTARTING"}:
                active.append(worker_id)
        active.sort()
        return active


class BoardroomArbitrator:
    """Deterministic weighted consensus over proposal ballots."""

    def arbitrate(
        self,
        *,
        registry: AgentRegistry,
        target_agent: str,
        ballots: Iterable[Mapping[str, Any]],
        threshold: float = 0.5,
    ) -> Dict[str, Any]:
        normalized_target = _coerce_agent_id(target_agent)
        normalized_threshold = _clamp(threshold, low=0.0, high=1.0)
        if normalized_target is None or not registry.has_agent(normalized_target):
            return {
                "target_agent": normalized_target,
                "threshold": normalized_threshold,
                "aggregate_score": 0.0,
                "approved": False,
                "votes": [],
            }

        votes: List[Dict[str, Any]] = []
        for ballot in ballots:
            voter_id = _coerce_agent_id(ballot.get("agent_id")) if isinstance(ballot, Mapping) else None
            if voter_id is None or not registry.has_agent(voter_id):
                continue

            voter_state = registry._mutable_agent_state(voter_id)
            reasoning_score = _clamp(_safe_float(ballot.get("reasoning_score"), default=0.0), low=0.0, high=1.0)
            authority_level = _clamp(_safe_float(voter_state.get("authority_level"), default=0.0), low=0.0, high=1.0)
            trust_weight = _clamp(
                _safe_float(voter_state["trust_weights"].get(normalized_target, _DEFAULT_TRUST_WEIGHT)),
                low=0.0,
                high=1.0,
            )
            decision_score = reasoning_score * authority_level * trust_weight
            votes.append(
                {
                    "agent_id": voter_id,
                    "reasoning_score": reasoning_score,
                    "authority_level": authority_level,
                    "trust_weight": trust_weight,
                    "decision_score": decision_score,
                }
            )

        aggregate_score = 0.0
        if votes:
            aggregate_score = sum(vote["decision_score"] for vote in votes) / float(len(votes))

        return {
            "target_agent": normalized_target,
            "threshold": normalized_threshold,
            "aggregate_score": aggregate_score,
            "approved": aggregate_score >= normalized_threshold,
            "votes": votes,
        }


class TrustStabilityMetric:
    """Variance of trust over version history for each agent and globally."""

    def compute(self, registry: AgentRegistry) -> Dict[str, Any]:
        per_agent_variance: Dict[str, float] = {}
        all_variances: List[float] = []

        for agent_id, samples in registry.trust_history.items():
            if len(samples) <= 1:
                variance = 0.0
            else:
                variance = float(pvariance(samples))
            per_agent_variance[agent_id] = variance
            all_variances.append(variance)

        global_variance = 0.0
        if all_variances:
            global_variance = sum(all_variances) / float(len(all_variances))

        return {
            "per_agent_variance": per_agent_variance,
            "global_variance": global_variance,
            "sample_count": max((len(series) for series in registry.trust_history.values()), default=0),
        }


class GovernanceFormalizationLayer:
    """Projection-driven deterministic governance state evolution."""

    def __init__(
        self,
        *,
        registry: AgentRegistry,
        relationship_engine: RelationshipWeightEngine | None = None,
        outcome_adapter: ProjectionOutcomeAdapter | None = None,
        stability_metric: TrustStabilityMetric | None = None,
    ) -> None:
        self._registry = registry
        self._relationship_engine = relationship_engine or RelationshipWeightEngine()
        self._outcome_adapter = outcome_adapter or ProjectionOutcomeAdapter()
        self._stability_metric = stability_metric or TrustStabilityMetric()

    @property
    def registry(self) -> AgentRegistry:
        return self._registry

    def ingest_projection_delta(
        self,
        *,
        previous_view: Mapping[str, Any] | None,
        current_view: Mapping[str, Any] | None,
    ) -> Dict[str, Any]:
        observations = self._outcome_adapter.derive_observations(
            previous_view=previous_view,
            current_view=current_view,
            known_agents=self._registry.agent_ids,
        )
        self._relationship_engine.apply_observations(self._registry, observations)
        stability = self._stability_metric.compute(self._registry)
        return {
            "registry": self._registry.to_dict(),
            "observations": [observation.as_dict() for observation in observations],
            "stability": stability,
        }
