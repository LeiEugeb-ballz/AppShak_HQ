from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, Mapping

from appshak_phase4.orchestrator import Phase4Orchestrator


class Phase4Runner:
    def __init__(self, orchestrator: Phase4Orchestrator | None = None) -> None:
        self._orchestrator = orchestrator or Phase4Orchestrator()

    def run_once(
        self,
        *,
        replay_snapshot: Mapping[str, Any] | None = None,
        replay_path: str | Path | None = None,
    ) -> Dict[str, Any]:
        return self._orchestrator.run_phase4_cycle(
            replay_snapshot=replay_snapshot,
            replay_path=replay_path,
        )

    def run_continuous(
        self,
        *,
        poll_interval_seconds: float = 1.0,
        max_cycles: int | None = None,
        replay_path: str | Path | None = None,
    ) -> list[Dict[str, Any]]:
        interval = max(0.0, float(poll_interval_seconds))
        cycle_limit = int(max_cycles) if max_cycles is not None else None

        completed: list[Dict[str, Any]] = []
        while True:
            completed.append(self.run_once(replay_path=replay_path))
            if cycle_limit is not None and len(completed) >= max(0, cycle_limit):
                break
            if interval > 0:
                time.sleep(interval)
        return completed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run AppShak Phase 4 orchestration pipeline.")
    parser.add_argument("--continuous", action="store_true")
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--max-cycles", type=int, default=0)
    parser.add_argument("--replay-path", type=str, default="")
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    runner = Phase4Runner()

    replay_path = str(args.replay_path).strip() or None
    if args.continuous:
        max_cycles = int(args.max_cycles) if int(args.max_cycles) > 0 else None
        output = runner.run_continuous(
            poll_interval_seconds=max(0.0, float(args.poll_interval)),
            max_cycles=max_cycles,
            replay_path=replay_path,
        )
    else:
        output = runner.run_once(replay_path=replay_path)

    print(json.dumps(output, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
