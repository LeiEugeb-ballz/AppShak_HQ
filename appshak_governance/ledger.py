from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping

from .registry import normalize_registry_state
from .utils import canonical_hash, canonical_json


class GovernanceAuditLedger:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def append(
        self,
        *,
        entry_type: str,
        payload: Mapping[str, Any],
        timestamp: str,
    ) -> Dict[str, Any]:
        entries = self.read_entries()
        previous_hash = entries[-1]["entry_hash"] if entries else "GENESIS"
        seq = len(entries) + 1
        record = {
            "seq": seq,
            "entry_type": str(entry_type).strip().upper(),
            "timestamp": str(timestamp),
            "payload": dict(payload),
            "prev_hash": previous_hash,
        }
        entry_hash = canonical_hash(record)
        persisted = dict(record)
        persisted["entry_hash"] = entry_hash
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(canonical_json(persisted))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        return persisted

    def read_entries(self) -> List[Dict[str, Any]]:
        if not self._path.exists():
            return []
        entries: List[Dict[str, Any]] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if isinstance(row, Mapping):
                entries.append(dict(row))
        entries.sort(key=lambda row: int(row.get("seq", 0)))
        return entries

    def reconstruct_registry(self, *, fallback_registry: Mapping[str, Any]) -> Dict[str, Any]:
        state = normalize_registry_state(fallback_registry)
        for entry in self.read_entries():
            entry_type = str(entry.get("entry_type", "")).strip().upper()
            payload = entry.get("payload")
            if not isinstance(payload, Mapping):
                continue

            if entry_type == "REGISTRY_UPDATE":
                candidate = payload.get("registry")
                state = normalize_registry_state(candidate)
                continue

            if entry_type == "TRUST_CHANGE":
                state = _apply_trust_change(state, payload)
                continue

            if entry_type == "WATER_COOLER_LESSON":
                state = _apply_lesson_injection(state, payload)
                continue
        return normalize_registry_state(state)

    def validate_hash_chain(self) -> bool:
        entries = self.read_entries()
        previous_hash = "GENESIS"
        for expected_seq, entry in enumerate(entries, start=1):
            if int(entry.get("seq", -1)) != expected_seq:
                return False
            record = {
                "seq": int(entry.get("seq", 0)),
                "entry_type": str(entry.get("entry_type", "")).strip().upper(),
                "timestamp": str(entry.get("timestamp", "")),
                "payload": dict(entry.get("payload", {})) if isinstance(entry.get("payload"), Mapping) else {},
                "prev_hash": str(entry.get("prev_hash", "")),
            }
            if record["prev_hash"] != previous_hash:
                return False
            if str(entry.get("entry_hash", "")) != canonical_hash(record):
                return False
            previous_hash = str(entry.get("entry_hash", ""))
        return True

    def validate_registry_hash(self, *, registry_state: Mapping[str, Any]) -> bool:
        entries = self.read_entries()
        registry_updates = [entry for entry in entries if str(entry.get("entry_type", "")).upper() == "REGISTRY_UPDATE"]
        if not registry_updates:
            return False
        latest = registry_updates[-1]
        payload = latest.get("payload", {})
        expected_hash = ""
        if isinstance(payload, Mapping):
            expected_hash = str(payload.get("registry_hash", ""))
        actual_hash = canonical_hash(normalize_registry_state(registry_state))
        return expected_hash == actual_hash


def _apply_trust_change(state: Mapping[str, Any], payload: Mapping[str, Any]) -> Dict[str, Any]:
    working = normalize_registry_state(state)
    subject_id = str(payload.get("subject_id", "")).strip().lower()
    if subject_id not in working["agents"]:
        return working

    reputation_delta = float(payload.get("reputation_delta", 0.0))
    observer_deltas = payload.get("observer_trust_deltas")
    observer_trust_deltas = dict(observer_deltas) if isinstance(observer_deltas, Mapping) else {}

    subject = working["agents"][subject_id]
    subject["reputation_score"] = min(1.0, max(0.0, float(subject["reputation_score"]) + reputation_delta))

    for observer_id, observer_state in working["agents"].items():
        trust_weights = observer_state.get("trust_weights", {})
        if not isinstance(trust_weights, dict):
            continue
        current = float(trust_weights.get(subject_id, 0.5))
        delta = float(observer_trust_deltas.get(observer_id, 0.0))
        trust_weights[subject_id] = min(1.0, max(0.0, current + delta))

    working["version"] = int(working.get("version", 1)) + 1
    updated_at = str(payload.get("source_timestamp", "")).strip()
    if updated_at:
        working["last_updated"] = updated_at

    history = working.setdefault("history", {})
    for agent_id, agent_state in working["agents"].items():
        series = history.setdefault(agent_id, [])
        series.append(float(agent_state.get("reputation_score", 0.5)))
    return normalize_registry_state(working)


def _apply_lesson_injection(state: Mapping[str, Any], payload: Mapping[str, Any]) -> Dict[str, Any]:
    working = normalize_registry_state(state)
    lesson = payload.get("lesson")
    if not isinstance(lesson, Mapping):
        return working
    lesson_id = str(lesson.get("lesson_id", "")).strip()
    recipients = lesson.get("recipients")
    if not lesson_id or not isinstance(recipients, list):
        return working

    for recipient_raw in recipients:
        recipient = str(recipient_raw).strip().lower()
        if recipient not in working["agents"]:
            continue
        refs = working["agents"][recipient].setdefault("knowledge_lessons", [])
        if lesson_id not in refs:
            refs.append(lesson_id)
            refs.sort()
    return normalize_registry_state(working)
