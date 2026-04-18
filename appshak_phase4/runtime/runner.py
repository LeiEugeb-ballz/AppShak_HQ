from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, Mapping

from appshak_phase4.orchestrator import Phase4Orchestrator
from appshak_phase4.runtime.autonomy_loop import AutonomyLoopEngine
from appshak_phase4.runtime.stability import StabilityRecoveryWrapper


class Phase4Runner:
    def __init__(
        self,
        orchestrator: Phase4Orchestrator | None = None,
        *,
        runtime_root: str | Path = "appshak_state/phase4/runtime",
        watchdog_timeout_seconds: float = 8.0,
        heartbeat_seconds: float = 15.0,
        max_retries: int = 2,
    ) -> None:
        self._orchestrator = orchestrator or Phase4Orchestrator()
        self._stability = StabilityRecoveryWrapper(
            root=runtime_root,
            watchdog_timeout_seconds=watchdog_timeout_seconds,
        )
        self._autonomy = AutonomyLoopEngine(
            orchestrator=self._orchestrator,
            stability=self._stability,
            heartbeat_seconds=heartbeat_seconds,
            max_retries=max_retries,
        )

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

    def run_autonomy_cycle(
        self,
        *,
        replay_snapshot: Mapping[str, Any] | None = None,
        replay_path: str | Path | None = None,
    ) -> Dict[str, Any]:
        return self._autonomy.run_cycle(
            replay_snapshot=replay_snapshot,
            replay_path=str(replay_path) if replay_path is not None else None,
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

    def run_autonomy_continuous(self, *, max_cycles: int | None = None) -> list[Dict[str, Any]]:
        return self._autonomy.run_continuous(max_cycles=max_cycles)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run AppShak Phase 4 orchestration pipeline.")
    parser.add_argument("--continuous", action="store_true")
    parser.add_argument("--autonomy", action="store_true")
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--heartbeat-seconds", type=float, default=15.0)
    parser.add_argument("--watchdog-timeout-seconds", type=float, default=8.0)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--runtime-root", type=str, default="appshak_state/phase4/runtime")
    parser.add_argument("--max-cycles", type=int, default=0)
    parser.add_argument("--replay-path", type=str, default="")
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    runner = Phase4Runner(
        runtime_root=args.runtime_root,
        watchdog_timeout_seconds=max(1.0, float(args.watchdog_timeout_seconds)),
        heartbeat_seconds=max(10.0, min(30.0, float(args.heartbeat_seconds))),
        max_retries=max(0, int(args.max_retries)),
    )

    replay_path = str(args.replay_path).strip() or None
    if args.autonomy and args.continuous:
        max_cycles = int(args.max_cycles) if int(args.max_cycles) > 0 else None
        output = runner.run_autonomy_continuous(max_cycles=max_cycles)
    elif args.autonomy:
        output = runner.run_autonomy_cycle(replay_path=replay_path)
    elif args.continuous:
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
