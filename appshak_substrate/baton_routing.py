"""Durable verified batons and capability-only routing policy."""

from __future__ import annotations

import json
import hashlib
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from appshak_substrate.mailstore_sqlite import SQLiteMailStore
from appshak_substrate.types import iso_now


CAPABILITIES = frozenset({
    "REPOSITORY_INSPECTION", "RUNTIME_STABILIZATION", "IMPLEMENTATION", "INTEGRATION",
    "VALIDATION_IMPLEMENTATION", "ARCHITECTURAL_AUDIT", "ROOT_CAUSE_ANALYSIS", "CERTIFICATION",
})


@dataclass(frozen=True, slots=True)
class RouteTarget:
    target_id: str
    capabilities: tuple[str, ...]
    provider_class: str
    model_class: str
    priority: int = 100
    enabled: bool = True


class CapabilityRoutingPolicy:
    """Deterministic configured target selection; no product model is task truth."""

    def __init__(self, targets: Iterable[RouteTarget], *, version: str = "routing-policy-v1") -> None:
        self.version = str(version)
        self.targets = tuple(targets)
        if any(not target.target_id.strip() for target in self.targets):
            raise ValueError("Route target IDs must be non-empty.")
        if len({target.target_id for target in self.targets}) != len(self.targets):
            raise ValueError("Route target IDs must be unique.")
        if not self.version.strip():
            raise ValueError("Routing policy version must be non-empty.")
        for target in self.targets:
            if not target.provider_class.strip() or not target.model_class.strip():
                raise ValueError("Route provider and model classes must be non-empty.")
            if any(capability not in CAPABILITIES for capability in target.capabilities):
                raise ValueError("Route target contains an unknown capability.")

    @classmethod
    def default(cls) -> "CapabilityRoutingPolicy":
        # No deployment target is configured in source. Fail closed until the
        # caller supplies an explicit policy derived from deployment config.
        return cls(())

    def resolve(self, capability: str, *, requested_target: Optional[str] = None) -> Optional[Dict[str, Any]]:
        capability = str(capability).strip().upper()
        if capability not in CAPABILITIES:
            return None
        eligible = [target for target in self.targets
                    if target.enabled and capability in target.capabilities]
        if requested_target is not None:
            eligible = [target for target in eligible if target.target_id == requested_target]
        if not eligible:
            return None
        selected = sorted(eligible, key=lambda target: (target.priority, target.target_id))[0]
        return {
            "target_id": selected.target_id,
            "capability": capability,
            "provider_class": selected.provider_class,
            "model_class": selected.model_class,
            "policy_version": self.version,
            "priority": selected.priority,
        }


