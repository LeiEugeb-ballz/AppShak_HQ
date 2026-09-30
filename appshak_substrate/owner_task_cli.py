"""Explicit owner-task intake and inspection; creation never dispatches work."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from appshak_substrate.mailstore_sqlite import SQLiteMailStore
from appshak_substrate.tool_gateway import ToolGateway


def main() -> int:
    parser = argparse.ArgumentParser(description="Durable AppShak owner-task commands.")
    parser.add_argument("--db-path", required=True, help="Existing substrate SQLite database path.")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="Persist one owner objective without dispatching it.")
    create.add_argument("--owner-id", required=True)
    create.add_argument("--objective", required=True)
    create.add_argument("--authority-id", required=True)
    create.add_argument("--source-request-id", required=True)
    assign = commands.add_parser("assign", help="Bind a created task to an existing worker workspace.")
    assign.add_argument("--task-id", required=True)
    assign.add_argument("--agent-id", required=True)
    assign.add_argument("--worktree", required=True)
    assign.add_argument("--authority-id", required=True)
    assign.add_argument("--actor-id", required=True)
    assign.add_argument("--source-ref", required=True)
    inspect = commands.add_parser("inspect", help="Show durable task, history, attempts and artifact references.")
    inspect.add_argument("--task-id", required=True)
    args = parser.parse_args()
    store = SQLiteMailStore(args.db_path)
    if args.command == "create":
        result = store.create_owner_task(owner_id=args.owner_id, objective=args.objective,
                                         authority_id=args.authority_id,
                                         source_request_id=args.source_request_id)
    elif args.command == "assign":
        worktree = Path(args.worktree)
        if not worktree.is_dir():
            parser.error("--worktree must be an existing directory")
        result = store.assign_owner_task(
            task_id=args.task_id, agent_id=args.agent_id,
            workspace_id=ToolGateway.workspace_identity(args.agent_id, worktree),
            authority_id=args.authority_id, actor_id=args.actor_id, source_ref=args.source_ref,
        )
    else:
        result = store.get_owner_task(args.task_id)
        if result is None:
            parser.error("owner task does not exist")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
