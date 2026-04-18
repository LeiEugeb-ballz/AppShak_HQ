from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping

from appshak_phase4.adapters import projection_to_phase4_snapshot
from appshak_phase4.pipeline import ProjectionExtractor, SnapshotNormalizer, SnapshotValidator
from appshak_phase4.writers import InspectionWriter, IntegrityWriter


class Phase4Orchestrator:
    def __init__(
        self,
        *,
        extractor: ProjectionExtractor | None = None,
        normalizer: SnapshotNormalizer | None = None,
        validator: SnapshotValidator | None = None,
        inspection_writer: InspectionWriter | None = None,
        integrity_writer: IntegrityWriter | None = None,
    ) -> None:
        self.extractor = extractor or ProjectionExtractor()
        self.normalizer = normalizer or SnapshotNormalizer()
        self.validator = validator or SnapshotValidator()
        self.inspection_writer = inspection_writer or InspectionWriter()
        self.integrity_writer = integrity_writer or IntegrityWriter()

    def run_phase4_cycle(
        self,
        *,
        replay_snapshot: Mapping[str, Any] | None = None,
        replay_path: str | Path | None = None,
        runtime_context: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        projection_snapshot = self.extractor.get_snapshot(
            replay_snapshot=replay_snapshot,
            replay_path=replay_path,
        )
        phase4_snapshot = projection_to_phase4_snapshot(projection_snapshot)
        normalized = self.normalizer.normalize(phase4_snapshot)
        validated = self.validator.validate(normalized)

        inspection_saved = self.inspection_writer.write(validated, runtime_context=runtime_context)
        integrity_saved = self.integrity_writer.write(validated, runtime_context=runtime_context)
        return {
            "run_id": normalized.run_id,
            "timestamp": normalized.timestamp,
            "inspection_pointer_path": str(inspection_saved.get("pointer_path", "")),
            "integrity_pointer_path": str(integrity_saved.get("latest_path", "")),
            "inspection_record": validated.inspection.to_dict(),
            "integrity_record": validated.integrity.to_dict(),
            "runtime_context": dict(runtime_context) if isinstance(runtime_context, Mapping) else {},
        }


def run_phase4_cycle(
    *,
    replay_snapshot: Mapping[str, Any] | None = None,
    replay_path: str | Path | None = None,
    runtime_context: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    orchestrator = Phase4Orchestrator()
    return orchestrator.run_phase4_cycle(
        replay_snapshot=replay_snapshot,
        replay_path=replay_path,
        runtime_context=runtime_context,
    )
