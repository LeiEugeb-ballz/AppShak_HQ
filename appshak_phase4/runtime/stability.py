from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Mapping

from appshak_integrity.utils import canonical_hash


@dataclass(frozen=True)
class CyclePreparation:
    allowed: bool
    resumed: bool
    reason: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "allowed": bool(self.allowed),
            "resumed": bool(self.resumed),
            "reason": str(self.reason),
        }


class StabilityRecoveryWrapper:
    def __init__(
        self,
        *,
        root: str | Path = "appshak_state/phase4/runtime",
        watchdog_timeout_seconds: float = 8.0,
    ) -> None:
        self.root = Path(root)
        self.state_path = self.root / "state.json"
        self.trace_path = self.root / "cycle_trace.jsonl"
        self.memory_path = self.root / "memory.json"
        self.watchdog_timeout_seconds = max(1.0, float(watchdog_timeout_seconds))

    def load_state(self) -> Dict[str, Any]:
        if not self.state_path.exists():
            return _default_state()
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return _default_state()
        if not isinstance(payload, Mapping):
            return _default_state()
        return _normalize_state(payload)

    def save_state(self, state: Mapping[str, Any]) -> Dict[str, Any]:
        normalized = _normalize_state(state)
        self._atomic_write_json(self.state_path, normalized)
        return normalized

    def prepare_cycle(self, *, cycle_id: str, cycle_index: int) -> CyclePreparation:
        state = self.load_state()
        completed = state.get("completed_cycle_ids", [])
        inflight = state.get("inflight_cycle", {})
        completed_set = {str(item) for item in completed if isinstance(item, str)}

        if cycle_id in completed_set:
            return CyclePreparation(allowed=False, resumed=False, reason="duplicate_completed")

        inflight_id = str(inflight.get("cycle_id", "")) if isinstance(inflight, Mapping) else ""
        if inflight_id == cycle_id:
            return CyclePreparation(allowed=True, resumed=True, reason="resume_inflight")

        state["inflight_cycle"] = {
            "cycle_id": str(cycle_id),
            "cycle_index": max(0, int(cycle_index)),
        }
        self.save_state(state)
        return CyclePreparation(allowed=True, resumed=False, reason="new_cycle")

    def mark_cycle_stable(
        self,
        *,
        cycle_id: str,
        cycle_index: int,
        watchdog_status: str,
        watchdog_reason: str,
        runtime_trace: Mapping[str, Any],
    ) -> Dict[str, Any]:
        state = self.load_state()
        completed = state.get("completed_cycle_ids", [])
        completed_ids = [str(item) for item in completed if isinstance(item, str)]
        if cycle_id not in completed_ids:
            completed_ids.append(cycle_id)
        completed_ids = completed_ids[-2000:]

        state["completed_cycle_ids"] = completed_ids
        state["last_stable_cycle_index"] = max(0, int(cycle_index))
        state["next_cycle_index"] = max(1, int(cycle_index) + 1)
        state["inflight_cycle"] = {}
        state["last_watchdog"] = {
            "status": str(watchdog_status),
            "reason": str(watchdog_reason),
        }

        trace_payload = {
            "cycle_id": str(cycle_id),
            "cycle_index": max(0, int(cycle_index)),
            "watchdog": dict(state["last_watchdog"]),
            "trace_hash": canonical_hash(runtime_trace),
            "trace": dict(runtime_trace),
        }
        self.append_trace(trace_payload)
        return self.save_state(state)

    def mark_cycle_failure(self, *, cycle_id: str, reason: str) -> Dict[str, Any]:
        state = self.load_state()
        state["last_watchdog"] = {
            "status": "failed",
            "reason": str(reason),
        }
        state["inflight_cycle"] = {
            "cycle_id": str(cycle_id),
            "cycle_index": max(0, int(state.get("next_cycle_index", 1))),
        }
        return self.save_state(state)

    def append_trace(self, payload: Mapping[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        line = json.dumps(dict(payload), ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
        with self.trace_path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())

    def load_memory(self) -> Dict[str, Any]:
        if not self.memory_path.exists():
            return {"cycle_summaries": [], "weekly_summaries": {}}
        try:
            payload = json.loads(self.memory_path.read_text(encoding="utf-8"))
        except Exception:
            return {"cycle_summaries": [], "weekly_summaries": {}}
        if not isinstance(payload, Mapping):
            return {"cycle_summaries": [], "weekly_summaries": {}}
        cycle_summaries = payload.get("cycle_summaries")
        weekly = payload.get("weekly_summaries")
        return {
            "cycle_summaries": list(cycle_summaries) if isinstance(cycle_summaries, list) else [],
            "weekly_summaries": dict(weekly) if isinstance(weekly, Mapping) else {},
        }

    def save_memory(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        cycle_summaries = payload.get("cycle_summaries")
        weekly = payload.get("weekly_summaries")
        normalized = {
            "cycle_summaries": list(cycle_summaries) if isinstance(cycle_summaries, list) else [],
            "weekly_summaries": dict(weekly) if isinstance(weekly, Mapping) else {},
        }
        self._atomic_write_json(self.memory_path, normalized)
        return normalized

    def _atomic_write_json(self, path: Path, payload: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            delete=False,
            suffix=".tmp",
        ) as handle:
            json.dump(dict(payload), handle, ensure_ascii=True, sort_keys=True, indent=2)
            handle.write("\n")
            temp_path = Path(handle.name)
        try:
            os.replace(str(temp_path), str(path))
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)


def _default_state() -> Dict[str, Any]:
    return {
        "next_cycle_index": 1,
        "last_stable_cycle_index": 0,
        "completed_cycle_ids": [],
        "inflight_cycle": {},
        "retry_queue": [],
        "external_gate": {"executed_keys": []},
        "last_watchdog": {"status": "ok", "reason": ""},
    }


def _normalize_state(state: Mapping[str, Any]) -> Dict[str, Any]:
    source = dict(state)
    completed = source.get("completed_cycle_ids")
    retry_queue = source.get("retry_queue")
    inflight = source.get("inflight_cycle")
    external_gate = source.get("external_gate")
    watchdog = source.get("last_watchdog")

    return {
        "next_cycle_index": max(1, _as_int(source.get("next_cycle_index"), default=1)),
        "last_stable_cycle_index": max(0, _as_int(source.get("last_stable_cycle_index"), default=0)),
        "completed_cycle_ids": [str(item) for item in completed if isinstance(item, str)] if isinstance(completed, list) else [],
        "inflight_cycle": dict(inflight) if isinstance(inflight, Mapping) else {},
        "retry_queue": [dict(item) for item in retry_queue if isinstance(item, Mapping)] if isinstance(retry_queue, list) else [],
        "external_gate": dict(external_gate) if isinstance(external_gate, Mapping) else {"executed_keys": []},
        "last_watchdog": dict(watchdog) if isinstance(watchdog, Mapping) else {"status": "ok", "reason": ""},
    }


def _as_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default
