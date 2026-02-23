from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from appshak_substrate.mailstore_sqlite import SQLiteMailStore
from appshak_substrate.policy import ToolPolicy
from appshak_substrate.tool_gateway import ToolGateway
from appshak_substrate.workspace_manager import WorkspaceManager


def _run(cmd: list[str], cwd: Path) -> None:
    result = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{result.stderr or result.stdout}")


class TestToolGatewayEnforcement(unittest.TestCase):
    def test_worktree_creation_and_policy_enforcement(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appshak_gateway_") as temp_dir:
            root = Path(temp_dir)
            repo = root / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            _run(["git", "init"], cwd=repo)
            _run(["git", "config", "user.email", "test@example.com"], cwd=repo)
            _run(["git", "config", "user.name", "Test"], cwd=repo)
            (repo / "README.md").write_text("test\n", encoding="utf-8")
            _run(["git", "add", "README.md"], cwd=repo)
            _run(["git", "commit", "-m", "init"], cwd=repo)

            manager = WorkspaceManager(repo_root=repo, workspaces_root=repo / "workspaces")
            worktrees = manager.ensure_worktrees(["recon", "forge", "command"])
            self.assertTrue(worktrees["recon"].exists())
            self.assertTrue(worktrees["forge"].exists())
            self.assertTrue(worktrees["command"].exists())

            store = SQLiteMailStore(root / "mailstore.db")
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
                    "payload": {"argv": ["git", "status"], "idempotency_key": "deny-non-chief"},
                }
            )
            self.assertFalse(denied_non_chief.allowed)

            denied_traversal = gateway.execute(
                {
                    "agent_id": "forge",
                    "authorized_by": "command",
                    "action_type": "WRITE_FILE",
                    "working_dir": str(worktrees["forge"]),
                    "payload": {
                        "path": "../escape.txt",
                        "content": "blocked",
                        "idempotency_key": "deny-traversal",
                    },
                }
            )
            self.assertFalse(denied_traversal.allowed)

            allowed = gateway.execute(
                {
                    "agent_id": "command",
                    "authorized_by": "command",
                    "action_type": "RUN_CMD",
                    "working_dir": str(worktrees["command"]),
                    "payload": {"argv": ["git", "status"], "idempotency_key": "allow-status"},
                }
            )
            self.assertTrue(allowed.allowed)
            self.assertEqual(allowed.return_code, 0)

            duplicate = gateway.execute(
                {
                    "agent_id": "command",
                    "authorized_by": "command",
                    "action_type": "RUN_CMD",
                    "working_dir": str(worktrees["command"]),
                    "payload": {"argv": ["git", "status"], "idempotency_key": "allow-status"},
                }
            )
            self.assertFalse(duplicate.allowed)

            audits = store.list_tool_audit(limit=20)
            self.assertGreaterEqual(len(audits), 4)
            self.assertTrue(any(not row["allowed"] for row in audits))
            self.assertTrue(any(row["allowed"] for row in audits))


if __name__ == "__main__":
    unittest.main()