class VerifiedBatonManager:
    """Canonical baton authority backed by the existing SQLite substrate."""

    def __init__(self, store: SQLiteMailStore, repository_root: str | Path) -> None:
        self.store = store
        self.repository_root = Path(repository_root).resolve()

    @staticmethod
    def _row_dict(row: Any) -> Optional[Dict[str, Any]]:
        if not row:
            return None
        item = dict(row)
        for key in ("current_state_json", "results_json", "evidence_json", "verification_evidence_json"):
            raw = item.pop(key, None)
            item[key.removesuffix("_json")] = json.loads(raw) if raw else None
        return item

    @staticmethod
    def _dispatch_dict(row: Any) -> Optional[Dict[str, Any]]:
        if not row:
            return None
        item = dict(row)
        for key in ("route_json", "context_json"):
            raw = item.pop(key, None)
            item[key.removesuffix("_json")] = json.loads(raw) if raw else None
        return item

    def create_baton(self, *, baton_id: str, source_baton_id: Optional[str], task_id: str,
                     work_package: str, next_objective: str, git_commit: str, completion_status: str,
                     current_state: Dict[str, Any], results: Dict[str, Any],
                     evidence_references: List[str],
                     validation_id: str, required_capability: str,
                     producer_id: str, working_tree_hash: Optional[str] = None) -> Dict[str, Any]:
        capability = str(required_capability).strip().upper()
        if capability not in CAPABILITIES:
            raise ValueError("Unknown required capability.")
        for name, value in (("baton_id", baton_id), ("task_id", task_id),
                            ("work_package", work_package), ("next_objective", next_objective),
                            ("git_commit", git_commit),
                            ("completion_status", completion_status), ("producer_id", producer_id),
                            ("validation_id", validation_id)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string.")
        if (not isinstance(current_state, dict) or not isinstance(results, dict) or not results
                or not isinstance(evidence_references, list) or not evidence_references):
            raise ValueError("Baton state, results and evidence references are required.")
        if any(not isinstance(ref, str) or not ref.strip() for ref in evidence_references):
            raise ValueError("Baton evidence references must be non-empty strings.")
        tree_hash = working_tree_hash or self._working_tree_hash()
        if not tree_hash:
            raise ValueError("Git working-tree basis could not be determined.")
        now = iso_now()
        with self.store._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM capability_batons WHERE baton_id = ?", (baton_id,)).fetchone():
                conn.rollback()
                raise ValueError("baton_id already exists.")
            conn.execute(
                """INSERT INTO capability_batons
                   (baton_id, source_baton_id, task_id, work_package, next_objective,
                    repository_root, git_commit, working_tree_hash, completion_status,
                    current_state_json, results_json, evidence_json, validation_id,
                    required_capability, created_at, producer_id, verification_status, status, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                           'UNVERIFIED', 'DRAFT', ?)""",
                (baton_id, source_baton_id, task_id, work_package, next_objective,
                 str(self.repository_root), git_commit, tree_hash, completion_status,
                 json.dumps(current_state, sort_keys=True), json.dumps(results, sort_keys=True),
                 json.dumps(evidence_references, sort_keys=True), validation_id, capability,
                 now, producer_id, now),
            )
            self._history(conn, baton_id, "baton_created", None, "DRAFT", producer_id,
                          baton_id, {"required_capability": capability}, now)
            conn.commit()
        return self.get_baton(baton_id) or {}

    def get_baton(self, baton_id: str) -> Optional[Dict[str, Any]]:
        with self.store._connection() as conn:
            row = conn.execute("SELECT * FROM capability_batons WHERE baton_id = ?", (baton_id,)).fetchone()
            if not row:
                return None
            item = self._row_dict(row)
            item["history"] = [dict(history) for history in conn.execute(
                "SELECT * FROM baton_history WHERE baton_id = ? ORDER BY id", (baton_id,)).fetchall()]
            dispatch = conn.execute("SELECT * FROM baton_dispatches WHERE baton_id = ?", (baton_id,)).fetchone()
            item["dispatch"] = self._dispatch_dict(dispatch)
            return item

    def verify_baton(self, baton_id: str, *, verifier_id: str = "system:baton-verifier") -> Dict[str, Any]:
        baton = self.get_baton(baton_id)
        if not baton:
            raise ValueError("Baton does not exist.")
        if baton["status"] in {"REJECTED", "SUPERSEDED"}:
            return baton
        checks: List[Dict[str, Any]] = []
        errors: List[str] = []
        now = iso_now()
        with self.store._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE capability_batons SET status = 'VERIFYING', verification_status = 'VERIFYING', updated_at = ? WHERE baton_id = ?",
                         (now, baton_id))
            conn.commit()
        task = self.store.get_owner_task(baton["task_id"])
        task_ok = bool(task and task["state"] == "COMPLETE")
        checks.append({"check": "task_complete", "passed": task_ok})
        if not task_ok:
            errors.append("Referenced task is not COMPLETE.")
        state_ok = bool(task and baton["current_state"].get("task_state") == task["state"])
        checks.append({"check": "current_state_matches_task", "passed": state_ok})
        if not state_ok:
            errors.append("Baton current state does not match durable task truth.")
        validation = self.store.get_validation_run(baton["validation_id"])
        validation_ok = bool(validation and validation["task_id"] == baton["task_id"]
                             and validation["status"] == "PASSED")
        checks.append({"check": "validation_passed", "passed": validation_ok})
        if not validation_ok:
            errors.append("Referenced validation is not a persisted PASS for the task.")
        completion_claim_ok = baton["completion_status"] == "COMPLETE"
        checks.append({"check": "completion_claim", "passed": completion_claim_ok})
        if not completion_claim_ok:
            errors.append("Baton completion status does not claim COMPLETE.")
        capability_ok = baton["required_capability"] in CAPABILITIES
        checks.append({"check": "capability_valid", "passed": capability_ok})
        if not capability_ok:
            errors.append("Required capability is invalid.")
        root_ok = Path(baton["repository_root"]).resolve() == self.repository_root
        checks.append({"check": "repository_identity", "passed": root_ok})
        if not root_ok:
            errors.append("Baton repository identity does not match the canonical repository.")
        head = self._git("rev-parse", "HEAD")
        commit_exists = self._git_ok("cat-file", "-e", f"{baton['git_commit']}^{{commit}}")
        commit_current = bool(head and head == baton["git_commit"])
        checks.append({"check": "git_basis", "passed": commit_exists and commit_current,
                       "head": head, "expected": baton["git_commit"]})
        if not commit_exists or not commit_current:
            errors.append("Baton Git basis is missing or stale.")
        current_tree_hash = self._working_tree_hash()
        tree_ok = bool(current_tree_hash and current_tree_hash == baton["working_tree_hash"])
        checks.append({"check": "working_tree_basis", "passed": tree_ok,
                       "actual": current_tree_hash, "expected": baton["working_tree_hash"]})
        if not tree_ok:
            errors.append("Baton working-tree basis is missing or stale.")
        for reference in baton["evidence"] or []:
            path = Path(reference)
            if not path.is_absolute():
                path = self.repository_root / path
            try:
                path = path.resolve()
                path.relative_to(self.repository_root)
                exists = path.exists()
            except ValueError:
                exists = False
            checks.append({"check": "evidence_reference", "reference": reference, "passed": exists})
            if not exists:
                errors.append(f"Evidence reference is missing: {reference}")
        if baton["source_baton_id"]:
            source = self.get_baton(baton["source_baton_id"])
            superseded_by_current = bool(source and source["status"] == "SUPERSEDED" and any(
                item["event_type"] == "baton_superseded" and item["source_ref"] == baton_id
                for item in source["history"]
            ))
            lineage_ok = bool(source and (source["status"] == "VERIFIED" or superseded_by_current))
        else:
            lineage_ok = True
        checks.append({"check": "source_lineage", "passed": lineage_ok,
                       "source_baton_id": baton["source_baton_id"]})
        if not lineage_ok:
            errors.append("Source baton lineage is missing or not verified.")
        with self.store._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if not errors:
                if baton["source_baton_id"]:
                    source_row = conn.execute(
                        "SELECT status FROM capability_batons WHERE baton_id = ?",
                        (baton["source_baton_id"],),
                    ).fetchone()
                    superseded_by_current = conn.execute(
                        """SELECT 1 FROM baton_history
                           WHERE baton_id = ? AND event_type = 'baton_superseded' AND source_ref = ?
                           LIMIT 1""",
                        (baton["source_baton_id"], baton_id),
                    ).fetchone()
                    competing = conn.execute(
                        """SELECT baton_id FROM capability_batons
                           WHERE source_baton_id = ? AND baton_id != ? AND status = 'VERIFIED'
                           LIMIT 1""",
                        (baton["source_baton_id"], baton_id),
                    ).fetchone()
                    source_is_eligible = bool(source_row and (
                        source_row["status"] == "VERIFIED"
                        or (source_row["status"] == "SUPERSEDED" and superseded_by_current)
                    ))
                    if not source_is_eligible or competing:
                        errors.append("Source baton is obsolete or already has a verified successor.")
                else:
                    another_head = conn.execute(
                        "SELECT baton_id FROM capability_batons WHERE baton_id != ? AND status = 'VERIFIED' LIMIT 1",
                        (baton_id,),
                    ).fetchone()
                    if another_head:
                        errors.append("A verified baton head already exists; a new root would branch lineage.")
            passed = not errors
            final_status = "VERIFIED" if passed else "REJECTED"
            reason = ("verified against durable task, validation, evidence, lineage and Git basis"
                      if passed else "; ".join(errors))
            if passed and baton["source_baton_id"] and source_row["status"] == "VERIFIED":
                conn.execute(
                    "UPDATE capability_batons SET status = 'SUPERSEDED', updated_at = ? WHERE baton_id = ?",
                    (now, baton["source_baton_id"]),
                )
                self._history(conn, baton["source_baton_id"], "baton_superseded", "VERIFIED",
                              "SUPERSEDED", verifier_id, baton_id,
                              {"successor_baton_id": baton_id}, now)
            conn.execute(
                """UPDATE capability_batons SET status = ?, verification_status = ?,
                   verification_reason = ?, verification_evidence_json = ?, updated_at = ?
                   WHERE baton_id = ?""",
                (final_status, final_status, reason, json.dumps(checks, sort_keys=True), now, baton_id),
            )
            self._history(conn, baton_id, "baton_verified" if passed else "baton_rejected",
                          "VERIFYING", final_status, verifier_id, baton_id,
                          {"checks": checks, "reason": reason}, now)
            conn.commit()
        return self.get_baton(baton_id) or {}

    def dispatch(self, baton_id: str, policy: CapabilityRoutingPolicy,
                 *, requested_target: Optional[str] = None,
                 dispatcher_id: str = "system:capability-router") -> Dict[str, Any]:
        baton = self.verify_baton(baton_id, verifier_id=dispatcher_id)
        if baton["status"] != "VERIFIED":
            raise ValueError("Only a VERIFIED baton can be dispatched.")
        with self.store._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = conn.execute(
                "SELECT status FROM capability_batons WHERE baton_id = ?", (baton_id,)
            ).fetchone()
            if not current or current["status"] != "VERIFIED":
                conn.rollback()
                raise ValueError("Only a current VERIFIED baton can be dispatched.")
            existing = conn.execute("SELECT * FROM baton_dispatches WHERE baton_id = ?", (baton_id,)).fetchone()
            route = policy.resolve(baton["required_capability"], requested_target=requested_target)
            if existing and existing["status"] != "WAITING_FOR_CAPABILITY":
                conn.commit()
                return self._dispatch_dict(existing) or {}
            now = iso_now()
            context = {
                "baton_id": baton_id,
                "source_baton_id": baton["source_baton_id"],
                "task_id": baton["task_id"],
                "work_package": baton["work_package"],
                "repository_root": baton["repository_root"],
                "git_commit": baton["git_commit"],
                "required_capability": baton["required_capability"],
                "validation_id": baton["validation_id"],
                "results": baton["results"],
                "evidence_references": baton["evidence"],
                "constraints": ["verify before dispatch", "no model self-selection", "no automatic retry"],
                "next_objective": baton["next_objective"],
            }
            if route:
                status, reason, target_id, route_json = "READY_FOR_EXTERNAL_DISPATCH", "eligible policy route selected", route["target_id"], json.dumps(route, sort_keys=True)
            else:
                status, reason, target_id, route_json = "WAITING_FOR_CAPABILITY", "no eligible configured target", None, None
            if existing:
                conn.execute(
                    """UPDATE baton_dispatches SET required_capability = ?, status = ?, target_id = ?,
                       route_json = ?, context_json = ?, reason = ?, updated_at = ? WHERE baton_id = ?""",
                    (baton["required_capability"], status, target_id, route_json,
                     json.dumps(context, sort_keys=True), reason, now, baton_id),
                )
                dispatch_id = existing["dispatch_id"]
            else:
                dispatch_id = str(uuid.uuid4())
                conn.execute(
                    """INSERT INTO baton_dispatches
                       (dispatch_id, baton_id, required_capability, status, target_id,
                        route_json, context_json, reason, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (dispatch_id, baton_id, baton["required_capability"], status, target_id,
                     route_json, json.dumps(context, sort_keys=True), reason, now, now),
                )
            self._history(conn, baton_id, "dispatch_recorded", baton["status"], baton["status"],
                          dispatcher_id, dispatch_id, {"status": status, "reason": reason}, now)
            conn.commit()
            return self._dispatch_dict(conn.execute(
                "SELECT * FROM baton_dispatches WHERE baton_id = ?", (baton_id,)
            ).fetchone()) or {}

    def supersede(self, baton_id: str, *, actor_id: str = "system:baton-router") -> Dict[str, Any]:
        now = iso_now()
        with self.store._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT status FROM capability_batons WHERE baton_id = ?", (baton_id,)).fetchone()
            if not row:
                raise ValueError("Baton does not exist.")
            conn.execute("UPDATE capability_batons SET status = 'SUPERSEDED', updated_at = ? WHERE baton_id = ?",
                         (now, baton_id))
            self._history(conn, baton_id, "baton_superseded", row["status"], "SUPERSEDED",
                          actor_id, baton_id, {}, now)
            conn.commit()
        return self.get_baton(baton_id) or {}

    def write_current_projection(self, path: str | Path, baton_id: str) -> Dict[str, Any]:
        baton = self.get_baton(baton_id)
        if not baton or baton["status"] != "VERIFIED":
            raise ValueError("Only a VERIFIED baton can become the current projection.")
        projection = {
            "baton_id": baton["baton_id"], "source_baton_id": baton["source_baton_id"],
            "status": baton["status"], "verification_status": baton["verification_status"],
            "task_id": baton["task_id"], "git_commit": baton["git_commit"],
            "working_tree_hash": baton["working_tree_hash"],
            "work_package": baton["work_package"], "next_objective": baton["next_objective"],
            "required_capability": baton["required_capability"],
            "canonical_state": "sqlite:capability_batons",
        }
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".tmp")
        temporary.write_text(json.dumps(projection, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(destination)
        return projection

    def _git(self, *args: str) -> Optional[str]:
        result = subprocess.run(["git", *args], cwd=str(self.repository_root),
                                capture_output=True, text=True, check=False)
        if result.returncode != 0:
            return None
        return result.stdout.strip()

    def _git_ok(self, *args: str) -> bool:
        result = subprocess.run(["git", *args], cwd=str(self.repository_root),
                                capture_output=True, text=True, check=False)
        return result.returncode == 0

    def _working_tree_hash(self) -> Optional[str]:
        diff = subprocess.run(["git", "diff", "--binary", "HEAD", "--"],
                              cwd=str(self.repository_root), capture_output=True, check=False)
        untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "-z"],
                                   cwd=str(self.repository_root), capture_output=True, check=False)
        if diff.returncode != 0 or untracked.returncode != 0:
            return None
        digest = hashlib.sha256()
        digest.update(b"tracked-diff\0")
        digest.update(diff.stdout)
        digest.update(b"untracked-files\0")
        for raw_name in sorted(filter(None, untracked.stdout.split(b"\0"))):
            try:
                relative = raw_name.decode("utf-8", errors="strict")
                path = self.repository_root / relative
                resolved = path.resolve()
                resolved.relative_to(self.repository_root)
                content = resolved.read_bytes()
            except (OSError, UnicodeError, ValueError):
                return None
            digest.update(raw_name)
            digest.update(b"\0")
            digest.update(hashlib.sha256(content).digest())
        return digest.hexdigest()

    @staticmethod
    def _history(conn: Any, baton_id: str, event_type: str, previous_status: Optional[str],
                 new_status: str, actor_id: str, source_ref: str,
                 evidence: Dict[str, Any], created_at: str) -> None:
        conn.execute(
            """INSERT INTO baton_history
               (baton_id, event_type, previous_status, new_status, actor_id,
                source_ref, evidence_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (baton_id, event_type, previous_status, new_status, actor_id, source_ref,
             json.dumps(evidence, sort_keys=True), created_at),
        )
