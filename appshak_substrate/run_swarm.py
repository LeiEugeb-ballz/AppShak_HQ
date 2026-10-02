from __future__ import annotations

import argparse
from pathlib import Path

from appshak_substrate.supervisor import Supervisor
from appshak_substrate.workspace_manager import WorkspaceManager


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run AppShak substrate swarm supervisor.")
    parser.add_argument("--agents", nargs="+", default=["recon", "forge", "command"])
    parser.add_argument("--durable", action="store_true", help="Use durable SQLite substrate (default behavior).")
    parser.add_argument("--db-path", type=str, default="appshak_state/substrate/mailstore.db")
    parser.add_argument("--initialize-db", action="store_true",
                        help="Explicitly create the durable database on first startup.")
    parser.add_argument("--duration-seconds", type=float, default=60.0)
    parser.add_argument("--worktrees", action="store_true", help="Enable per-agent git worktree isolation.")
    parser.add_argument("--repo-root", type=str, default=".")
    parser.add_argument("--workspaces-root", type=str, default="workspaces")
    parser.add_argument("--reset-worktrees", action="store_true")
    parser.add_argument("--include-unrouted", action="store_true")
    parser.add_argument("--max-restarts", type=int, default=5)
    parser.add_argument("--restart-backoff-seconds", type=float, default=1.0)
    parser.add_argument("--heartbeat-interval-seconds", type=float, default=5.0)
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    db_path = Path(args.db_path)
    if db_path.exists() and not db_path.is_file():
        parser.error(f"Canonical mailstore path is not a file: {db_path}")
    if not db_path.exists() and not args.initialize_db:
        parser.error(f"Canonical mailstore is missing: {db_path}; use --initialize-db explicitly on first startup")
    agents = [str(agent).strip().lower() for agent in args.agents if str(agent).strip()]
    if not agents:
        raise ValueError("At least one agent is required.")

    workspace_roots = None
    if args.worktrees:
        manager = WorkspaceManager(
            repo_root=Path(args.repo_root),
            workspaces_root=args.workspaces_root,
            reset_on_ensure=args.reset_worktrees,
        )
        ensured = manager.ensure_worktrees(agents)
        workspace_roots = {agent: str(path) for agent, path in ensured.items()}

    supervisor = Supervisor(
        db_path=Path(args.db_path),
        agent_ids=agents,
        include_unrouted=args.include_unrouted,
        max_restarts=args.max_restarts,
        restart_backoff_seconds=args.restart_backoff_seconds,
        heartbeat_interval_seconds=args.heartbeat_interval_seconds,
        workspace_roots=workspace_roots,
    )

    try:
        supervisor.run(duration_seconds=args.duration_seconds)
    except KeyboardInterrupt:
        supervisor.stop()


if __name__ == "__main__":
    main()
