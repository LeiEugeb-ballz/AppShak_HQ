from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from appshak_substrate.mailstore_sqlite import SQLiteMailStore
from appshak_substrate.policy import PolicyDecision, ToolPolicy
from appshak_substrate.types import ToolActionType, ToolRequest, ToolResult


class ToolGateway:
    """Single execution gateway for all external/tool actions."""

    def __init__(
        self,
        *,
        mail_store: SQLiteMailStore,
        policy: ToolPolicy,
        workspace_roots: Optional[Mapping[str, str | Path]] = None,
        command_timeout_seconds: float = 120.0,
    ) -> None:
        self.mail_store = mail_store
        self.policy = policy
        self.command_timeout_seconds = max(1.0, float(command_timeout_seconds))
        self.workspace_roots: Dict[str, Path] = {}
        if workspace_roots:
            self.set_workspace_roots(workspace_roots)

    def set_workspace_roots(self, workspace_roots: Mapping[str, str | Path]) -> None:
        self.workspace_roots = {str(agent): Path(path).resolve() for agent, path in workspace_roots.items()}

    def execute(self, request: ToolRequest | Dict[str, Any]) -> ToolResult:
        req = self._coerce_request(request)
        payload = dict(req.payload)
        idempotency_key = payload.get("idempotency_key")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            return self._deny(
                req,
                reason="Missing required payload.idempotency_key.",
                payload=payload,
                idempotency_key=None,
            )
        idempotency_key = idempotency_key.strip()
        allow_duplicate = bool(payload.get("allow_duplicate"))

        workspace_root = self.workspace_roots.get(req.agent_id)
        if workspace_root is None:
            return self._deny(
                req,
                reason=f"No registered workspace root for agent '{req.agent_id}'.",
                payload=payload,
                idempotency_key=idempotency_key,
            )

        decision = self.policy.validate(req, worktree_root=workspace_root)
        if not decision.allowed:
            return self._deny(
                req,
                reason=decision.reason,
                payload=payload,
                idempotency_key=idempotency_key,
            )

        normalized_payload = dict(decision.normalized_payload)
        if req.action_type == ToolActionType.OPEN_PR:
            return self._deny(
                req,
                reason="OPEN_PR is intentionally not implemented in substrate baseline.",
                payload=normalized_payload,
                idempotency_key=idempotency_key,
            )

        if not allow_duplicate:
            existing = self.mail_store.get_idempotency_record(idempotency_key)
            if existing is not None:
                return self._deny(
                    req,
                    reason=f"Duplicate idempotency_key blocked: {idempotency_key}",
                    payload=normalized_payload,
                    idempotency_key=idempotency_key,
                    result={"duplicate_of": existing},
                )
            reserved = self.mail_store.reserve_idempotency_key(
                idempotency_key,
                agent_id=req.agent_id,
                action_type=req.action_type.value,
            )
            if not reserved:
                return self._deny(
                    req,
                    reason=f"Duplicate idempotency_key blocked (race): {idempotency_key}",
                    payload=normalized_payload,
                    idempotency_key=idempotency_key,
                )

        try:
            exec_result = self._execute_allowed(req, normalized_payload)
            result_payload = {
                "stdout": exec_result.stdout,
                "stderr": exec_result.stderr,
                "return_code": exec_result.return_code,
                "error": exec_result.error,
            }
            if not allow_duplicate:
                self.mail_store.set_idempotency_result(idempotency_key, result_payload)
            audit_id = self.mail_store.append_tool_audit(
                agent_id=req.agent_id,
                action_type=req.action_type.value,
                working_dir=req.working_dir,
                idempotency_key=idempotency_key,
                allowed=exec_result.allowed,
                reason=exec_result.reason,
                payload=normalized_payload,
                result=result_payload,
                correlation_id=req.correlation_id,
            )
            exec_result.audit_event_id = audit_id
            return exec_result
        except Exception as exc:
            error_payload = {"error": repr(exc)}
            if not allow_duplicate:
                self.mail_store.set_idempotency_result(idempotency_key, error_payload)
            audit_id = self.mail_store.append_tool_audit(
                agent_id=req.agent_id,
                action_type=req.action_type.value,
                working_dir=req.working_dir,
                idempotency_key=idempotency_key,
                allowed=False,
                reason=f"Execution error: {exc}",
                payload=normalized_payload,
                result=error_payload,
                correlation_id=req.correlation_id,
            )
            return ToolResult(
                allowed=False,
                action_type=req.action_type,
                agent_id=req.agent_id,
                working_dir=req.working_dir,
                error=repr(exc),
                reason=f"Execution error: {exc}",
                audit_event_id=audit_id,
                correlation_id=req.correlation_id,
            )

    def _execute_allowed(self, request: ToolRequest, payload: Dict[str, Any]) -> ToolResult:
        if request.action_type == ToolActionType.RUN_CMD:
            argv = payload.get("argv", [])
            if not isinstance(argv, list) or not argv:
                raise ValueError("RUN_CMD requires normalized argv list.")
            result = subprocess.run(
                argv,
                cwd=request.working_dir,
                text=True,
                capture_output=True,
                check=False,
                timeout=self.command_timeout_seconds,
                shell=False,
            )
            return ToolResult(
                allowed=True,
                action_type=request.action_type,
                agent_id=request.agent_id,
                working_dir=request.working_dir,
                stdout=result.stdout,
                stderr=result.stderr,
                return_code=result.returncode,
                reason="RUN_CMD executed.",
                correlation_id=request.correlation_id,
            )

        if request.action_type == ToolActionType.WRITE_FILE:
            file_path = Path(payload["path"])
            content = payload.get("content", "")
            text = content if isinstance(content, str) else str(content)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(text, encoding="utf-8")
            return ToolResult(
                allowed=True,
                action_type=request.action_type,
                agent_id=request.agent_id,
                working_dir=request.working_dir,
                stdout=f"Wrote {len(text)} bytes to {file_path}",
                return_code=0,
                reason="WRITE_FILE executed.",
                correlation_id=request.correlation_id,
            )

        if request.action_type == ToolActionType.READ_FILE:
            file_path = Path(payload["path"])
            if not file_path.exists():
                return ToolResult(
                    allowed=True,
                    action_type=request.action_type,
                    agent_id=request.agent_id,
                    working_dir=request.working_dir,
                    stderr=f"File does not exist: {file_path}",
                    return_code=1,
                    reason="READ_FILE target missing.",
                    correlation_id=request.correlation_id,
                )
            content = file_path.read_text(encoding="utf-8")
            return ToolResult(
                allowed=True,
                action_type=request.action_type,
                agent_id=request.agent_id,
                working_dir=request.working_dir,
                stdout=content,
                return_code=0,
                reason="READ_FILE executed.",
                correlation_id=request.correlation_id,
            )

        if request.action_type == ToolActionType.GIT_COMMIT:
            message = str(payload["message"])
            paths = payload.get("paths", [])
            add_cmd = ["git", "add", "--"]
            if isinstance(paths, list) and paths:
                add_cmd.extend(str(p) for p in paths)
            add_res = subprocess.run(
                add_cmd,
                cwd=request.working_dir,
                text=True,
                capture_output=True,
                check=False,
                timeout=self.command_timeout_seconds,
                shell=False,
            )
            commit_res = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=request.working_dir,
                text=True,
                capture_output=True,
                check=False,
                timeout=self.command_timeout_seconds,
                shell=False,
            )
            combined_stdout = (add_res.stdout or "") + (commit_res.stdout or "")
            combined_stderr = (add_res.stderr or "") + (commit_res.stderr or "")
            return_code = commit_res.returncode if commit_res.returncode != 0 else add_res.returncode
            return ToolResult(
                allowed=True,
                action_type=request.action_type,
                agent_id=request.agent_id,
                working_dir=request.working_dir,
                stdout=combined_stdout,
                stderr=combined_stderr,
                return_code=return_code,
                reason="GIT_COMMIT executed.",
                correlation_id=request.correlation_id,
            )

        if request.action_type == ToolActionType.GIT_DIFF:
            args = payload.get("args", [])
            if not isinstance(args, list):
                args = []
            cmd = ["git", "diff", *[str(arg) for arg in args]]
            diff_res = subprocess.run(
                cmd,
                cwd=request.working_dir,
                text=True,
                capture_output=True,
                check=False,
                timeout=self.command_timeout_seconds,
                shell=False,
            )
            return ToolResult(
                allowed=True,
                action_type=request.action_type,
                agent_id=request.agent_id,
                working_dir=request.working_dir,
                stdout=diff_res.stdout,
                stderr=diff_res.stderr,
                return_code=diff_res.returncode,
                reason="GIT_DIFF executed.",
                correlation_id=request.correlation_id,
            )

        raise ValueError(f"Unsupported action type: {request.action_type.value}")

    def _deny(
        self,
        request: ToolRequest,
        *,
        reason: str,
        payload: Dict[str, Any],
        idempotency_key: Optional[str],
        result: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        audit_id = self.mail_store.append_tool_audit(
            agent_id=request.agent_id,
            action_type=request.action_type.value,
            working_dir=request.working_dir,
            idempotency_key=idempotency_key,
            allowed=False,
            reason=reason,
            payload=payload,
            result=result,
            correlation_id=request.correlation_id,
        )
        return ToolResult(
            allowed=False,
            action_type=request.action_type,
            agent_id=request.agent_id,
            working_dir=request.working_dir,
            reason=reason,
            error=reason,
            audit_event_id=audit_id,
            correlation_id=request.correlation_id,
        )

    @staticmethod
    def _coerce_request(request: ToolRequest | Dict[str, Any]) -> ToolRequest:
        if isinstance(request, ToolRequest):
            return request
        if isinstance(request, dict):
            action_type = request.get("action_type")
            if isinstance(action_type, ToolActionType):
                normalized_action = action_type
            elif isinstance(action_type, str):
                normalized_action = ToolActionType(action_type.strip().upper())
            else:
                raise ValueError("Tool request requires action_type.")
            payload = request.get("payload", {})
            return ToolRequest(
                agent_id=str(request.get("agent_id", "")),
                action_type=normalized_action,
                working_dir=str(request.get("working_dir", "")),
                payload=dict(payload) if isinstance(payload, dict) else {},
                authorized_by=(
                    str(request.get("authorized_by"))
                    if request.get("authorized_by") is not None
                    else None
                ),
                correlation_id=(
                    str(request.get("correlation_id"))
                    if request.get("correlation_id") is not None
                    else None
                ),
            )
        raise TypeError(f"Unsupported tool request type: {type(request)!r}")
