"""Read-only office state from the canonical substrate database."""

from __future__ import annotations

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
            "SELECT task_id, objective, state, assigned_agent, workspace_id, "
            "assignment_authority_id FROM owner_tasks ORDER BY created_at DESC, task_id DESC LIMIT ?",
            (max(1, min(int(limit), 1000)),),
        ):
            task = dict(row)
            task_id = task["task_id"]
            task["attempts"] = [dict(item) for item in conn.execute(
                "SELECT attempt_id, state, authority_id, agent_id, workspace_id, requested_operation "
                "FROM execution_attempts WHERE task_id = ? ORDER BY rowid", (task_id,),
            )]
            task["artifacts"] = [dict(item) for item in conn.execute(
                "SELECT artifact_id, reference, size_bytes, sha256, attempt_id "
                "FROM owner_task_artifacts WHERE task_id = ? ORDER BY rowid", (task_id,),
            )]
            task["validations"] = [dict(item) for item in conn.execute(
                "SELECT validation_id, status, artifact_id, validated_sha256 FROM validation_runs "
                "WHERE task_id = ? ORDER BY created_at, validation_id", (task_id,),
            )]
            tasks.append(task)
        batons = []
        for row in conn.execute(
            "SELECT b.baton_id, b.source_baton_id, b.task_id, b.status, b.verification_status, "
            "b.required_capability, b.git_commit, d.dispatch_id, d.status AS dispatch_status, "
            "d.target_id FROM capability_batons b LEFT JOIN baton_dispatches d "
            "ON d.baton_id = b.baton_id ORDER BY b.created_at DESC, b.baton_id DESC LIMIT ?",
            (max(1, min(int(limit), 1000)),),
        ):
            batons.append(dict(row))
        return {"source": "canonical_sqlite", "tasks": tasks, "batons": batons}
