from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

from appshak_projection.schemas import normalize_projection_view
from appshak_projection.view_store import ProjectionViewStore


class ProjectionExtractor:
    def __init__(self, view_store: ProjectionViewStore | None = None) -> None:
        self._view_store = view_store or ProjectionViewStore()

    def get_snapshot(
        self,
        *,
        replay_snapshot: Mapping[str, Any] | None = None,
        replay_path: str | Path | None = None,
    ) -> Dict[str, Any]:
        if isinstance(replay_snapshot, Mapping):
            return normalize_projection_view(dict(replay_snapshot))
        if replay_path is not None:
            return self._load_replay_snapshot(replay_path)
        return self._view_store.load()

    def load_replay_history(self, replay_root: str | Path) -> list[Dict[str, Any]]:
        root = Path(replay_root)
        if root.is_file():
            return [self._load_replay_snapshot(root)]
        if not root.exists() or not root.is_dir():
            return []

        snapshots: list[Dict[str, Any]] = []
        for path in sorted(root.rglob("*.json")):
            snapshots.append(self._load_replay_snapshot(path))
        return snapshots

    def iter_replay_history(self, replay_root: str | Path) -> Iterable[Dict[str, Any]]:
        for snapshot in self.load_replay_history(replay_root):
            yield snapshot

    def _load_replay_snapshot(self, replay_path: str | Path) -> Dict[str, Any]:
        source = Path(replay_path)
        if source.is_dir():
            json_files = sorted(source.rglob("*.json"))
            if not json_files:
                return normalize_projection_view({})
            source = json_files[-1]
        if not source.exists():
            return normalize_projection_view({})
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except Exception:
            return normalize_projection_view({})
        if not isinstance(payload, Mapping):
            return normalize_projection_view({})
        return normalize_projection_view(payload)
