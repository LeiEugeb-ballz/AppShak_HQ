from __future__ import annotations

import json
import sqlite3
import time
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

        with self._connect() as conn:
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
        with self._connect() as conn:
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
        with self._connect() as conn:
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
        with self._connect() as conn:
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
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM events WHERE id = ?", (int(event_id),)).fetchone()
            if row is None:
                return None
            return SubstrateEvent.from_row(row)

    def list_events(self, *, status: Optional[str] = None) -> List[SubstrateEvent]:
        with self._connect() as conn:
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
        with self._connect() as conn:
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
        with self._connect() as conn:
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
        with self._connect() as conn:
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
        with self._connect() as conn:
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
        with self._connect() as conn:
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
        with self._connect() as conn:
            conn.execute(
                "UPDATE idempotency_keys SET result_json = ? WHERE idempotency_key = ?",
                (json.dumps(result, ensure_ascii=True), key),
            )
            conn.commit()

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

        with self._connect() as conn:
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

    def _initialize_schema(self) -> None:
        schema_path = Path(__file__).with_name("schema.sql")
        schema_sql = schema_path.read_text(encoding="utf-8")
        with self._connect() as conn:
            conn.executescript(schema_sql)
            columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(tool_audit)").fetchall()
            }
            if "idempotency_key" not in columns:
                conn.execute("ALTER TABLE tool_audit ADD COLUMN idempotency_key TEXT")
            conn.commit()
