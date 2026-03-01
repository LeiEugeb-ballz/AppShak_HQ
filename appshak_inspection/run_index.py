from __future__ import annotations

import argparse
import json
from pathlib import Path

from appshak_governance.ledger import GovernanceAuditLedger

from appshak_integrity.store import IntegrityReportStore

from .indexer import build_inspection_index
from .store import InspectionIndexStore


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build deterministic inspection index.")
    parser.add_argument("--projection-view", type=str, default="appshak_state/projection/view.json")
    parser.add_argument("--governance-ledger", type=str, default="appshak_state/governance/ledger.jsonl")
    parser.add_argument("--integrity-root", type=str, default="appshak_state/integrity")
    parser.add_argument("--inspection-root", type=str, default="appshak_state/inspection")
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    projection_path = Path(args.projection_view)
    if projection_path.exists():
        projection_payload = json.loads(projection_path.read_text(encoding="utf-8"))
        if not isinstance(projection_payload, dict):
            projection_payload = {}
    else:
        projection_payload = {}

    governance_entries = GovernanceAuditLedger(args.governance_ledger).read_entries()
    integrity_report = IntegrityReportStore(args.integrity_root).load_latest()
    index = build_inspection_index(
        projection_snapshot=projection_payload,
        governance_entries=governance_entries,
        integrity_report=integrity_report,
    )
    saved = InspectionIndexStore(args.inspection_root).save(index)
    print(
        json.dumps(
            {
                "index_hash": index.get("index_hash"),
                "saved": {key: str(path) for key, path in saved.items()},
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
