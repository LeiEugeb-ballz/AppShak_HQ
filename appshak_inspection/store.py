from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping

from .utils import atomic_write_json, to_timestamp_token


class InspectionIndexStore:
    def __init__(self, root: Path | str = "appshak_state/inspection") -> None:
        self.root = Path(root)

    @property
    def pointer_path(self) -> Path:
        return self.root / "index.json"

    def save(self, index: Mapping[str, Any]) -> Dict[str, Path]:
        generated_at = str(index.get("generated_at", ""))
        token = to_timestamp_token(generated_at)
        versioned_path = _next_unique_file(self.root / f"{token}_index.json")
        atomic_write_json(versioned_path, dict(index))
        pointer_payload = {
            "generated_at": generated_at,
            "index_path": str(versioned_path),
        }
        atomic_write_json(self.pointer_path, pointer_payload)
        return {
            "versioned_path": versioned_path,
            "pointer_path": self.pointer_path,
        }

    def load_latest(self) -> Dict[str, Any]:
        if not self.pointer_path.exists():
            return {}
        try:
            pointer = json.loads(self.pointer_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(pointer, Mapping):
            return {}
        index_path_raw = pointer.get("index_path")
        if not isinstance(index_path_raw, str):
            return {}
        index_path = Path(index_path_raw)
        if not index_path.exists():
            return {}
        try:
            payload = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}


def _next_unique_file(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    index = 2
    while True:
        candidate = path.with_name(f"{stem}_v{index:02d}{suffix}")
        if not candidate.exists():
            return candidate
        index += 1
