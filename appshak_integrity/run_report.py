from __future__ import annotations

import argparse
import json
from pathlib import Path

from .report import build_integrity_report, load_governance_entries, load_integrity_report, load_snapshot
from .store import IntegrityReportStore, render_markdown_report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate deterministic AppShak integrity report.")
    parser.add_argument("--window", type=str, default="7d")
    parser.add_argument("--projection-view", type=str, default="appshak_state/projection/view.json")
    parser.add_argument("--governance-ledger", type=str, default="appshak_state/governance/ledger.jsonl")
    parser.add_argument("--replay-result", type=str, default="appshak_state/governance/replay_latest.json")
    parser.add_argument("--out-root", type=str, default="appshak_state/integrity")
    parser.add_argument("--no-markdown", action="store_true")
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    snapshot = load_snapshot(args.projection_view)
    entries = load_governance_entries(args.governance_ledger)
    replay_payload = load_integrity_report(args.replay_result)
    report = build_integrity_report(
        window=args.window,
        projection_snapshot=snapshot,
        governance_entries=entries,
        replay_result=replay_payload,
    )

    markdown = None if args.no_markdown else render_markdown_report(report)
    store = IntegrityReportStore(args.out_root)
    saved = store.save(report, markdown=markdown)

    print(
        json.dumps(
            {
                "saved": {key: str(path) for key, path in saved.items()},
                "report_hash": report.get("report_hash"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
