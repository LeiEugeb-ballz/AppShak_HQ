from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from appshak_substrate.agent_runtime import AgentRuntime
from appshak_substrate.mailstore_sqlite import SQLiteMailStore
from appshak_substrate.policy import ToolPolicy
from appshak_substrate.tool_gateway import ToolGateway


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AppShak substrate worker process.")
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--worktree", required=True)
    parser.add_argument("--consumer-id", required=True)
    parser.add_argument("--log-path", required=True)
    parser.add_argument("--claim-timeout", type=float, default=1.0)
    parser.add_argument("--lease-seconds", type=float, default=15.0)
    parser.add_argument("--heartbeat-interval-seconds", type=float, default=1.0)
    parser.add_argument("--include-unrouted", action="store_true")
    parser.add_argument("--chief-agent-id", type=str, default="command")
    parser.add_argument("--command-timeout-seconds", type=float, default=120.0)
    return parser


def _build_runtime(
    *,
    args: argparse.Namespace,
    mail_store: SQLiteMailStore,
) -> AgentRuntime:
    workspace_roots = {args.agent_id: args.worktree}
    tool_gateway: Optional[ToolGateway] = None
    if workspace_roots:
        tool_gateway = ToolGateway(
            mail_store=mail_store,
            policy=ToolPolicy(chief_agent_id=args.chief_agent_id),
            workspace_roots=workspace_roots,
            command_timeout_seconds=args.command_timeout_seconds,
        )

    runtime_log_path = str(Path(args.log_path).with_suffix(".runtime.jsonl"))

    return AgentRuntime(
        agent_id=args.agent_id,
        mail_store=mail_store,
        tool_gateway=tool_gateway,
        runtime_log_path=runtime_log_path,
    )


def _build_logger(log_path: str) -> logging.Logger:
    logger = logging.getLogger(f"substrate.worker.{Path(log_path).stem}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers = []
    destination = Path(log_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(destination, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


def _main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    mail_store = SQLiteMailStore(args.db_path, lease_seconds=args.lease_seconds)
    runtime = _build_runtime(args=args, mail_store=mail_store)
    logger = _build_logger(args.log_path)
    consumer_id = args.consumer_id
    worktree = str(Path(args.worktree).resolve())
    pid = os.getpid()
    logger.info(
        "WORKER_START agent_id=%s consumer_id=%s pid=%s worktree=%s db_path=%s",
        args.agent_id,
        consumer_id,
        pid,
        worktree,
        args.db_path,
    )

    stop_event = threading.Event()

    def _request_stop(*_: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)

    heartbeat_interval = max(0.2, float(args.heartbeat_interval_seconds))
    next_heartbeat = 0.0

    while not stop_event.is_set():
        now = time.monotonic()
        if now >= next_heartbeat:
            mail_store.record_worker_heartbeat(
                agent_id=args.agent_id,
                consumer_id=consumer_id,
                pid=pid,
            )
            next_heartbeat = now + heartbeat_interval

        event = mail_store.claim_next_event(
            consumer_id=consumer_id,
            timeout=args.claim_timeout,
            target_agent=args.agent_id,
            include_unrouted=bool(args.include_unrouted),
            lease_seconds=args.lease_seconds,
        )
        if event is None:
            continue
        if event.event_id is None:
            continue
        try:
            logger.info("EVENT_CLAIMED agent_id=%s event_id=%s type=%s", args.agent_id, event.event_id, event.type)
            runtime.handle_event(event)
            mail_store.ack_event(event.event_id, consumer_id=consumer_id)
            logger.info("EVENT_ACKED agent_id=%s event_id=%s", args.agent_id, event.event_id)
        except Exception as exc:
            mail_store.fail_event(event.event_id, repr(exc), consumer_id=consumer_id)
            logger.error("EVENT_FAILED agent_id=%s event_id=%s error=%s", args.agent_id, event.event_id, repr(exc))
    logger.info("WORKER_STOP agent_id=%s consumer_id=%s", args.agent_id, consumer_id)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
