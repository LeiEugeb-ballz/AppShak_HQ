from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping

from appshak_inspection.indexer import build_inspection_index
from appshak_inspection.store import InspectionIndexStore
from appshak_inspection.utils import canonical_hash

from appshak_phase4.adapters import phase4_to_projection_snapshot
from appshak_phase4.contracts import ValidationResult


class InspectionWriter:
    def __init__(self, store: InspectionIndexStore | None = None) -> None:
        self._store = store or InspectionIndexStore()

    def write(
        self,
        validated: ValidationResult,
        *,
        runtime_context: Mapping[str, Any] | None = None,
    ) -> Dict[str, Path]:
        projection_snapshot = phase4_to_projection_snapshot(validated.snapshot)
        integrity_payload = {
            "report_hash": f"phase4_{validated.snapshot.run_id}",
            "trust": {"trend": {}},
            "propagation": {},
            "arbitration": {},
        }
        index = build_inspection_index(
            projection_snapshot=projection_snapshot,
            governance_entries=[],
            integrity_report=integrity_payload,
        )
        index["generated_at"] = validated.inspection.timestamp
        index["phase4"] = {
            "record_type": "inspection",
            "run_id": validated.inspection.run_id,
            "anomalies": [dict(item) for item in validated.inspection.anomalies],
            "coverage": dict(validated.inspection.coverage),
            "runtime": dict(runtime_context) if isinstance(runtime_context, Mapping) else {},
        }
        index = _without_nulls(index)
        index_no_hash = dict(index)
        index_no_hash.pop("index_hash", None)
        index["index_hash"] = canonical_hash(index_no_hash)
        return self._store.save(index)


def _without_nulls(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _without_nulls(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_without_nulls(item) for item in value]
    if value is None:
        return ""
    return value
