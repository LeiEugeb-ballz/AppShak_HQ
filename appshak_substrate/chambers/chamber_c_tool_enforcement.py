from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from appshak_substrate.mailstore_sqlite import SQLiteMailStore
from appshak_substrate.policy import ToolPolicy
from appshak_substrate.tool_gateway import ToolGateway
from appshak_substrate.workspace_manager import WorkspaceManager


def _run(cmd: list[str], cwd: Path) -> None:
    result = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{result.stderr or result.stdout}")


def run_chamber() -> int:
    with tempfile.TemporaryDirectory(prefix="appshak_chamber_c_") as temp_dir:
        root = Path(temp_dir)
        repo = root / "repo"
        repo.mkdir(parents=True, exist_ok=True)
        _run(["git", "init"], cwd=repo)
        _run(["git", "config", "user.email", "chamber@example.com"], cwd=repo)
        _run(["git", "config", "user.name", "Chamber"], cwd=repo)
        (repo / "README.md").write_text("chamber-c\n", encoding="utf-8")
        _run(["git", "add", "README.md"], cwd=repo)
        _run(["git", "commit", "-m", "init"], cwd=repo)

        manager = WorkspaceManager(repo_root=repo, workspaces_root=repo / "workspaces")
        worktrees = manager.ensure_worktrees(["recon", "forge", "command"])
        db_path = root / "mailstore.db"
        store = SQLiteMailStore(db_path)
        gateway = ToolGateway(
            mail_store=store,
            policy=ToolPolicy(chief_agent_id="command"),
            workspace_roots=worktrees,
        )

        denied_non_chief = gateway.execute(
            {
                "agent_id": "forge",
                "action_type": "RUN_CMD",
                "working_dir": str(worktrees["forge"]),
                "payload": {"argv": ["git", "status"], "idempotency_key": "chamber-c-deny-non-chief"},
            }
        )
        denied_traversal = gateway.execute(
            {
                "agent_id": "forge",
                "authorized_by": "command",
                "action_type": "WRITE_FILE",
                "working_dir": str(worktrees["forge"]),
                "payload": {
                    "path": "../escape.txt",
                    "content": "blocked",
                    "idempotency_key": "chamber-c-deny-traversal",
                },
            }
        )
        allowed = gateway.execute(
            {
                "agent_id": "command",
                "authorized_by": "command",
                "action_type": "RUN_CMD",
                "working_dir": str(worktrees["command"]),
                "payload": {"argv": ["git", "status"], "idempotency_key": "chamber-c-allow"},
            }
        )
        duplicate = gateway.execute(
            {
                "agent_id": "command",
                "authorized_by": "command",
                "action_type": "RUN_CMD",
                "working_dir": str(worktrees["command"]),
                "payload": {"argv": ["git", "status"], "idempotency_key": "chamber-c-allow"},
            }
        )

        audits = store.list_tool_audit(limit=20)
        passed = (
            (not denied_non_chief.allowed)
            and (not denied_traversal.allowed)
            and allowed.allowed
            and (not duplicate.allowed)
            and len(audits) >= 4
        )

        print(f"Chamber C: {'PASS' if passed else 'FAIL'}")
        print(f"db_path={db_path}")
        print(f"denied_non_chief={denied_non_chief.reason}")
        print(f"denied_traversal={denied_traversal.reason}")
        print(f"allowed_return_code={allowed.return_code}")
        print(f"duplicate_reason={duplicate.reason}")
        print(f"audit_entries={len(audits)}")
        return 0 if passed else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Chamber C tool enforcement validation.")
    _ = parser.parse_args()
    raise SystemExit(run_chamber())


if __name__ == "__main__":
    main()
