from __future__ import annotations

import json
import hashlib
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from appshak_substrate.types import SubstrateEvent, iso_now


class SQLiteMailStore:
    """Durable event/mail storage with lease-based claiming semantics."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        lease_seconds: float = 15.0,
        poll_interval: float = 0.1,
        busy_timeout_ms: int = 5000,
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.lease_seconds = max(0.1, float(lease_seconds))
        self.poll_interval = max(0.01, float(poll_interval))
        self.busy_timeout_ms = max(100, int(busy_timeout_ms))
        self._initialize_schema()

    def append_event(self, event: SubstrateEvent | Dict[str, Any]) -> int:
        normalized = SubstrateEvent.coerce(event)
        payload = dict(normalized.payload)
        if normalized.correlation_id:
            payload.setdefault("correlation_id", normalized.correlation_id)
        if normalized.target_agent:
            payload.setdefault("target_agent", normalized.target_agent)

        correlation_id = normalized.correlation_id
        if not correlation_id:
            raw_corr = payload.get("correlation_id")
            correlation_id = raw_corr if isinstance(raw_corr, str) and raw_corr.strip() else None

        target_agent = normalized.target_agent
        if not target_agent:
            raw_target = payload.get("target_agent")
            target_agent = raw_target if isinstance(raw_target, str) and raw_target.strip() else None

        justification = normalized.justification
        if not justification:
            maybe_justification = payload.get("prime_directive_justification")
            justification = maybe_justification if isinstance(maybe_justification, str) else None

        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO events (
                    ts, type, origin_id, target_agent, payload_json,
                    justification, status, error, correlation_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized.timestamp,
                    normalized.type,
                    normalized.origin_id,
                    target_agent,
                    json.dumps(payload, ensure_ascii=True),
                    justification,
                    "PENDING",
                    None,
                    correlation_id,
                ),
            )
            event_id = int(cursor.lastrowid)
            conn.commit()
            return event_id

    def claim_next_event(
        self,
        consumer_id: str,
        timeout: Optional[float],
        *,
        target_agent: Optional[str] = None,
        include_unrouted: bool = True,
        lease_seconds: Optional[float] = None,
    ) -> Optional[SubstrateEvent]:
        if not isinstance(consumer_id, str) or not consumer_id.strip():
            raise ValueError("consumer_id must be a non-empty string")

        timeout_seconds = None if timeout is None else max(0.0, float(timeout))
        deadline = None if timeout_seconds is None else time.monotonic() + timeout_seconds

        while True:
            claimed = self._try_claim_next(
                consumer_id=consumer_id.strip(),
                target_agent=target_agent.strip() if isinstance(target_agent, str) and target_agent.strip() else None,
                include_unrouted=bool(include_unrouted),
                lease_seconds=lease_seconds,
            )
            if claimed is not None:
                return claimed

            if deadline is not None and time.monotonic() >= deadline:
                return None

            sleep_for = self.poll_interval
            if deadline is not None:
                sleep_for = min(sleep_for, max(0.0, deadline - time.monotonic()))
                if sleep_for <= 0:
                    return None
            time.sleep(sleep_for)

    def ack_event(self, event_id: int, status: str = "DONE", *, consumer_id: Optional[str] = None) -> None:
        normalized_status = status.strip().upper() if isinstance(status, str) and status.strip() else "DONE"
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if consumer_id:
                row = conn.execute(
                    "SELECT claimed_by FROM leases WHERE event_id = ?",
                    (int(event_id),),
                ).fetchone()
                if row is not None and str(row["claimed_by"]) != consumer_id:
                    conn.rollback()
                    raise PermissionError(
                        f"consumer '{consumer_id}' cannot ack event {event_id}; lease held by '{row['claimed_by']}'"
                    )
            conn.execute(
                "UPDATE events SET status = ?, error = NULL WHERE id = ?",
                (normalized_status, int(event_id)),
            )
            conn.execute("DELETE FROM leases WHERE event_id = ?", (int(event_id),))
            conn.commit()

    def fail_event(self, event_id: int, error: str, *, consumer_id: Optional[str] = None) -> None:
        err = str(error)[:4000]
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if consumer_id:
                row = conn.execute(
                    "SELECT claimed_by FROM leases WHERE event_id = ?",
                    (int(event_id),),
                ).fetchone()
                if row is not None and str(row["claimed_by"]) != consumer_id:
                    conn.rollback()
                    raise PermissionError(
                        f"consumer '{consumer_id}' cannot fail event {event_id}; lease held by '{row['claimed_by']}'"
                    )
            conn.execute(
                "UPDATE events SET status = 'FAILED', error = ? WHERE id = ?",
                (err, int(event_id)),
            )
            conn.execute("DELETE FROM leases WHERE event_id = ?", (int(event_id),))
            conn.commit()

    def requeue_event(
        self,
        event_id: int,
        *,
        consumer_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if consumer_id:
                row = conn.execute(
                    "SELECT claimed_by FROM leases WHERE event_id = ?",
                    (int(event_id),),
                ).fetchone()
                if row is not None and str(row["claimed_by"]) != consumer_id:
                    conn.rollback()
                    raise PermissionError(
                        f"consumer '{consumer_id}' cannot requeue event {event_id}; lease held by '{row['claimed_by']}'"
                    )
            conn.execute(
                "UPDATE events SET status = 'PENDING', error = ? WHERE id = ?",
                (str(error)[:4000] if error else None, int(event_id)),
            )
            conn.execute("DELETE FROM leases WHERE event_id = ?", (int(event_id),))
            conn.commit()

    def get_event(self, event_id: int) -> Optional[SubstrateEvent]:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM events WHERE id = ?", (int(event_id),)).fetchone()
            if row is None:
                return None
            return SubstrateEvent.from_row(row)

    def list_events(self, *, status: Optional[str] = None) -> List[SubstrateEvent]:
        with self._connection() as conn:
            if status is None:
                rows = conn.execute("SELECT * FROM events ORDER BY id ASC").fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM events WHERE status = ? ORDER BY id ASC",
                    (status,),
                ).fetchall()
        return [SubstrateEvent.from_row(row) for row in rows]

    def status_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) as count FROM events GROUP BY status ORDER BY status ASC"
            ).fetchall()
            for row in rows:
                counts[str(row["status"])] = int(row["count"])
        return counts

    def append_tool_audit(
        self,
        *,
        agent_id: str,
        action_type: str,
        working_dir: str,
        idempotency_key: Optional[str],
        allowed: bool,
        reason: Optional[str],
        payload: Dict[str, Any],
        result: Optional[Dict[str, Any]],
        correlation_id: Optional[str] = None,
    ) -> int:
        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO tool_audit (
                    ts, agent_id, action_type, working_dir, idempotency_key, allowed,
                    reason, payload_json, result_json, correlation_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    iso_now(),
                    str(agent_id),
                    str(action_type),
                    str(working_dir),
                    idempotency_key,
                    1 if allowed else 0,
                    reason,
                    json.dumps(payload, ensure_ascii=True),
                    json.dumps(result, ensure_ascii=True) if result is not None else None,
                    correlation_id,
                ),
            )
            audit_id = int(cursor.lastrowid)
            conn.commit()
            return audit_id

    def list_tool_audit(self, *, limit: int = 100) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT id, ts, agent_id, action_type, working_dir, allowed, reason,
                       idempotency_key, payload_json, result_json, correlation_id
                FROM tool_audit
                ORDER BY id DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
            result = json.loads(row["result_json"]) if row["result_json"] else None
            out.append(
                {
                    "id": int(row["id"]),
                    "ts": str(row["ts"]),
                    "agent_id": str(row["agent_id"]),
                    "action_type": str(row["action_type"]),
                    "working_dir": str(row["working_dir"]),
                    "idempotency_key": row["idempotency_key"],
                    "allowed": bool(row["allowed"]),
                    "reason": row["reason"],
                    "payload": payload,
                    "result": result,
                    "correlation_id": row["correlation_id"],
                }
            )
        return out

    def reserve_idempotency_key(
        self,
        idempotency_key: str,
        *,
        agent_id: str,
        action_type: str,
        event_id: Optional[int] = None,
    ) -> bool:
        key = idempotency_key.strip()
        if not key:
            raise ValueError("idempotency_key must be non-empty.")
        with self._connection() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO idempotency_keys (
                        idempotency_key, created_ts, agent_id, action_type, event_id, result_json
                    )
                    VALUES (?, ?, ?, ?, ?, NULL)
                    """,
                    (key, iso_now(), str(agent_id), str(action_type), event_id),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                conn.rollback()
                return False

    def get_idempotency_record(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        key = idempotency_key.strip()
        if not key:
            return None
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT idempotency_key, created_ts, agent_id, action_type, event_id, result_json
                FROM idempotency_keys
                WHERE idempotency_key = ?
                """,
                (key,),
            ).fetchone()
        if row is None:
            return None
        result_json = row["result_json"]
        result = json.loads(result_json) if isinstance(result_json, str) and result_json.strip() else None
        return {
            "idempotency_key": str(row["idempotency_key"]),
            "created_ts": str(row["created_ts"]),
            "agent_id": str(row["agent_id"]),
            "action_type": str(row["action_type"]),
            "event_id": row["event_id"],
            "result": result,
        }

    def set_idempotency_result(self, idempotency_key: str, result: Dict[str, Any]) -> None:
        key = idempotency_key.strip()
        if not key:
            return
        with self._connection() as conn:
            conn.execute(
                "UPDATE idempotency_keys SET result_json = ? WHERE idempotency_key = ?",
                (json.dumps(result, ensure_ascii=True), key),
            )
            conn.commit()

    @staticmethod
    def _attempt_dict(row: sqlite3.Row) -> Dict[str, Any]:
        item = dict(row)
        item["request"] = json.loads(item.pop("request_json"))
        outcome_json = item.pop("outcome_json")
        item["outcome"] = json.loads(outcome_json) if outcome_json else None
        return item

    def get_attempt(self, attempt_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM execution_attempts WHERE attempt_id = ?", (attempt_id,)).fetchone()
        return self._attempt_dict(row) if row else None

    def create_owner_task(self, *, owner_id: str, objective: str, authority_id: str,
                          source_request_id: str) -> Dict[str, Any]:
        for name, value in (("owner_id", owner_id), ("objective", objective),
                            ("authority_id", authority_id), ("source_request_id", source_request_id)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string.")
        if authority_id.strip().casefold() in {"approved", "authorized", "validated", "admin", "chief", "command"}:
            raise ValueError("Task authority must use an opaque authority_id, not a display label.")
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM owner_tasks WHERE source_request_id = ?",
                               (source_request_id,)).fetchone()
            if row:
                if (row["owner_id"], row["objective"], row["authority_id"]) != (owner_id, objective, authority_id):
                    raise ValueError("Task source_request_id is bound to a different owner-task contract.")
                return dict(row)
            task_id, now = str(uuid.uuid4()), iso_now()
            conn.execute(
                """INSERT INTO owner_tasks (task_id, source_request_id, owner_id, objective,
                   authority_id, state, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'CREATED', ?, ?)""",
                (task_id, source_request_id, owner_id, objective, authority_id, now, now),
            )
            self._task_history(conn, task_id, "task_created", None, "CREATED", owner_id,
                               source_request_id, None, now)
            conn.commit()
            return dict(conn.execute("SELECT * FROM owner_tasks WHERE task_id = ?", (task_id,)).fetchone())

    def assign_owner_task(self, *, task_id: str, agent_id: str, workspace_id: str,
                          authority_id: str, actor_id: str, source_ref: str) -> Dict[str, Any]:
        for name, value in (("task_id", task_id), ("agent_id", agent_id),
                            ("workspace_id", workspace_id), ("authority_id", authority_id),
                            ("actor_id", actor_id), ("source_ref", source_ref)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string.")
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM owner_tasks WHERE task_id = ?", (task_id,)).fetchone()
            if not row:
                raise ValueError("Owner task does not exist.")
            if actor_id != row["owner_id"] or authority_id != row["authority_id"]:
                raise ValueError("Assignment owner or authority does not match the task.")
            if row["state"] == "ASSIGNED" and (row["assigned_agent"], row["workspace_id"],
                    row["assignment_authority_id"], row["assignment_source"]) == (agent_id, workspace_id,
                                                                                     authority_id, source_ref):
                return dict(row)
            if row["state"] != "CREATED":
                raise ValueError("Only CREATED tasks can be assigned; reassignment is not implemented.")
            now = iso_now()
            conn.execute(
                """UPDATE owner_tasks SET state = 'ASSIGNED', assigned_agent = ?, workspace_id = ?,
                   assignment_authority_id = ?, assignment_source = ?, assigned_at = ?, updated_at = ?
                   WHERE task_id = ?""",
                (agent_id, workspace_id, authority_id, source_ref, now, now, task_id),
            )
            self._task_history(conn, task_id, "task_assigned", "CREATED", "ASSIGNED",
                               actor_id, source_ref, None, now)
            conn.commit()
            return dict(conn.execute("SELECT * FROM owner_tasks WHERE task_id = ?", (task_id,)).fetchone())

    def get_owner_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM owner_tasks WHERE task_id = ?", (task_id,)).fetchone()
            if not row:
                return None
            result = dict(row)
            result["history"] = [dict(item) for item in conn.execute(
                "SELECT * FROM owner_task_history WHERE task_id = ? ORDER BY id", (task_id,)).fetchall()]
            result["attempts"] = [self._attempt_dict(item) for item in conn.execute(
                "SELECT * FROM execution_attempts WHERE task_id = ? ORDER BY rowid", (task_id,)).fetchall()]
            result["artifacts"] = [dict(item) for item in conn.execute(
                "SELECT * FROM owner_task_artifacts WHERE task_id = ? ORDER BY rowid", (task_id,)).fetchall()]
            result["criteria"] = [self._criterion_dict(item) for item in conn.execute(
                "SELECT * FROM task_acceptance_criteria WHERE task_id = ? ORDER BY created_at, criterion_id",
                (task_id,)).fetchall()]
            result["validations"] = [self._validation_dict(conn, item) for item in conn.execute(
                "SELECT * FROM validation_runs WHERE task_id = ? ORDER BY created_at, validation_id",
                (task_id,)).fetchall()]
            return result

    @staticmethod
    def _criterion_dict(row: sqlite3.Row) -> Dict[str, Any]:
        item = dict(row)
        item["config"] = json.loads(item.pop("config_json"))
        item["required"] = bool(item["required"])
        return item

    @staticmethod
    def _validation_dict(conn: sqlite3.Connection, row: sqlite3.Row) -> Dict[str, Any]:
        item = dict(row)
        raw_evidence = item.pop("evidence_json")
        item["evidence"] = json.loads(raw_evidence) if raw_evidence else None
        item["checks"] = []
        for check in conn.execute(
            "SELECT * FROM validation_checks WHERE validation_id = ? ORDER BY criterion_id",
            (item["validation_id"],),
        ).fetchall():
            check_item = dict(check)
            check_item["evidence"] = json.loads(check_item.pop("evidence_json"))
            item["checks"].append(check_item)
        return item

    def add_acceptance_criterion(self, *, task_id: str, criterion_type: str,
                                 config: Dict[str, Any], created_by: str,
                                 source_ref: str, required: bool = True) -> Dict[str, Any]:
        kind = str(criterion_type).strip().upper()
        if kind not in {"FILE_EXISTS", "EXACT_TEXT", "SHA256"}:
            raise ValueError("Unsupported acceptance criterion type.")
        if not isinstance(config, dict):
            raise ValueError("Acceptance criterion config must be an object.")
        if kind == "EXACT_TEXT" and not isinstance(config.get("expected"), str):
            raise ValueError("EXACT_TEXT requires string config.expected.")
        if kind == "SHA256":
            digest = config.get("expected")
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdefABCDEF" for c in digest):
                raise ValueError("SHA256 requires a 64-character hexadecimal config.expected.")
        for name, value in (("task_id", task_id), ("created_by", created_by), ("source_ref", source_ref)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string.")
        config_json = json.dumps(config, ensure_ascii=True, sort_keys=True)
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            task = conn.execute("SELECT * FROM owner_tasks WHERE task_id = ?", (task_id,)).fetchone()
            if not task:
                raise ValueError("Owner task does not exist.")
            if task["owner_id"] != created_by:
                raise ValueError("Only the task owner can define acceptance criteria.")
            if task["state"] not in {"CREATED", "ASSIGNED"}:
                raise ValueError("Acceptance criteria must be fixed before task execution.")
            existing = conn.execute(
                """SELECT * FROM task_acceptance_criteria WHERE task_id = ? AND criterion_type = ?
                   AND config_json = ? AND source_ref = ?""",
                (task_id, kind, config_json, source_ref),
            ).fetchone()
            if existing:
                conn.commit()
                return self._criterion_dict(existing)
            criterion_id, now = str(uuid.uuid4()), iso_now()
            conn.execute(
                """INSERT INTO task_acceptance_criteria
                   (criterion_id, task_id, criterion_type, config_json, required,
                    source_ref, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (criterion_id, task_id, kind, config_json, int(required), source_ref, created_by, now),
            )
            conn.commit()
            return self._criterion_dict(conn.execute(
                "SELECT * FROM task_acceptance_criteria WHERE criterion_id = ?", (criterion_id,)
            ).fetchone())

    def get_artifact(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM owner_task_artifacts WHERE artifact_id = ?",
                               (artifact_id,)).fetchone()
        return dict(row) if row else None

    def create_validation_run(self, *, task_id: str, artifact_id: str, validator_id: str,
                              source_request_id: str) -> Dict[str, Any]:
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute("SELECT * FROM validation_runs WHERE source_request_id = ?",
                                    (source_request_id,)).fetchone()
            if existing:
                if (existing["task_id"], existing["artifact_id"], existing["validator_id"]) != (
                        task_id, artifact_id, validator_id):
                    raise ValueError("Validation source_request_id is bound to a different contract.")
                conn.commit()
                return self._validation_dict(conn, existing)
            task = conn.execute("SELECT * FROM owner_tasks WHERE task_id = ?", (task_id,)).fetchone()
            artifact = conn.execute("SELECT * FROM owner_task_artifacts WHERE artifact_id = ?",
                                    (artifact_id,)).fetchone()
            if not task or task["state"] != "READY_FOR_VALIDATION":
                raise ValueError("Task is not ready for validation.")
            if not artifact or artifact["task_id"] != task_id:
                raise ValueError("Validation artifact does not belong to the task.")
            if not conn.execute(
                "SELECT 1 FROM task_acceptance_criteria WHERE task_id = ? AND required = 1 LIMIT 1",
                (task_id,),
            ).fetchone():
                raise ValueError("Task has no required acceptance criteria.")
            validation_id, now = str(uuid.uuid4()), iso_now()
            conn.execute(
                """INSERT INTO validation_runs
                   (validation_id, source_request_id, task_id, artifact_id, validator_id,
                    status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?)""",
                (validation_id, source_request_id, task_id, artifact_id, validator_id, now, now),
            )
            conn.commit()
            return self._validation_dict(conn, conn.execute(
                "SELECT * FROM validation_runs WHERE validation_id = ?", (validation_id,)
            ).fetchone())

    def get_validation_run(self, validation_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM validation_runs WHERE validation_id = ?",
                               (validation_id,)).fetchone()
            return self._validation_dict(conn, row) if row else None

    def complete_validation(self, validation_id: str, *, observed_text: str,
                            actor_id: str) -> Dict[str, Any]:
        """Persist deterministic checks and gate COMPLETE on the exact inspected bytes."""
        now = iso_now()
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            run = conn.execute("SELECT * FROM validation_runs WHERE validation_id = ?",
                               (validation_id,)).fetchone()
            if not run:
                raise ValueError("Validation run does not exist.")
            if run["status"] in {"PASSED", "FAILED", "ERROR", "NEEDS_RECONCILIATION"}:
                conn.commit()
                return self._validation_dict(conn, run)
            if run["status"] != "RUNNING" or not run["related_attempt_id"]:
                raise ValueError("Validation run is not backed by a running validator attempt.")
            attempt = conn.execute("SELECT * FROM execution_attempts WHERE attempt_id = ?",
                                   (run["related_attempt_id"],)).fetchone()
            if not attempt or attempt["state"] != "SUCCEEDED" or attempt["validation_id"] != validation_id:
                raise ValueError("Validator attempt has no durable successful outcome.")
            artifact = conn.execute("SELECT * FROM owner_task_artifacts WHERE artifact_id = ?",
                                    (run["artifact_id"],)).fetchone()
            if not artifact:
                return self._finish_validation_error(
                    conn, run, "ERROR", actor_id, {"reason": "artifact_record_missing"}, now)
            try:
                current_bytes = Path(artifact["reference"]).read_bytes()
            except OSError as exc:
                return self._finish_validation_error(
                    conn, run, "ERROR", actor_id,
                    {"reason": "artifact_read_error", "error": repr(exc)}, now)
            observed_bytes = observed_text.encode("utf-8")
            current_sha = hashlib.sha256(current_bytes).hexdigest()
            observed_sha = hashlib.sha256(observed_bytes).hexdigest()
            integrity_match = (
                artifact["sha256"] == current_sha == observed_sha
                and artifact["size_bytes"] == len(current_bytes) == len(observed_bytes)
            )
            criteria = conn.execute(
                "SELECT * FROM task_acceptance_criteria WHERE task_id = ? ORDER BY created_at, criterion_id",
                (run["task_id"],),
            ).fetchall()
            required_passed = True
            check_summaries: List[Dict[str, Any]] = []
            for criterion in criteria:
                config = json.loads(criterion["config_json"])
                kind = criterion["criterion_type"]
                if kind == "FILE_EXISTS":
                    passed, observed = True, {"exists": True}
                elif kind == "EXACT_TEXT":
                    passed = observed_text == config["expected"]
                    observed = {"text_sha256": observed_sha, "size_bytes": len(observed_bytes)}
                elif kind == "SHA256":
                    passed = current_sha.casefold() == str(config["expected"]).casefold()
                    observed = {"sha256": current_sha}
                else:
                    passed, observed = False, {"error": "unsupported_criterion"}
                status = "PASSED" if passed else "FAILED"
                evidence = {"criterion_type": kind, "observed": observed}
                conn.execute(
                    """INSERT OR REPLACE INTO validation_checks
                       (validation_id, criterion_id, status, evidence_json) VALUES (?, ?, ?, ?)""",
                    (validation_id, criterion["criterion_id"], status,
                     json.dumps(evidence, ensure_ascii=True, sort_keys=True)),
                )
                check_summaries.append({"criterion_id": criterion["criterion_id"], "status": status})
                if criterion["required"] and not passed:
                    required_passed = False
            passed = bool(criteria) and required_passed and integrity_match
            status = "PASSED" if passed else "FAILED"
            evidence = {
                "artifact_id": artifact["artifact_id"],
                "reference": artifact["reference"],
                "produced_sha256": artifact["sha256"],
                "observed_sha256": observed_sha,
                "completion_sha256": current_sha,
                "size_bytes": len(current_bytes),
                "integrity_match": integrity_match,
                "checks": check_summaries,
            }
            conn.execute(
                """UPDATE validation_runs SET status = ?, completed_at = ?, validated_sha256 = ?,
                   validated_size_bytes = ?, evidence_json = ?, updated_at = ? WHERE validation_id = ?""",
                (status, now, current_sha, len(current_bytes),
                 json.dumps(evidence, ensure_ascii=True, sort_keys=True), now, validation_id),
            )
            task_state = "COMPLETE" if passed else "VALIDATION_FAILED"
            event_type = "task_validation_passed" if passed else "task_validation_failed"
            self._set_task_state(conn, run["task_id"], task_state, event_type, actor_id,
                                 run["source_request_id"], run["related_attempt_id"], now)
            conn.commit()
            return self._validation_dict(conn, conn.execute(
                "SELECT * FROM validation_runs WHERE validation_id = ?", (validation_id,)
            ).fetchone())

    def record_validation_error(self, validation_id: str, *, actor_id: str,
                                evidence: Dict[str, Any], unknown: bool = False) -> Dict[str, Any]:
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            run = conn.execute("SELECT * FROM validation_runs WHERE validation_id = ?",
                               (validation_id,)).fetchone()
            if not run:
                raise ValueError("Validation run does not exist.")
            if run["status"] in {"PASSED", "FAILED", "ERROR", "NEEDS_RECONCILIATION"}:
                conn.commit()
                return self._validation_dict(conn, run)
            return self._finish_validation_error(
                conn, run, "NEEDS_RECONCILIATION" if unknown else "ERROR",
                actor_id, evidence, iso_now())

    def _finish_validation_error(self, conn: sqlite3.Connection, run: sqlite3.Row,
                                 status: str, actor_id: str, evidence: Dict[str, Any],
                                 now: str) -> Dict[str, Any]:
        conn.execute(
            """UPDATE validation_runs SET status = ?, completed_at = ?, evidence_json = ?,
               updated_at = ? WHERE validation_id = ?""",
            (status, now, json.dumps(evidence, ensure_ascii=True, sort_keys=True),
             now, run["validation_id"]),
        )
        task_state = "NEEDS_RECONCILIATION" if status == "NEEDS_RECONCILIATION" else "VALIDATION_ERROR"
        event_type = "task_needs_reconciliation" if status == "NEEDS_RECONCILIATION" else "task_validation_error"
        self._set_task_state(conn, run["task_id"], task_state, event_type, actor_id,
                             run["source_request_id"], run["related_attempt_id"] or "", now)
        conn.commit()
        return self._validation_dict(conn, conn.execute(
            "SELECT * FROM validation_runs WHERE validation_id = ?", (run["validation_id"],)
        ).fetchone())

    @staticmethod
    def _task_history(conn: sqlite3.Connection, task_id: str, event_type: str,
                      previous_state: Optional[str], new_state: str, actor_id: str,
                      source_ref: str, attempt_id: Optional[str], ts: str) -> None:
        conn.execute(
            """INSERT INTO owner_task_history (task_id, event_type, previous_state, new_state,
               ts, actor_id, source_ref, attempt_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (task_id, event_type, previous_state, new_state, ts, actor_id, source_ref, attempt_id),
        )

    def _set_task_state(self, conn: sqlite3.Connection, task_id: str, new_state: str,
                        event_type: str, actor_id: str, source_ref: str,
                        attempt_id: str, now: str) -> None:
        row = conn.execute("SELECT state FROM owner_tasks WHERE task_id = ?", (task_id,)).fetchone()
        if not row:
            raise ValueError("Linked owner task no longer exists.")
        conn.execute("UPDATE owner_tasks SET state = ?, updated_at = ? WHERE task_id = ?",
                     (new_state, now, task_id))
        self._task_history(conn, task_id, event_type, row["state"], new_state,
                           actor_id, source_ref, attempt_id, now)

    def reserve_attempt(self, *, source_request_id: str, source_event_id: Optional[int],
                        idempotency_key: str, authority_id: str, agent_id: str,
                        workspace_id: str, requested_operation: str, created_at: str,
                        request: Dict[str, Any], task_id: Optional[str] = None,
                        validation_id: Optional[str] = None) -> Dict[str, Any]:
        """Atomically bind a source request and idempotency key to one attempt."""
        request_json = json.dumps(request, ensure_ascii=True, sort_keys=True)
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM execution_attempts WHERE source_request_id = ? OR idempotency_key = ?",
                (source_request_id, idempotency_key),
            ).fetchone()
            if row:
                if (row["source_request_id"] != source_request_id or row["idempotency_key"] != idempotency_key
                        or row["request_json"] != request_json or row["task_id"] != task_id
                        or row["validation_id"] != validation_id):
                    conn.rollback()
                    raise ValueError("Source request or idempotency key is already bound to a different execution contract.")
                conn.commit()
                return self._attempt_dict(row)
            legacy = conn.execute("SELECT 1 FROM idempotency_keys WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
            if legacy:
                conn.rollback()
                raise ValueError("Legacy idempotency key has no execution attempt; manual reconciliation required.")
            if source_event_id is not None and not conn.execute(
                "SELECT 1 FROM events WHERE id = ?", (source_event_id,)
            ).fetchone():
                conn.rollback()
                raise ValueError("Execution source_event_id does not reference a durable event.")
            if task_id is not None:
                task = conn.execute("SELECT * FROM owner_tasks WHERE task_id = ?", (task_id,)).fetchone()
                if not task:
                    raise ValueError("Task-backed execution references a nonexistent owner task.")
                allowed_states = {"READY_FOR_VALIDATION"} if validation_id else {"ASSIGNED", "EXECUTING"}
                if task["state"] not in allowed_states:
                    raise ValueError("Owner task is not in the required executable or validation state.")
                if ((task["assigned_agent"], task["workspace_id"], task["assignment_authority_id"])
                        != (agent_id, workspace_id, authority_id)):
                    raise ValueError("Execution worker, workspace or authority conflicts with task assignment.")
            if validation_id is not None:
                validation = conn.execute("SELECT * FROM validation_runs WHERE validation_id = ?",
                                          (validation_id,)).fetchone()
                if (not validation or validation["task_id"] != task_id
                        or validation["status"] != "PENDING"):
                    raise ValueError("Validation run is not pending for this task.")
                if requested_operation != "READ_FILE":
                    raise ValueError("Deterministic file validation requires READ_FILE.")
            attempt_id = str(uuid.uuid4())
            now = iso_now()
            conn.execute(
                """INSERT INTO execution_attempts
                (attempt_id, source_request_id, source_event_id, idempotency_key, authority_id,
                 agent_id, workspace_id, requested_operation, task_id, validation_id, created_at, request_json,
                 state, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'RESERVED', ?)""",
                (attempt_id, source_request_id, source_event_id, idempotency_key, authority_id,
                 agent_id, workspace_id, requested_operation, task_id, validation_id,
                 created_at, request_json, now),
            )
            conn.execute(
                """INSERT INTO idempotency_keys
                (idempotency_key, created_ts, agent_id, action_type, event_id, result_json)
                VALUES (?, ?, ?, ?, ?, NULL)""",
                (idempotency_key, now, agent_id, requested_operation, source_event_id),
            )
            conn.commit()
            return self.get_attempt(attempt_id) or {}

    def begin_attempt(self, attempt_id: str, owner_id: str, lease_seconds: float) -> Optional[int]:
        now = datetime.now(timezone.utc)
        expiry = (now + timedelta(seconds=max(0.1, lease_seconds))).isoformat()
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """SELECT state, generation, lease_expiry, source_event_id, task_id,
                   validation_id, source_request_id FROM execution_attempts WHERE attempt_id = ?""",
                (attempt_id,),
            ).fetchone()
            if not row:
                conn.rollback()
                return None
            if row["state"] == "RUNNING" and row["lease_expiry"] <= now.isoformat():
                conn.execute("UPDATE execution_attempts SET state = 'NEEDS_RECONCILIATION', generation = generation + 1, owner_id = NULL, lease_expiry = NULL, updated_at = ? WHERE attempt_id = ?", (now.isoformat(), attempt_id))
                if row["task_id"]:
                    if row["validation_id"]:
                        run = conn.execute("SELECT * FROM validation_runs WHERE validation_id = ?",
                                           (row["validation_id"],)).fetchone()
                        self._finish_validation_error(conn, run, "NEEDS_RECONCILIATION", owner_id,
                            {"reason": "validator_attempt_lease_expired"}, now.isoformat())
                        return None
                    self._set_task_state(conn, row["task_id"], "NEEDS_RECONCILIATION",
                                         "task_needs_reconciliation", owner_id,
                                         row["source_request_id"], attempt_id, now.isoformat())
                conn.commit()
                return None
            if row["state"] != "RESERVED":
                conn.commit()
                return None
            if row["source_event_id"] is not None and not conn.execute(
                """SELECT 1 FROM leases WHERE event_id = ? AND claimed_by = ? AND lease_expiry > ?""",
                (row["source_event_id"], owner_id, now.isoformat()),
            ).fetchone():
                conn.commit()
                return None
            if row["task_id"]:
                task = conn.execute("SELECT state FROM owner_tasks WHERE task_id = ?", (row["task_id"],)).fetchone()
                valid_states = {"READY_FOR_VALIDATION"} if row["validation_id"] else {"ASSIGNED", "EXECUTING"}
                if not task or task["state"] not in valid_states:
                    conn.commit()
                    return None
            generation = int(row["generation"]) + 1
            conn.execute(
                """UPDATE execution_attempts SET state = 'RUNNING', generation = ?, owner_id = ?,
                lease_expiry = ?, started_at = ?, updated_at = ? WHERE attempt_id = ?""",
                (generation, owner_id, expiry, now.isoformat(), now.isoformat(), attempt_id),
            )
            if row["task_id"]:
                if row["validation_id"]:
                    validation = conn.execute("SELECT * FROM validation_runs WHERE validation_id = ?",
                                              (row["validation_id"],)).fetchone()
                    if not validation or validation["status"] != "PENDING":
                        conn.rollback()
                        return None
                    conn.execute(
                        """UPDATE validation_runs SET status = 'RUNNING', started_at = ?,
                           related_attempt_id = ?, updated_at = ? WHERE validation_id = ?""",
                        (now.isoformat(), attempt_id, now.isoformat(), row["validation_id"]),
                    )
                    self._set_task_state(conn, row["task_id"], "VALIDATING", "task_validation_started",
                                         owner_id, row["source_request_id"], attempt_id, now.isoformat())
                else:
                    self._set_task_state(conn, row["task_id"], "EXECUTING", "task_execution_started",
                                         owner_id, row["source_request_id"], attempt_id, now.isoformat())
            conn.commit()
            return generation

    def renew_attempt_lease(self, attempt_id: str, owner_id: str, generation: int, lease_seconds: float) -> bool:
        now = datetime.now(timezone.utc)
        expiry = (now + timedelta(seconds=max(0.1, lease_seconds))).isoformat()
        with self._connection() as conn:
            cursor = conn.execute(
                """UPDATE execution_attempts SET lease_expiry = ?, updated_at = ?
                WHERE attempt_id = ? AND state = 'RUNNING' AND owner_id = ? AND generation = ?
                  AND lease_expiry > ? AND (source_event_id IS NULL OR EXISTS
                    (SELECT 1 FROM leases WHERE event_id = source_event_id AND claimed_by = ? AND lease_expiry > ?))""",
                (expiry, now.isoformat(), attempt_id, owner_id, generation, now.isoformat(),
                 owner_id, now.isoformat()),
            )
            conn.commit()
            return cursor.rowcount == 1

    def renew_event_lease(self, event_id: int, consumer_id: str, lease_seconds: float) -> bool:
        now = datetime.now(timezone.utc)
        expiry = (now + timedelta(seconds=max(0.1, lease_seconds))).isoformat()
        with self._connection() as conn:
            cursor = conn.execute(
                """UPDATE leases SET lease_expiry = ? WHERE event_id = ? AND claimed_by = ?
                   AND lease_expiry > ?""",
                (expiry, event_id, consumer_id, now.isoformat()),
            )
            conn.commit()
            return cursor.rowcount == 1

    def record_attempt_outcome(self, attempt_id: str, owner_id: str, generation: int,
                               state: str, outcome: Dict[str, Any]) -> Optional[int]:
        if state not in {"SUCCEEDED", "FAILED", "TIMED_OUT", "NEEDS_RECONCILIATION"}:
            raise ValueError("Invalid terminal attempt state.")
        now = iso_now()
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM execution_attempts WHERE attempt_id = ?", (attempt_id,)).fetchone()
            if not row or row["state"] != "RUNNING" or row["owner_id"] != owner_id or row["generation"] != generation or row["lease_expiry"] <= now:
                conn.rollback()
                return None
            if row["source_event_id"] is not None and not conn.execute(
                "SELECT 1 FROM leases WHERE event_id = ? AND claimed_by = ? AND lease_expiry > ?",
                (row["source_event_id"], owner_id, now),
            ).fetchone():
                conn.rollback()
                return None
            request = json.loads(row["request_json"])
            result_json = json.dumps(outcome, ensure_ascii=True)
            audit = conn.execute(
                """INSERT INTO tool_audit (ts, agent_id, action_type, working_dir, idempotency_key,
                allowed, reason, payload_json, result_json, correlation_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (now, row["agent_id"], row["requested_operation"], request["working_dir"],
                 row["idempotency_key"], int(state == "SUCCEEDED"), outcome.get("reason"),
                 json.dumps(request["payload"], ensure_ascii=True), result_json, request.get("correlation_id")),
            )
            audit_id = int(audit.lastrowid)
            conn.execute(
                """UPDATE execution_attempts SET state = ?, outcome_json = ?, audit_id = ?,
                   owner_id = NULL, lease_expiry = NULL, updated_at = ? WHERE attempt_id = ?""",
                (state, result_json, audit_id, now, attempt_id),
            )
            conn.execute("UPDATE idempotency_keys SET result_json = ? WHERE idempotency_key = ?",
                         (result_json, row["idempotency_key"]))
            if row["task_id"] and row["validation_id"]:
                validation = conn.execute("SELECT * FROM validation_runs WHERE validation_id = ?",
                                          (row["validation_id"],)).fetchone()
                if state == "NEEDS_RECONCILIATION":
                    self._finish_validation_error(conn, validation, "NEEDS_RECONCILIATION",
                        owner_id, {"reason": "validator_attempt_unknown", "attempt_id": attempt_id}, now)
                    return audit_id
                if state in {"FAILED", "TIMED_OUT"}:
                    self._finish_validation_error(conn, validation, "ERROR", owner_id,
                        {"reason": "validator_tool_failed", "attempt_id": attempt_id,
                         "attempt_state": state, "tool_outcome": outcome}, now)
                    return audit_id
            elif row["task_id"]:
                task = conn.execute("SELECT state FROM owner_tasks WHERE task_id = ?", (row["task_id"],)).fetchone()
                if state == "NEEDS_RECONCILIATION" or task["state"] == "NEEDS_RECONCILIATION":
                    new_state, event_type = "NEEDS_RECONCILIATION", "task_needs_reconciliation"
                elif state in {"FAILED", "TIMED_OUT"} or task["state"] == "EXECUTION_FAILED":
                    new_state, event_type = "EXECUTION_FAILED", "task_execution_failed"
                else:
                    active = conn.execute(
                        """SELECT 1 FROM execution_attempts WHERE task_id = ?
                           AND state IN ('RESERVED', 'RUNNING') LIMIT 1""", (row["task_id"],)
                    ).fetchone()
                    new_state = "EXECUTING" if active else "READY_FOR_VALIDATION"
                    event_type = "task_execution_succeeded"
                self._set_task_state(conn, row["task_id"], new_state, event_type,
                                     owner_id, row["source_request_id"], attempt_id, now)
                if state == "SUCCEEDED" and row["requested_operation"] == "WRITE_FILE":
                    reference = request["payload"].get("path")
                    if isinstance(reference, str) and reference:
                        file_path = Path(reference).resolve()
                        try:
                            file_bytes = file_path.read_bytes()
                        except OSError:
                            file_bytes = None
                        if file_bytes is not None:
                            conn.execute(
                                """INSERT OR IGNORE INTO owner_task_artifacts
                                   (artifact_id, task_id, attempt_id, kind, reference, workspace_id,
                                    producer_id, size_bytes, sha256, created_at)
                                   VALUES (?, ?, ?, 'FILE', ?, ?, ?, ?, ?, ?)""",
                                (str(uuid.uuid4()), row["task_id"], attempt_id, str(file_path),
                                 row["workspace_id"], row["agent_id"], len(file_bytes),
                                 hashlib.sha256(file_bytes).hexdigest(), now),
                            )
            conn.commit()
            return audit_id

    def reconcile_attempts(self) -> Dict[str, int]:
        """Fence expired executions; never infer that an external effect failed."""
        now = iso_now()
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            expired = conn.execute(
                """SELECT attempt_id, task_id, validation_id, source_request_id, owner_id FROM execution_attempts
                   WHERE state = 'RUNNING' AND lease_expiry <= ?""", (now,)
            ).fetchall()
            for row in expired:
                conn.execute(
                    """UPDATE execution_attempts SET state = 'NEEDS_RECONCILIATION', generation = generation + 1,
                       owner_id = NULL, lease_expiry = NULL, updated_at = ? WHERE attempt_id = ?""",
                    (now, row["attempt_id"]),
                )
                if row["task_id"]:
                    if row["validation_id"]:
                        run = conn.execute("SELECT * FROM validation_runs WHERE validation_id = ?",
                                           (row["validation_id"],)).fetchone()
                        self._finish_validation_error(conn, run, "NEEDS_RECONCILIATION",
                            row["owner_id"] or "recovery",
                            {"reason": "validator_attempt_lease_expired",
                             "attempt_id": row["attempt_id"]}, now)
                    else:
                        self._set_task_state(conn, row["task_id"], "NEEDS_RECONCILIATION",
                                             "task_needs_reconciliation", row["owner_id"] or "recovery",
                                             row["source_request_id"], row["attempt_id"], now)
            stranded = conn.execute(
                """SELECT vr.* FROM validation_runs vr
                   JOIN execution_attempts ea ON ea.attempt_id = vr.related_attempt_id
                   WHERE vr.status = 'RUNNING' AND ea.state IN ('SUCCEEDED','FAILED','TIMED_OUT','NEEDS_RECONCILIATION')"""
            ).fetchall()
            for run in stranded:
                attempt = conn.execute("SELECT state FROM execution_attempts WHERE attempt_id = ?",
                                       (run["related_attempt_id"],)).fetchone()
                unknown = attempt["state"] == "NEEDS_RECONCILIATION"
                self._finish_validation_error(
                    conn, run, "NEEDS_RECONCILIATION" if unknown else "ERROR", "recovery",
                    {"reason": "validation_interrupted_before_verdict",
                     "attempt_id": run["related_attempt_id"], "attempt_state": attempt["state"]}, now)
            conn.commit()
        return {"fenced_unknown": len(expired), "validation_reconciled": len(stranded)}

    def list_attempts(self) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute("SELECT * FROM execution_attempts ORDER BY rowid").fetchall()
        return [self._attempt_dict(row) for row in rows]

    def publish_attempt_result(self, attempt_id: str) -> Optional[int]:
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM execution_attempts WHERE attempt_id = ?", (attempt_id,)).fetchone()
            if not row or row["state"] not in {"SUCCEEDED", "FAILED", "TIMED_OUT", "NEEDS_RECONCILIATION"} or not row["outcome_json"] or row["source_event_id"] is None:
                conn.commit()
                return None
            if row["published_event_id"] is not None:
                conn.commit()
                return int(row["published_event_id"])
            request = json.loads(row["request_json"])
            outcome = json.loads(row["outcome_json"])
            payload = {**outcome, "attempt_id": attempt_id, "source_event_id": row["source_event_id"],
                       "idempotency_key": row["idempotency_key"], "audit_event_id": row["audit_id"]}
            cursor = conn.execute(
                """INSERT INTO events (ts, type, origin_id, target_agent, payload_json, status, correlation_id)
                   VALUES (?, 'TOOL_RESULT', ?, ?, ?, 'PENDING', ?)""",
                (iso_now(), row["agent_id"], request.get("reply_to") or "command",
                 json.dumps(payload, ensure_ascii=True), request.get("correlation_id")),
            )
            result_id = int(cursor.lastrowid)
            conn.execute("UPDATE execution_attempts SET published_event_id = ?, updated_at = ? WHERE attempt_id = ?",
                         (result_id, iso_now(), attempt_id))
            conn.commit()
            return result_id

    def ack_attempt_event(self, attempt_id: str, consumer_id: Optional[str] = None) -> bool:
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT source_event_id, published_event_id, acknowledged_at FROM execution_attempts WHERE attempt_id = ?", (attempt_id,)).fetchone()
            if not row or row["published_event_id"] is None or row["source_event_id"] is None:
                conn.rollback()
                return False
            if row["acknowledged_at"]:
                conn.commit()
                return True
            event_id = int(row["source_event_id"])
            lease = conn.execute("SELECT claimed_by, lease_expiry FROM leases WHERE event_id = ?", (event_id,)).fetchone()
            if lease and lease["lease_expiry"] > iso_now() and lease["claimed_by"] != consumer_id:
                conn.rollback()
                return False
            conn.execute("UPDATE events SET status = 'DONE', error = NULL WHERE id = ?", (event_id,))
            conn.execute("DELETE FROM leases WHERE event_id = ?", (event_id,))
            conn.execute("UPDATE execution_attempts SET acknowledged_at = ?, updated_at = ? WHERE attempt_id = ?",
                         (iso_now(), iso_now(), attempt_id))
            conn.commit()
            return True

    def record_worker_heartbeat(
        self,
        *,
        agent_id: str,
        consumer_id: str,
        pid: int,
        ts: Optional[str] = None,
    ) -> None:
        timestamp = ts or iso_now()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO worker_heartbeats (agent_id, consumer_id, pid, ts)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    consumer_id = excluded.consumer_id,
                    pid = excluded.pid,
                    ts = excluded.ts
                """,
                (str(agent_id), str(consumer_id), int(pid), timestamp),
            )
            conn.commit()

    def get_worker_heartbeat(self, agent_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT agent_id, consumer_id, pid, ts FROM worker_heartbeats WHERE agent_id = ?",
                (str(agent_id),),
            ).fetchone()
        if row is None:
            return None
        return {
            "agent_id": str(row["agent_id"]),
            "consumer_id": str(row["consumer_id"]),
            "pid": int(row["pid"]),
            "ts": str(row["ts"]),
        }

    def list_worker_heartbeats(self) -> Dict[str, Dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute("SELECT agent_id, consumer_id, pid, ts FROM worker_heartbeats").fetchall()
        out: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            out[str(row["agent_id"])] = {
                "agent_id": str(row["agent_id"]),
                "consumer_id": str(row["consumer_id"]),
                "pid": int(row["pid"]),
                "ts": str(row["ts"]),
            }
        return out

    def _try_claim_next(
        self,
        *,
        consumer_id: str,
        target_agent: Optional[str],
        include_unrouted: bool,
        lease_seconds: Optional[float],
    ) -> Optional[SubstrateEvent]:
        lease_window = max(0.1, float(lease_seconds if lease_seconds is not None else self.lease_seconds))
        claimed_at = datetime.now(timezone.utc)
        lease_expiry = (claimed_at + timedelta(seconds=lease_window)).isoformat()
        claimed_ts = claimed_at.isoformat()
        now_iso = claimed_at.isoformat()

        where_parts = ["e.status = 'PENDING'", "l.event_id IS NULL"]
        params: List[Any] = []
        if target_agent is not None:
            if include_unrouted:
                where_parts.append("(e.target_agent = ? OR e.target_agent IS NULL OR e.target_agent = '')")
                params.append(target_agent)
            else:
                where_parts.append("e.target_agent = ?")
                params.append(target_agent)
        where_clause = " AND ".join(where_parts)

        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._release_expired_leases_locked(conn, now_iso)
            row = conn.execute(
                f"""
                SELECT e.*
                FROM events e
                LEFT JOIN leases l ON l.event_id = e.id
                WHERE {where_clause}
                ORDER BY e.id ASC
                LIMIT 1
                """,
                tuple(params),
            ).fetchone()
            if row is None:
                conn.commit()
                return None

            event_id = int(row["id"])
            try:
                conn.execute(
                    """
                    INSERT INTO leases (event_id, claimed_by, claim_ts, lease_expiry)
                    VALUES (?, ?, ?, ?)
                    """,
                    (event_id, consumer_id, claimed_ts, lease_expiry),
                )
            except sqlite3.IntegrityError:
                conn.rollback()
                return None

            conn.execute(
                "UPDATE events SET status = 'CLAIMED' WHERE id = ?",
                (event_id,),
            )
            conn.commit()
            return SubstrateEvent.from_row(row)

    def _release_expired_leases_locked(self, conn: sqlite3.Connection, now_iso: str) -> None:
        conn.execute(
            """
            UPDATE events
            SET status = 'PENDING'
            WHERE id IN (
                SELECT event_id FROM leases WHERE lease_expiry <= ?
            )
            """,
            (now_iso,),
        )
        conn.execute(
            "DELETE FROM leases WHERE lease_expiry <= ?",
            (now_iso,),
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            str(self.db_path),
            timeout=self.busy_timeout_ms / 1000.0,
            isolation_level=None,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms};")
        connection.execute("PRAGMA journal_mode=WAL;")
        connection.execute("PRAGMA synchronous=FULL;")
        connection.execute("PRAGMA foreign_keys=ON;")
        return connection

    @contextmanager
    def _connection(self) -> sqlite3.Connection:
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    def _initialize_schema(self) -> None:
        schema_path = Path(__file__).with_name("schema.sql")
        schema_sql = schema_path.read_text(encoding="utf-8")
        with self._connection() as conn:
            conn.executescript(schema_sql)
            columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(tool_audit)").fetchall()
            }
            if "idempotency_key" not in columns:
                conn.execute("ALTER TABLE tool_audit ADD COLUMN idempotency_key TEXT")
            attempt_columns = {str(row["name"]) for row in conn.execute(
                "PRAGMA table_info(execution_attempts)").fetchall()}
            if "task_id" not in attempt_columns:
                conn.execute("ALTER TABLE execution_attempts ADD COLUMN task_id TEXT REFERENCES owner_tasks(task_id)")
            if "validation_id" not in attempt_columns:
                conn.execute("ALTER TABLE execution_attempts ADD COLUMN validation_id TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_execution_attempts_task_id ON execution_attempts(task_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_execution_attempts_validation_id ON execution_attempts(validation_id)")
            baton_columns = {str(row["name"]) for row in conn.execute(
                "PRAGMA table_info(capability_batons)").fetchall()}
            if "working_tree_hash" not in baton_columns:
                conn.execute("ALTER TABLE capability_batons ADD COLUMN working_tree_hash TEXT NOT NULL DEFAULT ''")
            if "next_objective" not in baton_columns:
                conn.execute("ALTER TABLE capability_batons ADD COLUMN next_objective TEXT NOT NULL DEFAULT ''")
            if "results_json" not in baton_columns:
                conn.execute("ALTER TABLE capability_batons ADD COLUMN results_json TEXT NOT NULL DEFAULT '{}'")
            dispatch_columns = {str(row["name"]) for row in conn.execute(
                "PRAGMA table_info(baton_dispatches)").fetchall()}
            dispatch_migrations = {
                "handoff_task_id": "TEXT REFERENCES owner_tasks(task_id)",
                "attempt_id": "TEXT REFERENCES execution_attempts(attempt_id)",
                "payload_reference": "TEXT", "result_reference": "TEXT",
                "workspace_root": "TEXT", "credential_sha256": "TEXT",
                "chief_authorized_by": "TEXT",
                "pickup_owner_id": "TEXT", "pickup_generation": "INTEGER",
                "dispatched_at": "TEXT", "acknowledged_at": "TEXT",
                "result_at": "TEXT", "result_sha256": "TEXT", "result_size_bytes": "INTEGER",
            }
            for name, sql_type in dispatch_migrations.items():
                if name not in dispatch_columns:
                    conn.execute(f"ALTER TABLE baton_dispatches ADD COLUMN {name} {sql_type}")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_baton_dispatches_credential "
                         "ON baton_dispatches(credential_sha256) WHERE credential_sha256 IS NOT NULL")
            artifact_columns = {str(row["name"]) for row in conn.execute(
                "PRAGMA table_info(owner_task_artifacts)").fetchall()}
            artifact_migrations = {
                "artifact_id": "TEXT",
                "kind": "TEXT",
                "workspace_id": "TEXT",
                "producer_id": "TEXT",
                "size_bytes": "INTEGER",
                "sha256": "TEXT",
            }
            for name, sql_type in artifact_migrations.items():
                if name not in artifact_columns:
                    conn.execute(f"ALTER TABLE owner_task_artifacts ADD COLUMN {name} {sql_type}")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_owner_task_artifacts_id ON owner_task_artifacts(artifact_id)")
            conn.commit()
