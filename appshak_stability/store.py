from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping

from .utils import atomic_write_json, load_json


class StabilityRunStore:
    def __init__(self, root: Path | str = "appshak_state/stability") -> None:
        self.root = Path(root)

    def init_run(self, *, run_id: str, meta: Mapping[str, Any]) -> Path:
        run_dir = self.root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        self._write_run_meta(run_dir=run_dir, payload=dict(meta))
        return run_dir

    def checkpoint(self, *, run_dir: Path, checkpoint_id: int, payload: Mapping[str, Any]) -> Path:
        checkpoint_path = run_dir / "checkpoints" / f"checkpoint_{checkpoint_id:04d}.json"
        atomic_write_json(checkpoint_path, dict(payload))
        return checkpoint_path

    def update_meta(self, *, run_dir: Path, payload: Mapping[str, Any]) -> None:
        self._write_run_meta(run_dir=run_dir, payload=dict(payload))

    def list_runs(self) -> List[Dict[str, Any]]:
        if not self.root.exists():
            return []
        runs: List[Dict[str, Any]] = []
        for run_dir in sorted(self.root.iterdir(), key=lambda path: path.name, reverse=True):
            if not run_dir.is_dir():
                continue
            run_meta = load_json(run_dir / "run_meta.json")
            if isinstance(run_meta, dict):
                runs.append(run_meta)
        return runs

    def load_run(self, run_id: str) -> Dict[str, Any]:
        run_dir = self.root / str(run_id)
        if not run_dir.exists():
            return {}
        run_meta = load_json(run_dir / "run_meta.json")
        checkpoints_dir = run_dir / "checkpoints"
        checkpoints = []
        if checkpoints_dir.exists():
            for path in sorted(checkpoints_dir.iterdir(), key=lambda item: item.name):
                if path.is_file():
                    payload = load_json(path)
                    if isinstance(payload, dict):
                        checkpoints.append(payload)
        if not isinstance(run_meta, dict):
            run_meta = {}
        run_meta["checkpoints"] = checkpoints
        return run_meta

    @staticmethod
    def _write_run_meta(*, run_dir: Path, payload: Mapping[str, Any]) -> None:
        run_meta = dict(payload)
        version_token = str(run_meta.get("updated_at", "unknown")).replace(":", "").replace("-", "")
        versioned_path = _next_unique_file(run_dir / f"run_meta.{version_token}.json")
        atomic_write_json(versioned_path, run_meta)
        pointer_payload = dict(run_meta)
        pointer_payload["versioned_path"] = str(versioned_path)
        atomic_write_json(run_dir / "run_meta.json", pointer_payload)


def _next_unique_file(path: Path) -> Path:
    if not path.exists():
        return path
    index = 2
    while True:
        candidate = path.with_name(f"{path.stem}_v{index:02d}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1
