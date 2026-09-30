from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from appshak_substrate.mailstore_sqlite import SQLiteMailStore
from appshak_substrate.tool_gateway import ToolGateway
from appshak_substrate.types import SubstrateEvent, ToolActionType


class AgentRuntime:
    """Per-agent event handler for worker processes."""

    def __init__(
        self,
        *,
        agent_id: str,
        mail_store: SQLiteMailStore,
        tool_gateway: Optional[ToolGateway] = None,
        runtime_log_path: Optional[str | Path] = None,
        consumer_id: Optional[str] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> None:
        self.agent_id = agent_id
        self.mail_store = mail_store
        self.tool_gateway = tool_gateway
        self.runtime_log_path = Path(runtime_log_path) if runtime_log_path else None
        self.consumer_id = consumer_id
        self.cancel_event = cancel_event

    def handle_event(self, event: SubstrateEvent) -> Dict[str, Any]:
        if event.target_agent and event.target_agent != self.agent_id:
            return {"status": "skipped", "reason": "target_agent mismatch", "event_id": event.event_id}

        if event.type == "SUPERVISOR_HEARTBEAT":
            return {"status": "heartbeat_seen", "event_id": event.event_id}

        if event.type == "TOOL_REQUEST":
            result = self._handle_tool_request(event)
            self._log_runtime(
                {
                    "agent_id": self.agent_id,
                    "event_id": event.event_id,
                    "event_type": event.type,
                    "result": result,
                }
            )
            return result

        if self.agent_id == "forge" and event.type == "FORGE_PROPOSE_CHANGE":
            result = self._handle_forge_change(event)
            self._log_runtime(
                {
                    "agent_id": self.agent_id,
                    "event_id": event.event_id,
                    "event_type": event.type,
                    "result": result,
                }
            )
            return result

        result = {
            "status": "processed",
            "event_id": event.event_id,
            "event_type": event.type,
            "agent_id": self.agent_id,
        }
        self._log_runtime(result)
        return result

    def _handle_tool_request(self, event: SubstrateEvent) -> Dict[str, Any]:
        if self.tool_gateway is None:
            return {"status": "tool_gateway_missing", "event_id": event.event_id}

        payload = dict(event.payload)
        request_raw = payload.get("request")
        if not isinstance(request_raw, dict):
            return {"status": "invalid_request_payload", "event_id": event.event_id}

        request_data = dict(request_raw)
        request_data.setdefault("agent_id", self.agent_id)
        request_data.setdefault("working_dir", payload.get("working_dir") or request_data.get("working_dir"))
        request_data.setdefault("authorized_by", payload.get("authorized_by"))
        request_data.setdefault("correlation_id", event.correlation_id)
        request_data.setdefault("authority_id", payload.get("authority_id"))
        request_data.setdefault(
            "source_request_id",
            payload.get("source_request_id") or (f"event:{event.event_id}" if event.event_id is not None else None),
        )
        request_data.setdefault("workspace_id", payload.get("workspace_id"))
        request_data.setdefault("task_id", payload.get("task_id"))
        request_data.setdefault("requested_operation", payload.get("requested_operation") or request_data.get("action_type"))
        request_data.setdefault("created_at", payload.get("created_at") or event.timestamp)
        request_data["source_event_id"] = event.event_id
        request_data["reply_to"] = payload.get("reply_to") or request_data.get("reply_to") or "command"
        result = self.tool_gateway.execute(request_data, owner_id=self.consumer_id,
                                           cancel_event=self.cancel_event)
        if result.attempt_id is None:
            self.mail_store.append_event(SubstrateEvent(
                type="TOOL_RESULT", origin_id=self.agent_id,
                target_agent=payload.get("reply_to") or "command",
                correlation_id=event.correlation_id,
                payload={"source_event_id": event.event_id, "allowed": result.allowed,
                         "reason": result.reason, "return_code": result.return_code,
                         "audit_event_id": result.audit_event_id},
            ))
        return {
            "status": "tool_request_handled",
            "event_id": event.event_id,
            "allowed": result.allowed,
            "reason": result.reason,
            "audit_event_id": result.audit_event_id,
            "attempt_id": result.attempt_id,
        }

    def _handle_forge_change(self, event: SubstrateEvent) -> Dict[str, Any]:
        if self.tool_gateway is None:
            return {"status": "tool_gateway_missing", "event_id": event.event_id}
        payload = dict(event.payload)
        target_path = payload.get("path", "FORGE_OUTPUT.txt")
        content = payload.get("content", "")
        workdir = payload.get("working_dir")
        if not isinstance(workdir, str) or not workdir.strip():
            return {"status": "missing_working_dir", "event_id": event.event_id}
        idempotency_key = payload.get("idempotency_key")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            idempotency_key = f"forge-propose-{event.event_id}"
        result = self.tool_gateway.execute(
            {
                "agent_id": "forge",
                "authorized_by": payload.get("authorized_by"),
                "authority_id": payload.get("authority_id"),
                "source_request_id": payload.get("source_request_id") or (f"event:{event.event_id}" if event.event_id is not None else None),
                "workspace_id": payload.get("workspace_id"),
                "task_id": payload.get("task_id"),
                "requested_operation": ToolActionType.WRITE_FILE.value,
                "created_at": payload.get("created_at") or event.timestamp,
                "source_event_id": event.event_id,
                "reply_to": payload.get("reply_to") or "command",
                "action_type": ToolActionType.WRITE_FILE.value,
                "working_dir": workdir,
                "correlation_id": event.correlation_id,
                "payload": {
                    "path": target_path,
                    "content": content,
                    "idempotency_key": idempotency_key,
                },
            }, owner_id=self.consumer_id, cancel_event=self.cancel_event
        )
        return {
            "status": "forge_change_applied" if result.allowed else "forge_change_denied",
            "event_id": event.event_id,
            "allowed": result.allowed,
            "reason": result.reason,
            "audit_event_id": result.audit_event_id,
            "attempt_id": result.attempt_id,
        }

    def _log_runtime(self, record: Dict[str, Any]) -> None:
        if self.runtime_log_path is None:
            return
        self.runtime_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.runtime_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")
