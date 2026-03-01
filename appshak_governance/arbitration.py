from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping

from .constants import BOARDROOM_DECISION_THRESHOLD, BOARDROOM_REASONING_MAX, BOARDROOM_REASONING_MIN
from .registry import AgentRegistry
from .utils import as_float, clamp, normalize_agent_id


@dataclass(frozen=True)
class ArbitrationVote:
    agent_id: str
    reasoning_score: float
    authority_level: float
    trust_weight: float
    decision_score: float

    def as_dict(self) -> Dict[str, object]:
        return {
            "agent_id": self.agent_id,
            "reasoning_score": self.reasoning_score,
            "authority_level": self.authority_level,
            "trust_weight": self.trust_weight,
            "decision_score": self.decision_score,
        }


@dataclass(frozen=True)
class ArbitrationResult:
    target_agent: str
    threshold: float
    aggregate_score: float
    approved: bool
    votes: List[ArbitrationVote]

    def as_dict(self) -> Dict[str, object]:
        return {
            "target_agent": self.target_agent,
            "threshold": self.threshold,
            "aggregate_score": self.aggregate_score,
            "approved": self.approved,
            "votes": [vote.as_dict() for vote in self.votes],
        }


class BoardroomArbitrator:
    THRESHOLD = BOARDROOM_DECISION_THRESHOLD

    def arbitrate(
        self,
        *,
        registry: AgentRegistry,
        target_agent: str,
        ballots: Iterable[Mapping[str, object]],
    ) -> ArbitrationResult:
        target_id = normalize_agent_id(target_agent)
        if not target_id or not registry.has_agent(target_id):
            return ArbitrationResult(
                target_agent=target_id,
                threshold=self.THRESHOLD,
                aggregate_score=0.0,
                approved=False,
                votes=[],
            )

        votes: List[ArbitrationVote] = []
        for ballot in ballots:
            voter_id = normalize_agent_id(ballot.get("agent_id"))
            if not voter_id or not registry.has_agent(voter_id):
                continue

            reasoning_score = clamp(
                as_float(ballot.get("reasoning_score"), default=0.0),
                BOARDROOM_REASONING_MIN,
                BOARDROOM_REASONING_MAX,
            )
            authority_level = registry.authority_level(voter_id)
            trust_weight = registry.trust_weight(voter_id, target_id)
            decision_score = reasoning_score * authority_level * trust_weight
            votes.append(
                ArbitrationVote(
                    agent_id=voter_id,
                    reasoning_score=reasoning_score,
                    authority_level=authority_level,
                    trust_weight=trust_weight,
                    decision_score=decision_score,
                )
            )

        aggregate_score = 0.0
        if votes:
            aggregate_score = sum(vote.decision_score for vote in votes) / float(len(votes))
        approved = aggregate_score >= self.THRESHOLD
        return ArbitrationResult(
            target_agent=target_id,
            threshold=self.THRESHOLD,
            aggregate_score=aggregate_score,
            approved=approved,
            votes=votes,
        )
