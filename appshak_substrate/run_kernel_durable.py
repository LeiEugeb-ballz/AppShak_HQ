from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from appshak_substrate.kernel_compat import build_kernel_with_substrate


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run AppShak kernel with durable substrate bus.")
    parser.add_argument("--hours", type=float, default=24.0)
    parser.add_argument("--heartbeat-interval", type=float, default=15.0)
    parser.add_argument("--event-poll-timeout", type=float, default=1.0)
    parser.add_argument("--memory-root", type=str, default="appshak_state")
    parser.add_argument("--mailstore-db", type=str, default="appshak_state/substrate/mailstore.db")
    parser.add_argument("--mailstore-lease-seconds", type=float, default=15.0)
    parser.add_argument("--whitelist", nargs="*", default=["api.example.com"])
    parser.add_argument("--allow-real-world-impact", action="store_true")
    parser.add_argument("--retry-max", type=int, default=3)
    parser.add_argument("--cooldown-seconds", type=int, default=60)
    return parser


async def _run(args: argparse.Namespace) -> None:
    config = {
        "heartbeat_interval": args.heartbeat_interval,
        "event_poll_timeout": args.event_poll_timeout,
        "memory_root": args.memory_root,
        "endpoint_whitelist": args.whitelist,
        "allow_real_world_impact": args.allow_real_world_impact,
        "safeguard_retry_max": args.retry_max,
        "cooldown_timer_seconds": args.cooldown_seconds,
        "mailstore_lease_seconds": args.mailstore_lease_seconds,
    }
    bundle = build_kernel_with_substrate(
        config=config,
        db_path=Path(args.mailstore_db),
        consumer_id="kernel",
    )
    runner = asyncio.create_task(bundle.kernel.start())
    try:
        await asyncio.sleep(max(0.0, args.hours) * 3600.0)
    finally:
        await bundle.kernel.shutdown()
        if not runner.done():
            runner.cancel()
            await asyncio.gather(runner, return_exceptions=True)


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
