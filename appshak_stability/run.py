from __future__ import annotations

import argparse
import json

from .runner import StabilityRunner


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run AppShak stability harness.")
    parser.add_argument("--duration-hours", type=float, required=True)
    parser.add_argument("--poll-interval-seconds", type=float, default=60.0)
    parser.add_argument("--checkpoint-every-cycles", type=int, default=5)
    parser.add_argument("--projection-view", type=str, default="appshak_state/projection/view.json")
    parser.add_argument("--governance-ledger", type=str, default="appshak_state/governance/ledger.jsonl")
    parser.add_argument("--integrity-root", type=str, default="appshak_state/integrity")
    parser.add_argument("--inspection-root", type=str, default="appshak_state/inspection")
    parser.add_argument("--stability-root", type=str, default="appshak_state/stability")
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    runner = StabilityRunner(
        duration_hours=args.duration_hours,
        poll_interval_seconds=args.poll_interval_seconds,
        checkpoint_every_cycles=args.checkpoint_every_cycles,
        projection_view_path=args.projection_view,
        governance_ledger_path=args.governance_ledger,
        integrity_root=args.integrity_root,
        inspection_root=args.inspection_root,
        stability_root=args.stability_root,
    )
    result = runner.run()
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
