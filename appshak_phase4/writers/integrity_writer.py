from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping

from appshak_integrity.report import build_integrity_report
from appshak_integrity.store import IntegrityReportStore
from appshak_integrity.utils import canonical_hash

from appshak_phase4.adapters import phase4_to_projection_snapshot
from appshak_phase4.contracts import ValidationResult


class IntegrityWriter:
    def __init__(self, store: IntegrityReportStore | None = None) -> None:
        self._store = store or IntegrityReportStore()

    def write(
        self,
        validated: ValidationResult,
        *,
        runtime_context: Mapping[str, Any] | None = None,
    ) -> Dict[str, Path]:
        projection_snapshot = phase4_to_projection_snapshot(validated.snapshot)
        report = build_integrity_report(
            window="phase4",
            projection_snapshot=projection_snapshot,
            governance_entries=[],
            replay_result={
                "hashes_equal": True,
                "chain_valid": len(validated.integrity.violations) == 0,
            },
            generated_at=validated.integrity.timestamp,
        )
        report["phase4"] = {
            "record_type": "integrity",
            "run_id": validated.integrity.run_id,
            "consistency_score": float(validated.integrity.consistency_score),
            "violations": [dict(item) for item in validated.integrity.violations],
            "runtime": dict(runtime_context) if isinstance(runtime_context, Mapping) else {},
        }
        report["consistency_score"] = float(validated.integrity.consistency_score)
        report["violations"] = [dict(item) for item in validated.integrity.violations]
        report = _without_nulls(report)
        report_no_hash = dict(report)
        report_no_hash.pop("report_hash", None)
        report["report_hash"] = canonical_hash(report_no_hash)
        return self._store.save(report)


def _without_nulls(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _without_nulls(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_without_nulls(item) for item in value]
    if value is None:
        return ""
    return value
