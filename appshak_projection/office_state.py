"""Read-only office state from the canonical substrate database."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


class OfficeStateUnavailable(RuntimeError):
    """Canonical state cannot be read without inventing an empty office."""


def read_office_state(db_path: str | Path, *, limit: int = 100) -> dict[str, Any]:
    try:
        return _read_office_state(db_path, limit=limit)
    except (FileNotFoundError, sqlite3.DatabaseError) as exc:
        raise OfficeStateUnavailable(str(exc)) from exc


def _read_office_state(db_path: str | Path, *, limit: int) -> dict[str, Any]:
    """Read one SQLite snapshot without creating or changing runtime state."""
    path = Path(db_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Canonical mailstore is missing: {path}")
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN")
        tasks = []
        for row in conn.execute(
            "SELECT task_id, source_request_id, owner_id, objective, authority_id, state, "
            "assigned_agent, workspace_id, assignment_authority_id, assignment_source, "
            "assigned_at, created_at, updated_at FROM owner_tasks "
            "ORDER BY created_at DESC, task_id DESC LIMIT ?",
            (max(1, min(int(limit), 1000)),),
        ):
            task = dict(row)
            task_id = task["task_id"]
            task["attempts"] = [dict(item) for item in conn.execute(
                "SELECT attempt_id, state, authority_id, agent_id, workspace_id, requested_operation, "
                "validation_id, created_at, started_at, updated_at, outcome_json "
                "FROM execution_attempts WHERE task_id = ? ORDER BY rowid", (task_id,),
            )]
            for attempt in task["attempts"]:
                attempt["outcome"] = _json_value(attempt.pop("outcome_json"))
            task["artifacts"] = [dict(item) for item in conn.execute(
                "SELECT artifact_id, reference, size_bytes, sha256, attempt_id, kind, workspace_id, "
                "producer_id, created_at "
                "FROM owner_task_artifacts WHERE task_id = ? ORDER BY rowid", (task_id,),
            )]
            task["criteria"] = []
            for item in conn.execute(
                "SELECT criterion_id, criterion_type, config_json, required, source_ref, created_by, created_at "
                "FROM task_acceptance_criteria WHERE task_id = ? ORDER BY created_at, criterion_id", (task_id,),
            ):
                criterion = dict(item)
                criterion["config"] = _json_value(criterion.pop("config_json"))
                criterion["required"] = bool(criterion["required"])
                task["criteria"].append(criterion)
            task["validations"] = []
            for item in conn.execute(
                "SELECT validation_id, source_request_id, status, artifact_id, validator_id, started_at, "
                "completed_at, related_attempt_id, validated_sha256, validated_size_bytes, evidence_json, "
                "created_at, updated_at FROM validation_runs "
                "WHERE task_id = ? ORDER BY created_at, validation_id", (task_id,),
            ):
                validation = dict(item)
                validation["evidence"] = _json_value(validation.pop("evidence_json"))
                validation["checks"] = []
                for check_row in conn.execute(
                    "SELECT c.criterion_id, c.status, c.evidence_json, a.criterion_type, a.config_json, "
                    "a.required FROM validation_checks c "
                    "LEFT JOIN task_acceptance_criteria a ON a.criterion_id = c.criterion_id "
                    "WHERE c.validation_id = ? ORDER BY c.criterion_id",
                    (validation["validation_id"],),
                ):
                    check = dict(check_row)
                    check["evidence"] = _json_value(check.pop("evidence_json"))
                    check["expected"] = _json_value(check.pop("config_json"))
                    check["required"] = bool(check["required"])
                    validation["checks"].append(check)
                task["validations"].append(validation)
            tasks.append(task)
        batons = []
        for row in conn.execute(
            "SELECT b.baton_id, b.source_baton_id, b.task_id, b.work_package, b.next_objective, "
            "b.status, b.verification_status, b.verification_reason, b.required_capability, "
            "b.git_commit, b.completion_status, b.validation_id, b.producer_id, b.policy_version, "
            "b.created_at, b.updated_at, d.dispatch_id, d.status AS dispatch_status, d.target_id, "
            "d.reason AS dispatch_reason, d.handoff_task_id, d.attempt_id AS handoff_attempt_id, "
            "d.payload_reference, d.result_reference, d.pickup_owner_id, "
            "d.pickup_generation, d.dispatched_at, d.acknowledged_at, "
            "d.result_at, d.result_sha256, d.result_size_bytes, "
            "d.created_at AS dispatch_created_at, "
            "d.updated_at AS dispatch_updated_at FROM capability_batons b LEFT JOIN baton_dispatches d "
            "ON d.baton_id = b.baton_id ORDER BY b.created_at DESC, b.baton_id DESC LIMIT ?",
            (max(1, min(int(limit), 1000)),),
        ):
            batons.append(dict(row))
        return {"source": "canonical_sqlite", "tasks": tasks, "batons": batons}


def _json_value(raw: Any) -> Any:
    if raw is None:
        return None
    try:
        return json.loads(str(raw))
    except (TypeError, ValueError):
        return None
