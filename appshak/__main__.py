from __future__ import annotations

import argparse
import asyncio

from appshak import AppShakKernel


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run AppShak kernel.")
    parser.add_argument("--hours", type=float, default=24.0, help="How long to run before shutdown.")
    parser.add_argument("--heartbeat-interval", type=float, default=15.0)
    parser.add_argument("--event-poll-timeout", type=float, default=1.0)
    parser.add_argument("--memory-root", type=str, default="appshak_state")
    parser.add_argument("--whitelist", nargs="*", default=["api.example.com"])
    parser.add_argument("--allow-real-world-impact", action="store_true")
    parser.add_argument("--retry-max", type=int, default=3)
    parser.add_argument("--cooldown-seconds", type=int, default=60)
    return parser


async def _run(args: argparse.Namespace) -> None:
    kernel = AppShakKernel(
        {
            "heartbeat_interval": args.heartbeat_interval,
            "event_poll_timeout": args.event_poll_timeout,
            "memory_root": args.memory_root,
            "endpoint_whitelist": args.whitelist,
            "allow_real_world_impact": args.allow_real_world_impact,
            "safeguard_retry_max": args.retry_max,
            "cooldown_timer_seconds": args.cooldown_seconds,
        }
    )
    runner = asyncio.create_task(kernel.start())
    try:
        await asyncio.sleep(max(0.0, args.hours) * 3600.0)
    finally:
        await kernel.shutdown()
        if not runner.done():
            runner.cancel()
            await asyncio.gather(runner, return_exceptions=True)


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
