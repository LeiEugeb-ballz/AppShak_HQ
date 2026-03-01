from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence

from .engine import GovernanceEngine
from .utils import canonical_hash


@dataclass(frozen=True)
class ReplayResult:
    final_registry_hash: str
    reconstructed_registry_hash: str
    chain_valid: bool
    hashes_equal: bool
    versions_processed: int

    def as_dict(self) -> Dict[str, object]:
        return {
            "final_registry_hash": self.final_registry_hash,
            "reconstructed_registry_hash": self.reconstructed_registry_hash,
            "chain_valid": self.chain_valid,
            "hashes_equal": self.hashes_equal,
            "versions_processed": self.versions_processed,
        }


class DeterministicReplayHarness:
    def run(
        self,
        *,
        agent_definitions: Sequence[Mapping[str, object]],
        projection_views: Iterable[Mapping[str, object]],
        registry_path: Path | str,
        ledger_path: Path | str,
    ) -> ReplayResult:
        engine = GovernanceEngine.from_agent_definitions(
            agent_definitions=agent_definitions,
            registry_path=registry_path,
            ledger_path=ledger_path,
        )
        previous_view: Mapping[str, object] | None = None
        for view in projection_views:
            engine.ingest_projection_delta(previous_view=previous_view, current_view=view)
            previous_view = view

        final_registry = engine.registry.snapshot()
        reconstructed = engine.reconstruct_registry_from_ledger()
        final_hash = canonical_hash(final_registry)
        reconstructed_hash = canonical_hash(reconstructed)
        chain_valid = True
        if engine.ledger is not None:
            chain_valid = engine.ledger.validate_hash_chain()
        return ReplayResult(
            final_registry_hash=final_hash,
            reconstructed_registry_hash=reconstructed_hash,
            chain_valid=chain_valid,
            hashes_equal=final_hash == reconstructed_hash,
            versions_processed=int(final_registry.get("version", 0)),
        )
