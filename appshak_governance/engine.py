from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence

from .arbitration import BoardroomArbitrator
from .ledger import GovernanceAuditLedger
from .projection_adapter import ProjectionOutcomeAdapter
from .registry import AgentRegistry, AgentRegistryStore
from .relationship import RelationshipWeightEngine
from .stability import TrustStabilityMetric
from .utils import canonical_hash
from .water_cooler import WaterCoolerPropagation


class GovernanceEngine:
    def __init__(
        self,
        *,
        registry: AgentRegistry,
        registry_store: AgentRegistryStore | None = None,
        ledger: GovernanceAuditLedger | None = None,
        outcome_adapter: ProjectionOutcomeAdapter | None = None,
        relationship_engine: RelationshipWeightEngine | None = None,
        arbitrator: BoardroomArbitrator | None = None,
        water_cooler: WaterCoolerPropagation | None = None,
        stability_metric: TrustStabilityMetric | None = None,
    ) -> None:
        self.registry = registry
        self.registry_store = registry_store
        self.ledger = ledger
        self.outcome_adapter = outcome_adapter or ProjectionOutcomeAdapter()
        self.relationship_engine = relationship_engine or RelationshipWeightEngine()
        self.arbitrator = arbitrator or BoardroomArbitrator()
        self.water_cooler = water_cooler or WaterCoolerPropagation()
        self.stability_metric = stability_metric or TrustStabilityMetric()

    @classmethod
    def from_agent_definitions(
        cls,
        *,
        agent_definitions: Sequence[Mapping[str, Any]],
        registry_path: Path | str | None = None,
        ledger_path: Path | str | None = None,
    ) -> "GovernanceEngine":
        registry_store = AgentRegistryStore(registry_path) if registry_path is not None else None
        if registry_store is None:
            registry = AgentRegistry.from_definitions(agent_definitions)
        else:
            loaded = registry_store.load()
            if loaded.get("agents"):
                registry = AgentRegistry(loaded)
            else:
                registry = AgentRegistry.from_definitions(agent_definitions)
                registry_store.save_atomic(registry.snapshot())
        ledger = GovernanceAuditLedger(ledger_path) if ledger_path is not None else None
        return cls(registry=registry, registry_store=registry_store, ledger=ledger)

    def ingest_projection_delta(
        self,
        *,
        previous_view: Mapping[str, object] | None,
        current_view: Mapping[str, object] | None,
    ) -> Dict[str, object]:
        current = current_view if isinstance(current_view, Mapping) else {}
        timestamp = str(current.get("timestamp", "")).strip()
        outcomes = self.outcome_adapter.derive_outcomes(
            previous_view=previous_view,
            current_view=current,
            known_agents=self.registry.agent_ids,
        )
        trust_changes = self.relationship_engine.apply_outcomes(registry=self.registry, outcomes=outcomes)
        lesson = self.water_cooler.maybe_propagate(
            registry=self.registry,
            previous_view=previous_view,
            current_view=current_view,
        )
        if lesson.get("triggered"):
            self.registry.record_noop_update(updated_at=timestamp)
            if self.ledger is not None:
                self.ledger.append(entry_type="WATER_COOLER_LESSON", payload=lesson, timestamp=timestamp)

        stability = self.stability_metric.compute(registry=self.registry)

        for change in trust_changes:
            if self.ledger is not None:
                self.ledger.append(entry_type="TRUST_CHANGE", payload=change.as_dict(), timestamp=change.source_timestamp)

        if self.ledger is not None:
            registry_snapshot = self.registry.snapshot()
            self.ledger.append(
                entry_type="REGISTRY_UPDATE",
                payload={
                    "registry": registry_snapshot,
                    "registry_hash": canonical_hash(registry_snapshot),
                },
                timestamp=self.registry.last_updated,
            )
            self.ledger.append(
                entry_type="TRUST_STABILITY_METRIC",
                payload=stability,
                timestamp=self.registry.last_updated,
            )

        persisted_registry = self.registry.snapshot()
        if self.registry_store is not None:
            persisted_registry = self.registry_store.save_atomic(persisted_registry)

        return {
            "registry": persisted_registry,
            "registry_hash": canonical_hash(persisted_registry),
            "outcomes": outcomes,
            "trust_changes": [change.as_dict() for change in trust_changes],
            "water_cooler": lesson,
            "stability_metric": stability,
        }

    def arbitrate(
        self,
        *,
        target_agent: str,
        ballots: Iterable[Mapping[str, object]],
        timestamp: str,
    ) -> Dict[str, object]:
        result = self.arbitrator.arbitrate(registry=self.registry, target_agent=target_agent, ballots=ballots)
        payload = result.as_dict()
        if self.ledger is not None:
            self.ledger.append(entry_type="ARBITRATION_OUTCOME", payload=payload, timestamp=timestamp)
        return payload

    def reconstruct_registry_from_ledger(self) -> Dict[str, object]:
        if self.ledger is None:
            return self.registry.snapshot()
        return self.ledger.reconstruct_registry(fallback_registry=self.registry.snapshot())
