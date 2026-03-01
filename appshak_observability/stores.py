from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping

from appshak_integrity.store import IntegrityReportStore
from appshak_inspection.store import InspectionIndexStore
from appshak_stability.store import StabilityRunStore


def load_json_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


class ObservabilityDataStore:
    def __init__(
        self,
        *,
        inspection_root: str | Path = "appshak_state/inspection",
        integrity_root: str | Path = "appshak_state/integrity",
        stability_root: str | Path = "appshak_state/stability",
    ) -> None:
        self.inspection_store = InspectionIndexStore(inspection_root)
        self.integrity_store = IntegrityReportStore(integrity_root)
        self.stability_store = StabilityRunStore(stability_root)

    def load_entities(self) -> List[Dict[str, Any]]:
        index = self.inspection_store.load_latest()
        entities = index.get("entities")
        if not isinstance(entities, Mapping):
            return []
        output: List[Dict[str, Any]] = []
        for entity_id in sorted(entities.keys()):
            entity = entities.get(entity_id)
            if isinstance(entity, Mapping):
                output.append(dict(entity))
        return output

    def load_entity(self, entity_id: str) -> Dict[str, Any]:
        index = self.inspection_store.load_latest()
        entities = index.get("entities")
        if not isinstance(entities, Mapping):
            return {}
        value = entities.get(str(entity_id).strip().lower())
        return dict(value) if isinstance(value, Mapping) else {}

    def load_entity_timeline(self, entity_id: str) -> List[Dict[str, Any]]:
        index = self.inspection_store.load_latest()
        timeline = index.get("office_timeline")
        if not isinstance(timeline, list):
            return []
        normalized_id = str(entity_id).strip().lower()
        output: List[Dict[str, Any]] = []
        for row in timeline:
            if not isinstance(row, Mapping):
                continue
            entity_ids = row.get("entity_ids")
            if isinstance(entity_ids, list) and normalized_id in entity_ids:
                output.append(dict(row))
        return output

    def load_office_timeline(self) -> List[Dict[str, Any]]:
        index = self.inspection_store.load_latest()
        timeline = index.get("office_timeline")
        if not isinstance(timeline, list):
            return []
        return [dict(row) for row in timeline if isinstance(row, Mapping)]

    def load_integrity_latest(self) -> Dict[str, Any]:
        return self.integrity_store.load_latest()

    def load_integrity_history(self, *, limit: int, cursor: str | None) -> Dict[str, Any]:
        return self.integrity_store.load_history(limit=limit, cursor=cursor)

    def load_stability_runs(self) -> List[Dict[str, Any]]:
        return self.stability_store.list_runs()

    def load_stability_run(self, run_id: str) -> Dict[str, Any]:
        return self.stability_store.load_run(run_id)
