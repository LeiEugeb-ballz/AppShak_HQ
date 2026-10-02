"""Deterministic artifact validation bound to durable WP2 tool attempts."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from appshak_substrate.mailstore_sqlite import SQLiteMailStore
from appshak_substrate.tool_gateway import ToolGateway
from appshak_substrate.types import ToolActionType, iso_now


class ArtifactValidator:
    """Independently read one produced file and persist a criteria verdict."""

    def __init__(self, *, mail_store: SQLiteMailStore, tool_gateway: ToolGateway,
                 validator_id: str = "system:deterministic-file-validator") -> None:
        self.mail_store = mail_store
        self.tool_gateway = tool_gateway
        self.validator_id = validator_id

    def validate(self, *, task_id: str, artifact_id: str,
                 source_request_id: str) -> Dict[str, Any]:
        run = self.mail_store.create_validation_run(
            task_id=task_id, artifact_id=artifact_id, validator_id=self.validator_id,
            source_request_id=source_request_id,
        )
        if run["status"] != "PENDING":
            return run
        task = self.mail_store.get_owner_task(task_id)
        artifact = self.mail_store.get_artifact(artifact_id)
        if task is None or artifact is None:
            return self.mail_store.record_validation_error(
                run["validation_id"], actor_id=self.validator_id,
                evidence={"reason": "task_or_artifact_missing"},
            )
        result = self.tool_gateway.execute({
            "task_id": task_id,
            "validation_id": run["validation_id"],
            "agent_id": task["assigned_agent"],
            "authorized_by": task["owner_id"],
            "action_type": ToolActionType.READ_FILE.value,
            "working_dir": str(Path(artifact["reference"]).parent),
            "authority_id": task["assignment_authority_id"],
            "source_request_id": f"{source_request_id}:read",
            "workspace_id": task["workspace_id"],
            "requested_operation": ToolActionType.READ_FILE.value,
            "created_at": iso_now(),
            "payload": {
                "path": artifact["reference"],
                "idempotency_key": f"validation:{run['validation_id']}:read",
            },
        })
        if not result.allowed:
            current = self.mail_store.get_validation_run(run["validation_id"])
            if current and current["status"] in {"ERROR", "NEEDS_RECONCILIATION"}:
                return current
            return self.mail_store.record_validation_error(
                run["validation_id"], actor_id=self.validator_id,
                evidence={"reason": "validator_tool_denied", "tool_reason": result.reason,
                          "attempt_id": result.attempt_id},
                unknown=result.attempt_id is not None,
            )
        return self.mail_store.complete_validation(
            run["validation_id"], observed_text=result.stdout, actor_id=self.validator_id,
        )
