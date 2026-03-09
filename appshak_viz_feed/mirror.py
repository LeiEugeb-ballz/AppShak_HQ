from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any, Dict, Mapping

from .models import build_viz_event, validate_viz_event
from .src.io_ndjson import read_ndjson, write_json
from .src.reducer import initial_state, reduce_event


class VizFeedMirror:
    def __init__(self, root: Path | str, *, run_id: str | None = None) -> None:
        self.root = Path(root)
        self.run_id = run_id or uuid.uuid4().hex
        self.run_dir = self.root / "runs" / self.run_id
        self.events_path = self.run_dir / "events.ndjson"
        self.rejections_path = self.run_dir / "rejections.ndjson"
        self.snapshot_latest_path = self.run_dir / "snapshot_latest.json"
        self._lock = asyncio.Lock()
        self._last_seq = 0
        self.run_dir.mkdir(parents=True, exist_ok=True)

    async def mirror_event(self, event: Any) -> Dict[str, Any] | None:
        event_dict = _event_to_dict(event)
        seq = _candidate_seq(event_dict, self._last_seq + 1)
        if seq <= self._last_seq:
            await self._append_rejection(
                {
                    "run_id": self.run_id,
                    "reason": "non_monotonic_seq",
                    "seq": seq,
                    "last_seq": self._last_seq,
                    "type": str(event_dict.get("type", "")),
                    "origin_id": str(event_dict.get("origin_id", "")),
                }
            )
            return None

        viz_event = build_viz_event(event=event_dict, run_id=self.run_id, seq=seq)
        errors = validate_viz_event(viz_event)
        if errors:
            await self._append_rejection(
                {
                    "run_id": self.run_id,
                    "reason": "validation_failed",
                    "errors": errors,
                    "seq": seq,
                    "type": viz_event.get("type"),
                    "origin_id": viz_event.get("origin_id"),
                }
            )
            return None

        async with self._lock:
            await asyncio.to_thread(self._append_line, self.events_path, viz_event)
            await asyncio.to_thread(self._refresh_snapshot_latest, self.events_path, self.snapshot_latest_path)
            self._last_seq = seq
        return viz_event

    async def _append_rejection(self, record: Mapping[str, Any]) -> None:
        async with self._lock:
            await asyncio.to_thread(self._append_line, self.rejections_path, record)

    @staticmethod
    def _append_line(path: Path, record: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(record), ensure_ascii=True, sort_keys=True))
            handle.write("\n")

    @staticmethod
    def _refresh_snapshot_latest(events_path: Path, snapshot_path: Path) -> None:
        st = initial_state(mode="LIVE")
        for event in read_ndjson(str(events_path)):
            st = reduce_event(st, event)
        write_json(
            str(snapshot_path),
            {
                "schema_version": st.schema_version,
                "run_id": st.run_id,
                "last_seq_processed": st.last_seq_processed,
                "viewer": st.viewer,
                "agents": st.agents,
                "jobs": st.jobs,
                "room_occupancy": st.room_occupancy,
                "alerts": st.alerts,
                "blocked_events": st.blocked_events,
                "warnings": st.warnings,
            },
        )


def _candidate_seq(event: Mapping[str, Any], default: int) -> int:
    payload = event.get("payload")
    payload_map = payload if isinstance(payload, Mapping) else {}
    queue_index = payload_map.get("queue_index")
    try:
        return int(queue_index)
    except Exception:
        return int(default)


def _event_to_dict(event: Any) -> Dict[str, Any]:
    if hasattr(event, "to_dict") and callable(event.to_dict):
        try:
            raw = event.to_dict()
            if isinstance(raw, Mapping):
                return dict(raw)
        except Exception:
            pass
    if isinstance(event, Mapping):
        return dict(event)
    return {"type": "", "origin_id": "unknown", "timestamp": "", "payload": {}}
