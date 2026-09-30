from __future__ import annotations

import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from appshak_substrate.mailstore_sqlite import SQLiteMailStore
from appshak_substrate.policy import ToolPolicy
from appshak_substrate.tool_gateway import ToolGateway
from appshak_substrate.workspace_manager import WorkspaceManager, WorkspaceStateError


def _run(command: list[str], cwd: Path) -> None:
    result = subprocess.run(command, cwd=str(cwd), text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)


def _repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    _run(["git", "init"], repo)
    _run(["git", "config", "user.email", "wp1@example.com"], repo)
    _run(["git", "config", "user.name", "WP1"], repo)
    (repo / "README.md").write_text("baseline\n", encoding="utf-8")
    _run(["git", "add", "README.md"], repo)
    _run(["git", "commit", "-m", "init"], repo)
    return repo


def _authority(agent: str, worktree: Path, operation: str, source: str) -> dict[str, str]:
    return {
        "authority_id": f"authority:{source}",
        "source_request_id": source,
        "workspace_id": ToolGateway.workspace_identity(agent, worktree),
        "requested_operation": operation,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


class TestS1Wp1WorkspaceAuthority(unittest.TestCase):
    def test_workspace_survives_restart(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appshak_wp1_restart_") as temp_dir:
            root = Path(temp_dir)
            repo = _repo(root)
            manager = WorkspaceManager(repo_root=repo, workspaces_root=repo / "workspaces")
            first = manager.ensure_worktrees(["forge"])["forge"]
            sentinel = first / "sentinel.txt"
            sentinel.write_text("preserve-me\n", encoding="utf-8")

            second = WorkspaceManager(repo_root=repo, workspaces_root=repo / "workspaces")
            reused = second.ensure_worktrees(["forge"])["forge"]

            self.assertEqual(reused, first)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve-me\n")

    def test_dirty_workspace_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appshak_wp1_dirty_") as temp_dir:
            root = Path(temp_dir)
            repo = _repo(root)
            manager = WorkspaceManager(repo_root=repo, workspaces_root=repo / "workspaces")
            worktree = manager.ensure_worktrees(["forge"])["forge"]
            (worktree / "README.md").write_text("dirty\n", encoding="utf-8")
            (worktree / "untracked.txt").write_text("keep\n", encoding="utf-8")

            WorkspaceManager(repo_root=repo, workspaces_root=repo / "workspaces").ensure_worktrees(["forge"])

            self.assertEqual((worktree / "README.md").read_text(encoding="utf-8"), "dirty\n")
            self.assertTrue((worktree / "untracked.txt").exists())

    def test_destructive_mode_requires_explicit_opt_in(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appshak_wp1_reset_") as temp_dir:
            root = Path(temp_dir)
            repo = _repo(root)
            manager = WorkspaceManager(repo_root=repo, workspaces_root=repo / "workspaces")
            worktree = manager.ensure_worktrees(["forge"])["forge"]
            (worktree / "README.md").write_text("dirty\n", encoding="utf-8")
            sentinel = worktree / "untracked.txt"
            sentinel.write_text("remove-only-by-opt-in\n", encoding="utf-8")

            WorkspaceManager(
                repo_root=repo,
                workspaces_root=repo / "workspaces",
                reset_on_ensure=True,
            ).ensure_worktrees(["forge"])

            self.assertEqual((worktree / "README.md").read_text(encoding="utf-8"), "baseline\n")
            self.assertFalse(sentinel.exists())

    def test_unknown_workspace_fails_without_cleanup(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appshak_wp1_unknown_") as temp_dir:
            root = Path(temp_dir)
            repo = _repo(root)
            unknown = repo / "workspaces" / "forge"
            unknown.mkdir(parents=True)
            sentinel = unknown / "sentinel.txt"
            sentinel.write_text("keep\n", encoding="utf-8")

            with self.assertRaises(WorkspaceStateError):
                WorkspaceManager(repo_root=repo, workspaces_root=repo / "workspaces").ensure_worktrees(["forge"])

            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep\n")

    def test_authority_is_required_and_recorded(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appshak_wp1_authority_") as temp_dir:
            root = Path(temp_dir)
            repo = _repo(root)
            worktree = WorkspaceManager(repo_root=repo, workspaces_root=repo / "workspaces").ensure_worktrees(["command"])["command"]
            store = SQLiteMailStore(root / "mailstore.db")
            gateway = ToolGateway(
                mail_store=store,
                policy=ToolPolicy(chief_agent_id="command"),
                workspace_roots={"command": worktree},
            )
            target = worktree / "unauthorized.txt"

            denied = gateway.execute(
                {
                    "agent_id": "command",
                    "action_type": "WRITE_FILE",
                    "working_dir": str(worktree),
                    "payload": {
                        "path": target.name,
                        "content": "must-not-write\n",
                        "idempotency_key": "wp1-missing-authority",
                    },
                }
            )
            self.assertFalse(denied.allowed)
            self.assertFalse(target.exists())
            self.assertIn("authority", denied.reason.lower())

            source = "wp1-authorized-request"
            authorized = gateway.execute(
                {
                    "agent_id": "command",
                    "action_type": "WRITE_FILE",
                    "working_dir": str(worktree),
                    "payload": {
                        "path": "authorized.txt",
                        "content": "attributed\n",
                        "idempotency_key": source,
                    },
                    **_authority("command", worktree, "WRITE_FILE", source),
                }
            )
            self.assertTrue(authorized.allowed)
            self.assertEqual((worktree / "authorized.txt").read_text(encoding="utf-8"), "attributed\n")

            audit = next(row for row in store.list_tool_audit(limit=10) if row["idempotency_key"] == source)
            self.assertEqual(audit["payload"]["authority_id"], f"authority:{source}")
            self.assertEqual(audit["payload"]["worker_id"], "command")
            self.assertEqual(audit["payload"]["source_request_id"], source)
            self.assertEqual(audit["payload"]["requested_operation"], "WRITE_FILE")


if __name__ == "__main__":
    unittest.main()
