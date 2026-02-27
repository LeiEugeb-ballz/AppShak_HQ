from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict

from .schemas import normalize_projection_view


class ProjectionViewStore:
    """Atomic JSON persistence for projection materialized view."""

    def __init__(self, path: str | Path = "appshak_state/projection/view.json") -> None:
        self.path = Path(path)

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return normalize_projection_view({})
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return normalize_projection_view({})
        return normalize_projection_view(payload)

    def save(self, view: Dict[str, Any]) -> Dict[str, Any]:
        normalized = normalize_projection_view(view)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(self.path.parent),
            delete=False,
            suffix=".tmp",
        ) as handle:
            json.dump(normalized, handle, ensure_ascii=True, sort_keys=True)
            handle.write("\n")
            temp_path = Path(handle.name)

        try:
            os.replace(str(temp_path), str(self.path))
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)

        return normalized
