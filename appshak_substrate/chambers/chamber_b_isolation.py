from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from appshak_substrate.workspace_manager import WorkspaceManager


def _run(cmd: list[str], cwd: Path) -> None:
    result = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{result.stderr or result.stdout}")


def run_chamber() -> int:
    with tempfile.TemporaryDirectory(prefix="appshak_chamber_b_") as temp_dir:
        repo = Path(temp_dir) / "repo"
        repo.mkdir(parents=True, exist_ok=True)
        _run(["git", "init"], cwd=repo)
        _run(["git", "config", "user.email", "chamber@example.com"], cwd=repo)
        _run(["git", "config", "user.name", "Chamber"], cwd=repo)
        (repo / "README.md").write_text("chamber-b\n", encoding="utf-8")
        _run(["git", "add", "README.md"], cwd=repo)
        _run(["git", "commit", "-m", "init"], cwd=repo)

        manager = WorkspaceManager(repo_root=repo, workspaces_root=repo / "workspaces")
        worktrees = manager.ensure_worktrees(["recon", "forge", "command"])

        recon_path = worktrees["recon"]
        forge_path = worktrees["forge"]
        command_path = worktrees["command"]

        recon_only_file = recon_path / "RECON_ONLY.txt"
        recon_only_file.write_text("recon", encoding="utf-8")

        isolation_ok = (
            recon_path.exists()
            and forge_path.exists()
            and command_path.exists()
            and recon_only_file.exists()
            and not (forge_path / "RECON_ONLY.txt").exists()
            and not (command_path / "RECON_ONLY.txt").exists()
        )

        print(f"Chamber B: {'PASS' if isolation_ok else 'FAIL'}")
        print(f"repo={repo}")
        print(f"recon={recon_path}")
        print(f"forge={forge_path}")
        print(f"command={command_path}")
        print(f"recon_only_file_exists={recon_only_file.exists()}")
        print(f"forge_has_recon_file={(forge_path / 'RECON_ONLY.txt').exists()}")
        print(f"command_has_recon_file={(command_path / 'RECON_ONLY.txt').exists()}")
        return 0 if isolation_ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Chamber B workspace isolation validation.")
    _ = parser.parse_args()
    raise SystemExit(run_chamber())


if __name__ == "__main__":
    main()
