"""Durable external pickup and result return on the verified baton dispatch row.

The dispatch ID is the handoff ID. A separate process uses only the pickup,
renew, and submit methods; the trusted backend prepares and publishes work.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any, Dict, Optional

from appshak_substrate.baton_routing import CapabilityRoutingPolicy
from appshak_substrate.mailstore_sqlite import SQLiteMailStore
from appshak_substrate.policy import ToolPolicy
from appshak_substrate.tool_gateway import ToolGateway
from appshak_substrate.types import ToolActionType, ToolRequest, iso_now


class ExternalHandoffManager:
    """Provider-neutral backend authority over one durable baton dispatch."""

    def __init__(self, store: SQLiteMailStore, *, tool_policy: Optional[ToolPolicy] = None) -> None:
        self.store = store
        self.tool_policy = tool_policy or ToolPolicy()

    @staticmethod
    def _public(row: Any) -> Dict[str, Any]:
        item = dict(row)
        item.pop("credential_sha256", None)
        for key in ("route_json", "context_json"):
            raw = item.pop(key, None)
            item[key.removesuffix("_json")] = json.loads(raw) if raw else None
        return item

    def get(self, dispatch_id: str) -> Optional[Dict[str, Any]]:
        with self.store._connection() as conn:
            row = conn.execute("SELECT * FROM baton_dispatches WHERE dispatch_id = ?", (dispatch_id,)).fetchone()
            return self._public(row) if row else None

    @staticmethod
    def _row(conn: Any, dispatch_id: str) -> Any:
        row = conn.execute("SELECT * FROM baton_dispatches WHERE dispatch_id = ?", (dispatch_id,)).fetchone()
        if row is None:
            raise ValueError("Handoff dispatch does not exist.")
        return row

    @staticmethod
    def _authenticate(row: Any, *, target_id: str, worker_id: str, secret: str) -> str:
        if not all(isinstance(value, str) and value.strip() for value in (target_id, worker_id, secret)):
            raise PermissionError("External worker identity or credential is missing.")
        digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        if (not row["credential_sha256"] or not hmac.compare_digest(row["credential_sha256"], digest)
                or row["target_id"] != target_id):
            raise PermissionError("External worker is not authorized for this handoff.")
        return f"{target_id}:{worker_id}"

    def prepare(self, *, dispatch_id: str, task_id: str, worker_secret: str,
                authorized_by: str) -> Dict[str, Any]:
        """Bind an owner-approved destination task to the persisted route."""
        if not isinstance(worker_secret, str) or len(worker_secret) < 24:
            raise ValueError("An out-of-band worker credential of at least 24 characters is required.")
        digest = hashlib.sha256(worker_secret.encode("utf-8")).hexdigest()
        with self.store._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            dispatch = self._row(conn, dispatch_id)
            baton = conn.execute("SELECT * FROM capability_batons WHERE baton_id = ?",
                                 (dispatch["baton_id"],)).fetchone()
            if not baton or baton["status"] != "VERIFIED":
                raise ValueError("Only a verified baton can own an external handoff.")
            if dispatch["status"] != "READY_FOR_EXTERNAL_DISPATCH" and not dispatch["handoff_task_id"]:
                raise ValueError("No configured external target is ready.")
            route = json.loads(dispatch["route_json"]) if dispatch["route_json"] else None
            if not route or route.get("target_id") != dispatch["target_id"] or route.get("capability") != dispatch["required_capability"]:
                raise ValueError("Persisted routing decision is inconsistent.")
            workspace_raw = route.get("workspace_root")
            if not isinstance(workspace_raw, str) or not Path(workspace_raw).is_dir():
                raise ValueError("Selected target has no configured, existing workspace.")
            workspace = Path(workspace_raw).resolve()
            source = conn.execute("SELECT * FROM owner_tasks WHERE task_id = ?", (baton["task_id"],)).fetchone()
            task = conn.execute("SELECT * FROM owner_tasks WHERE task_id = ?", (task_id,)).fetchone()
            expected_workspace = ToolGateway.workspace_identity(dispatch["target_id"], workspace)
            if (not source or source["state"] != "COMPLETE" or not task
                    or task["owner_id"] != source["owner_id"]
                    or task["source_request_id"] != f"handoff:{dispatch_id}"
                    or task["objective"] != baton["next_objective"]
                    or (task["assigned_agent"], task["workspace_id"], task["assignment_authority_id"])
                    != (dispatch["target_id"], expected_workspace, task["authority_id"])):
                raise ValueError("Destination task is not the authorized owner, objective, target, and workspace contract.")
            if not conn.execute("SELECT 1 FROM task_acceptance_criteria WHERE task_id = ? AND required = 1",
                                (task_id,)).fetchone():
                raise ValueError("Destination task requires a fixed acceptance criterion.")
            result_reference = str((workspace / f"handoff-{dispatch_id}.txt").resolve())
            decision = self.tool_policy.validate(ToolRequest(
                agent_id=dispatch["target_id"], action_type=ToolActionType.WRITE_FILE,
                working_dir=str(workspace), payload={"path": result_reference},
                authorized_by=authorized_by), worktree_root=workspace)
            if not decision.allowed:
                raise PermissionError(decision.reason)
            if dispatch["handoff_task_id"]:
                bound_contract = (dispatch["handoff_task_id"], dispatch["credential_sha256"],
                                  dispatch["result_reference"], dispatch["chief_authorized_by"])
                if bound_contract != (task_id, digest, result_reference, authorized_by):
                    raise ValueError("Handoff identity is already bound to another contract.")
            else:
                if task["state"] != "ASSIGNED":
                    raise ValueError("Destination task must be assigned before handoff preparation.")
                conn.execute("""UPDATE baton_dispatches SET handoff_task_id = ?, payload_reference = ?,
                    result_reference = ?, workspace_root = ?, credential_sha256 = ?,
                    chief_authorized_by = ?, updated_at = ?
                    WHERE dispatch_id = ?""",
                    (task_id, f"sqlite:baton_dispatches/{dispatch_id}/context", result_reference,
                     str(workspace), digest, authorized_by, iso_now(), dispatch_id))
            conn.commit()
        return self.get(dispatch_id) or {}

    def publish(self, dispatch_id: str, policy: CapabilityRoutingPolicy) -> Dict[str, Any]:
        """Persist one reserved attempt before a separate worker may pick up."""
        with self.store._connection() as conn:
            dispatch = self._row(conn, dispatch_id)
            if dispatch["status"] in {"HANDOFF_DISPATCHED", "EXTERNAL_PICKUP_ACKNOWLEDGED",
                                      "RESULT_RETURNED", "FAILED", "UNKNOWN"}:
                return self._public(dispatch)
            if dispatch["status"] != "READY_FOR_EXTERNAL_DISPATCH" or not dispatch["handoff_task_id"]:
                raise ValueError("Handoff is not prepared for dispatch.")
            baton = conn.execute("SELECT task_id, status FROM capability_batons WHERE baton_id = ?",
                                 (dispatch["baton_id"],)).fetchone()
            source = conn.execute("SELECT state FROM owner_tasks WHERE task_id = ?",
                                  (baton["task_id"],)).fetchone() if baton else None
            if not baton or baton["status"] != "VERIFIED" or not source or source["state"] != "COMPLETE":
                raise ValueError("Source baton and completed task are no longer current for dispatch.")
            route = json.loads(dispatch["route_json"])
            current = policy.resolve(dispatch["required_capability"], requested_target=dispatch["target_id"])
            if (current is None or current != route or not Path(dispatch["workspace_root"]).is_dir()):
                with self.store._connection() as update:
                    update.execute("BEGIN IMMEDIATE")
                    update.execute("""UPDATE baton_dispatches SET status = 'WAITING_FOR_CAPABILITY',
                        reason = 'configured target unavailable after routing', updated_at = ?
                        WHERE dispatch_id = ? AND status = 'READY_FOR_EXTERNAL_DISPATCH'""",
                        (iso_now(), dispatch_id))
                    update.commit()
                return self.get(dispatch_id) or {}
            task = conn.execute("SELECT * FROM owner_tasks WHERE task_id = ?",
                                (dispatch["handoff_task_id"],)).fetchone()
            if (not task or task["state"] != "ASSIGNED"
                    or task["assigned_agent"] != dispatch["target_id"]
                    or task["workspace_id"] != ToolGateway.workspace_identity(
                        dispatch["target_id"], dispatch["workspace_root"])):
                raise ValueError("Destination task is no longer assigned to the selected target and workspace.")
            decision = self.tool_policy.validate(ToolRequest(
                agent_id=dispatch["target_id"], action_type=ToolActionType.WRITE_FILE,
                working_dir=dispatch["workspace_root"], payload={"path": dispatch["result_reference"]},
                authorized_by=dispatch["chief_authorized_by"]),
                worktree_root=Path(dispatch["workspace_root"]))
            if not decision.allowed:
                raise PermissionError(decision.reason)
        request_id = f"external:{dispatch_id}"
        attempt = self.store.reserve_attempt(
            source_request_id=request_id, source_event_id=None, idempotency_key=request_id,
            authority_id=task["authority_id"], agent_id=dispatch["target_id"],
            workspace_id=task["workspace_id"], requested_operation="WRITE_FILE",
            created_at=dispatch["created_at"], task_id=task["task_id"],
            request={"working_dir": dispatch["workspace_root"],
                     "payload": {"path": dispatch["result_reference"], "idempotency_key": request_id},
                     "authorized_by": dispatch["chief_authorized_by"], "correlation_id": dispatch_id},
        )
        with self.store._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            latest = self._row(conn, dispatch_id)
            if latest["status"] == "READY_FOR_EXTERNAL_DISPATCH":
                now = iso_now()
                conn.execute("""UPDATE baton_dispatches SET status = 'HANDOFF_DISPATCHED',
                    attempt_id = ?, dispatched_at = ?, updated_at = ? WHERE dispatch_id = ?""",
                    (attempt["attempt_id"], now, now, dispatch_id))
            conn.commit()
        return self.get(dispatch_id) or {}

    def pickup(self, dispatch_id: str, *, target_id: str, worker_id: str,
               secret: str, lease_seconds: float = 30.0) -> Dict[str, Any]:
        with self.store._connection() as conn:
            row = self._row(conn, dispatch_id)
            owner = self._authenticate(row, target_id=target_id, worker_id=worker_id, secret=secret)
            if row["status"] not in {"HANDOFF_DISPATCHED", "EXTERNAL_PICKUP_ACKNOWLEDGED"}:
                raise ValueError("Handoff is not available for pickup.")
            attempt_id = row["attempt_id"]
            if not attempt_id:
                raise ValueError("Handoff has no durable execution attempt.")
        attempt = self.store.get_attempt(attempt_id)
        self._assert_binding(row, attempt)
        now = iso_now()
        if (attempt and attempt["state"] == "RUNNING" and attempt["owner_id"] == owner
                and attempt["lease_expiry"] > now):
            generation = attempt["generation"]
        else:
            generation = self.store.begin_attempt(attempt_id, owner, lease_seconds)
        if generation is None:
            raise ValueError("Another worker owns this handoff or its effect requires reconciliation.")
        with self.store._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = self._row(conn, dispatch_id)
            if row["status"] == "HANDOFF_DISPATCHED":
                timestamp = iso_now()
                conn.execute("""UPDATE baton_dispatches SET status = 'EXTERNAL_PICKUP_ACKNOWLEDGED',
                    pickup_owner_id = ?, pickup_generation = ?, acknowledged_at = ?, updated_at = ?
                    WHERE dispatch_id = ?""",
                    (owner, generation, timestamp, timestamp, dispatch_id))
            conn.commit()
        return self.get(dispatch_id) or {}

    def renew(self, dispatch_id: str, *, target_id: str, worker_id: str,
              secret: str, generation: int, lease_seconds: float = 30.0) -> bool:
        with self.store._connection() as conn:
            row = self._row(conn, dispatch_id)
            owner = self._authenticate(row, target_id=target_id, worker_id=worker_id, secret=secret)
            if row["status"] != "EXTERNAL_PICKUP_ACKNOWLEDGED" or row["pickup_generation"] != generation:
                return False
        return self.store.renew_attempt_lease(row["attempt_id"], owner, generation, lease_seconds)

    @staticmethod
    def _assert_binding(row: Any, attempt: Any) -> None:
        route = json.loads(row["route_json"]) if row["route_json"] else None
        if (not route or route.get("target_id") != row["target_id"]
                or route.get("capability") != row["required_capability"]
                or not attempt or attempt["task_id"] != row["handoff_task_id"]
                or attempt["agent_id"] != row["target_id"]
                or attempt["idempotency_key"] != f"external:{row['dispatch_id']}"
                or attempt["workspace_id"] != ToolGateway.workspace_identity(
                    row["target_id"], row["workspace_root"])):
            raise ValueError("Durable attempt does not match the handoff task and target.")

    def submit_result(self, dispatch_id: str, *, target_id: str, worker_id: str,
                      secret: str, generation: int, state: str,
                      sha256: Optional[str] = None) -> Dict[str, Any]:
        if state not in {"SUCCEEDED", "FAILED"}:
            raise ValueError("External result must be SUCCEEDED or FAILED.")
        with self.store._connection() as conn:
            row = self._row(conn, dispatch_id)
            owner = self._authenticate(row, target_id=target_id, worker_id=worker_id, secret=secret)
            if row["status"] in {"RESULT_RETURNED", "FAILED"}:
                if ((row["status"] == "RESULT_RETURNED") == (state == "SUCCEEDED")
                        and row["pickup_owner_id"] == owner and row["pickup_generation"] == generation
                        and (state == "FAILED" or row["result_sha256"] == sha256)):
                    return self._public(row)
                raise ValueError("A conflicting terminal result was already recorded.")
            if (row["status"] != "EXTERNAL_PICKUP_ACKNOWLEDGED"
                    or row["pickup_owner_id"] != owner or row["pickup_generation"] != generation):
                raise ValueError("Result does not belong to the acknowledged handoff owner.")
            attempt_id = row["attempt_id"]
            result_reference = row["result_reference"]
        self._assert_binding(row, self.store.get_attempt(attempt_id))
        size = None
        if state == "SUCCEEDED":
            if not isinstance(sha256, str) or len(sha256) != 64:
                raise ValueError("Successful result requires a SHA-256 digest.")
            result_path = Path(result_reference).resolve()
            workspace = Path(row["workspace_root"]).resolve()
            if not result_path.is_relative_to(workspace) or not result_path.is_file():
                raise ValueError("Result evidence is missing or outside the assigned workspace.")
            result_bytes = result_path.read_bytes()
            size = len(result_bytes)
            if size > 10 * 1024 * 1024 or not hmac.compare_digest(hashlib.sha256(result_bytes).hexdigest(), sha256):
                raise ValueError("Result evidence integrity failed.")
        outcome = {"allowed": state == "SUCCEEDED", "reason": None if state == "SUCCEEDED" else "external_worker_failed",
                   "state": state, "return_code": 0 if state == "SUCCEEDED" else 1,
                   "result_sha256": sha256 if state == "SUCCEEDED" else None}
        audit_id = self.store.record_attempt_outcome(attempt_id, owner, generation, state, outcome)
        if audit_id is None:
            attempt = self.store.get_attempt(attempt_id)
            if attempt and attempt["state"] in {"SUCCEEDED", "FAILED"}:
                recovered = self.reconcile(dispatch_id)
                if ((recovered["status"] == "RESULT_RETURNED") == (state == "SUCCEEDED")
                        and recovered["status"] in {"RESULT_RETURNED", "FAILED"}
                        and (state == "FAILED" or recovered["result_sha256"] == sha256)):
                    return recovered
            raise ValueError("External attempt lease was lost; reconciliation is required.")
        if state == "SUCCEEDED":
            artifact = next((item for item in self.store.get_owner_task(row["handoff_task_id"])["artifacts"]
                             if item["attempt_id"] == attempt_id), None)
            if not artifact or artifact["sha256"] != sha256 or artifact["size_bytes"] != size:
                self._mark_unknown(dispatch_id, "result artifact changed during return")
                raise ValueError("Result artifact changed during return; reconciliation is required.")
        with self.store._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            timestamp = iso_now()
            conn.execute("""UPDATE baton_dispatches SET status = ?, result_at = ?, result_sha256 = ?,
                result_size_bytes = ?, reason = ?, updated_at = ? WHERE dispatch_id = ?
                AND status = 'EXTERNAL_PICKUP_ACKNOWLEDGED'""",
                ("RESULT_RETURNED" if state == "SUCCEEDED" else "FAILED", timestamp,
                 sha256 if state == "SUCCEEDED" else None, size,
                 "external result returned" if state == "SUCCEEDED" else "external worker failed",
                 timestamp, dispatch_id))
            conn.commit()
        return self.get(dispatch_id) or {}

    def _mark_unknown(self, dispatch_id: str, reason: str) -> None:
        with self.store._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = self._row(conn, dispatch_id)
            if row["status"] not in {"RESULT_RETURNED", "FAILED", "UNKNOWN"}:
                now = iso_now()
                conn.execute("UPDATE baton_dispatches SET status = 'UNKNOWN', reason = ?, updated_at = ? WHERE dispatch_id = ?",
                             (reason, now, dispatch_id))
                task = conn.execute("SELECT state FROM owner_tasks WHERE task_id = ?", (row["handoff_task_id"],)).fetchone()
                if task and task["state"] in {"EXECUTING", "READY_FOR_VALIDATION"}:
                    self.store._set_task_state(conn, row["handoff_task_id"], "NEEDS_RECONCILIATION",
                        "task_needs_reconciliation", "system:external-handoff", dispatch_id,
                        row["attempt_id"], now)
            conn.commit()

    def reconcile(self, dispatch_id: str) -> Dict[str, Any]:
        """Recover persisted attempt truth without retrying an unknown effect."""
        with self.store._connection() as conn:
            row = self._row(conn, dispatch_id)
            attempt_id = row["attempt_id"]
        if not attempt_id or row["status"] in {"WAITING_FOR_CAPABILITY", "READY_FOR_EXTERNAL_DISPATCH",
                                                  "RESULT_RETURNED", "FAILED", "UNKNOWN"}:
            return self.get(dispatch_id) or {}
        self.store.reconcile_attempts()
        attempt = self.store.get_attempt(attempt_id)
        if not attempt:
            self._mark_unknown(dispatch_id, "durable attempt record missing")
        elif attempt["state"] == "NEEDS_RECONCILIATION":
            self._mark_unknown(dispatch_id, "external effect unknown after lease expiry")
        elif attempt["state"] == "RUNNING" and row["status"] == "HANDOFF_DISPATCHED":
            with self.store._connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("""UPDATE baton_dispatches SET status = 'EXTERNAL_PICKUP_ACKNOWLEDGED',
                    pickup_owner_id = ?, pickup_generation = ?, acknowledged_at = ?, updated_at = ?
                    WHERE dispatch_id = ? AND status = 'HANDOFF_DISPATCHED'""",
                    (attempt["owner_id"], attempt["generation"], attempt["started_at"], iso_now(), dispatch_id))
                conn.commit()
        elif attempt["state"] in {"SUCCEEDED", "FAILED"}:
            if attempt["state"] == "SUCCEEDED":
                artifact = next((item for item in self.store.get_owner_task(row["handoff_task_id"])["artifacts"]
                                 if item["attempt_id"] == attempt_id), None)
                if (not artifact or not attempt["outcome"]
                        or attempt["outcome"].get("result_sha256") != artifact["sha256"]):
                    self._mark_unknown(dispatch_id, "successful attempt has no result artifact")
                    return self.get(dispatch_id) or {}
            with self.store._connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("""UPDATE baton_dispatches SET status = ?, result_at = ?,
                    result_sha256 = ?, result_size_bytes = ?, reason = ?, updated_at = ?
                    WHERE dispatch_id = ? AND status IN ('HANDOFF_DISPATCHED', 'EXTERNAL_PICKUP_ACKNOWLEDGED')""",
                    ("RESULT_RETURNED" if attempt["state"] == "SUCCEEDED" else "FAILED", iso_now(),
                     artifact["sha256"] if attempt["state"] == "SUCCEEDED" else None,
                     artifact["size_bytes"] if attempt["state"] == "SUCCEEDED" else None,
                     "external result returned" if attempt["state"] == "SUCCEEDED" else "external worker failed",
                     iso_now(), dispatch_id))
                conn.commit()
        return self.get(dispatch_id) or {}
