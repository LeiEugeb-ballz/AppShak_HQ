from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class PerformanceHistoryManager:
    """Persistent, versioned store for sprint performance snapshots."""

    SCHEMA_VERSION = "1.0"

    def __init__(self, history_path: str | Path = "appshak_state/startup_sprint_history_v1.json") -> None:
        self.history_path = Path(history_path)
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.history_path.exists():
            self._save({"version": self.SCHEMA_VERSION, "records": []})

    def append_record(self, record: Dict[str, Any]) -> None:
        data = self._load()
        records = data.setdefault("records", [])
        if not isinstance(records, list):
            records = []
            data["records"] = records

        enriched = dict(record)
        enriched.setdefault("timestamp", self._iso_now())
        records.append(enriched)
        data["version"] = self.SCHEMA_VERSION
        self._save(data)

    def list_records(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        records = self._load().get("records", [])
        if not isinstance(records, list):
            return []
        if limit is None or limit <= 0:
            return records
        return records[-limit:]

    def query_by_sprint_id(self, sprint_id: str) -> Optional[Dict[str, Any]]:
        for record in self.list_records():
            if str(record.get("sprint_id")) == str(sprint_id):
                return record
        return None

    def export_history(self, output_path: str | Path) -> Path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(self._load(), indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        return output

    def _load(self) -> Dict[str, Any]:
        try:
            return json.loads(self.history_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"version": self.SCHEMA_VERSION, "records": []}

    def _save(self, payload: Dict[str, Any]) -> None:
        self.history_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )

    @staticmethod
    def _iso_now() -> str:
        return datetime.now(timezone.utc).isoformat()

