from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, Iterable, Optional


class WorkspaceManager:
    """Creates and validates per-agent git worktree isolation."""

    def __init__(
        self,
        *,
        repo_root: str | Path,
        workspaces_root: str | Path = "workspaces",
        baseline_branch: Optional[str] = None,
        reset_on_ensure: bool = False,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.workspaces_root = (
            Path(workspaces_root).resolve()
            if Path(workspaces_root).is_absolute()
            else (self.repo_root / workspaces_root).resolve()
        )
        self.reset_on_ensure = reset_on_ensure
        self.baseline_branch = baseline_branch or self._detect_current_branch()

    def ensure_worktrees(self, agent_ids: Iterable[str]) -> Dict[str, Path]:
        self._assert_git_repo()
        self.workspaces_root.mkdir(parents=True, exist_ok=True)
        result: Dict[str, Path] = {}

        for agent_id in agent_ids:
            normalized = str(agent_id).strip().lower()
            if not normalized:
                raise ValueError("Agent id cannot be empty.")
            path = (self.workspaces_root / normalized).resolve()
            if not path.exists():
                self._run_git(
                    "worktree",
                    "add",
                    str(path),
                    self.baseline_branch,
                )
            if self.reset_on_ensure:
                self.reset_worktree(normalized)
            self._ensure_clean(path)
            result[normalized] = path
        return result

    def worktree_for(self, agent_id: str) -> Path:
        path = (self.workspaces_root / str(agent_id).strip().lower()).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Missing worktree for agent '{agent_id}' at '{path}'.")
        return path

    def reset_worktree(self, agent_id: str) -> None:
        path = self.worktree_for(agent_id)
        self._run_git("-C", str(path), "reset", "--hard")
        self._run_git("-C", str(path), "clean", "-fd")
        self._run_git("-C", str(path), "checkout", self.baseline_branch)
        self._run_git("-C", str(path), "reset", "--hard", self.baseline_branch)

    def _ensure_clean(self, worktree_path: Path) -> None:
        result = self._run_git("-C", str(worktree_path), "status", "--porcelain")
        if result.stdout.strip():
            raise RuntimeError(f"Worktree '{worktree_path}' is not clean.")

    def _assert_git_repo(self) -> None:
        dot_git = self.repo_root / ".git"
        if not dot_git.exists():
            raise RuntimeError(f"repo_root '{self.repo_root}' is not a git repository.")

    def _detect_current_branch(self) -> str:
        self._assert_git_repo()
        res = self._run_git("rev-parse", "--abbrev-ref", "HEAD")
        branch = res.stdout.strip()
        if not branch:
            raise RuntimeError("Could not determine current git branch for baseline worktree creation.")
        return branch

    def _run_git(self, *args: str) -> subprocess.CompletedProcess[str]:
        cmd = ["git", "-C", str(self.repo_root), *args]
        result = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Git command failed ({' '.join(cmd)}): {result.stderr.strip() or result.stdout.strip()}"
            )
        return result
