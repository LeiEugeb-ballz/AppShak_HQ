from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Mapping

from appshak_integrity.utils import canonical_hash


class ExternalActionGate:
    def __init__(
        self,
        *,
        root: str | Path = "appshak_state/phase4/runtime",
        allowed_action_types: tuple[str, ...] = ("NOOP", "READ_ONLY_REPORT"),
    ) -> None:
        self.root = Path(root)
        self.audit_path = self.root / "external_audit.jsonl"
        self.allowed_action_types = tuple(sorted({str(item).strip().upper() for item in allowed_action_types if str(item).strip()}))

    def execute(
        self,
        *,
        cycle_id: str,
        action_request: Mapping[str, Any],
        chief_approved: bool,
        state: Mapping[str, Any],
    ) -> Dict[str, Any]:
        request = dict(action_request)
        action_type = str(request.get("action_type", "NOOP")).strip().upper() or "NOOP"
        idempotency_key = str(request.get("idempotency_key", "")).strip() or self._derive_idempotency_key(cycle_id, request)
        executed_keys = self._executed_keys(state)

        if not chief_approved:
            result = {
                "cycle_id": str(cycle_id),
                "status": "denied_chief_approval_required",
                "approved": False,
                "action_type": action_type,
                "idempotency_key": idempotency_key,
                "result": {"executed": False, "reason": "chief_approval_required"},
            }
            self._append_audit(result)
            return result

        if idempotency_key in executed_keys:
            result = {
                "cycle_id": str(cycle_id),
                "status": "skipped_duplicate",
                "approved": True,
                "action_type": action_type,
                "idempotency_key": idempotency_key,
                "result": {"executed": False, "reason": "duplicate_idempotency_key"},
            }
            self._append_audit(result)
            return result

        if action_type not in self.allowed_action_types:
            result = {
                "cycle_id": str(cycle_id),
                "status": "blocked_action_type",
                "approved": True,
                "action_type": action_type,
                "idempotency_key": idempotency_key,
                "result": {"executed": False, "reason": "action_type_not_allowed"},
            }
            self._append_audit(result)
            return result

        result = {
            "cycle_id": str(cycle_id),
            "status": "executed",
            "approved": True,
            "action_type": action_type,
            "idempotency_key": idempotency_key,
            "result": {
                "executed": True,
                "reason": "chief_approved_and_policy_allowed",
                "payload_digest": canonical_hash(request),
            },
        }
        self._append_audit(result)
        return result

    def _derive_idempotency_key(self, cycle_id: str, action_request: Mapping[str, Any]) -> str:
        return f"phase4:{canonical_hash({'cycle_id': cycle_id, 'request': dict(action_request)})[:24]}"

    def _append_audit(self, payload: Mapping[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        line = json.dumps(dict(payload), ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())

    def _executed_keys(self, state: Mapping[str, Any]) -> set[str]:
        gate_state = state.get("external_gate")
        if not isinstance(gate_state, Mapping):
            return set()
        keys = gate_state.get("executed_keys")
        if not isinstance(keys, list):
            return set()
        return {str(item) for item in keys if isinstance(item, str)}
