from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
import uuid
from datetime import datetime
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

    @staticmethod
    def workspace_identity(agent_id: str, workspace_root: str | Path) -> str:
        return f"worktree:{str(agent_id).strip().lower()}:{Path(workspace_root).resolve()}"

    def execute(self, request: ToolRequest | Dict[str, Any], *, owner_id: Optional[str] = None,
                cancel_event: Optional[threading.Event] = None) -> ToolResult:
        req = self._coerce_request(request)
        payload = dict(req.payload)
        authority_payload = {
            "authority_id": req.authority_id,
            "worker_id": req.agent_id,
            "source_request_id": req.source_request_id,
            "workspace_id": req.workspace_id,
            "requested_operation": req.requested_operation,
            "created_at": req.created_at,
        }
        idempotency_key = payload.get("idempotency_key")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            return self._deny(
                req,
                reason="Missing required payload.idempotency_key.",
                payload={**payload, **authority_payload},
                idempotency_key=None,
            )
        idempotency_key = idempotency_key.strip()
        if payload.get("allow_duplicate"):
            return self._deny(req, reason="allow_duplicate cannot bypass durable execution attempts.",
                              payload={**payload, **authority_payload}, idempotency_key=idempotency_key)

        workspace_root = self.workspace_roots.get(req.agent_id)
        if workspace_root is None:
            return self._deny(
                req,
                reason=f"No registered workspace root for agent '{req.agent_id}'.",
                payload={**payload, **authority_payload},
                idempotency_key=idempotency_key,
            )

        authority_error = self._authority_error(req, workspace_root)
        if authority_error is not None:
            return self._deny(
                req,
                reason=authority_error,
                payload={**payload, **authority_payload},
                idempotency_key=idempotency_key,
            )

        decision = self.policy.validate(req, worktree_root=workspace_root)
        if not decision.allowed:
            return self._deny(
                req,
                reason=decision.reason,
                payload={**payload, **authority_payload},
                idempotency_key=idempotency_key,
            )

        normalized_payload = {**decision.normalized_payload, **authority_payload}
        if req.action_type == ToolActionType.OPEN_PR:
            return self._deny(
                req,
                reason="OPEN_PR is intentionally not implemented in substrate baseline.",
                payload=normalized_payload,
                idempotency_key=idempotency_key,
            )

        contract = {
            "working_dir": req.working_dir,
            "payload": normalized_payload,
            "authorized_by": req.authorized_by,
            "correlation_id": req.correlation_id,
            "reply_to": req.reply_to,
        }
        try:
            attempt = self.mail_store.reserve_attempt(
                source_request_id=str(req.source_request_id), source_event_id=req.source_event_id,
                idempotency_key=idempotency_key, authority_id=str(req.authority_id),
                agent_id=req.agent_id, workspace_id=str(req.workspace_id),
                requested_operation=req.action_type.value, created_at=str(req.created_at), request=contract,
            )
        except ValueError as exc:
            return self._deny(req, reason=str(exc), payload=normalized_payload, idempotency_key=idempotency_key)

        attempt_id = str(attempt["attempt_id"])
        if attempt["state"] in {"SUCCEEDED", "FAILED", "TIMED_OUT"} and attempt["outcome"]:
            return self._result_from_outcome(req, attempt)
        if attempt["state"] == "NEEDS_RECONCILIATION":
            return self._attempt_denial(req, attempt_id, "Execution outcome is unknown; manual reconciliation required.")
        execution_owner = owner_id or f"direct:{os.getpid()}:{uuid.uuid4()}"
        generation = self.mail_store.begin_attempt(attempt_id, execution_owner, self.mail_store.lease_seconds)
        if generation is None:
            return self._attempt_denial(req, attempt_id, "Execution attempt is already running or requires reconciliation.")

        state = "FAILED"
        try:
            exec_result = self._execute_allowed(req, normalized_payload, attempt_id, execution_owner,
                                                generation, cancel_event)
            state = "SUCCEEDED" if exec_result.return_code in (None, 0) and not exec_result.error else "FAILED"
            if state == "FAILED":
                exec_result.allowed = False
                exec_result.reason = f"Tool exited with return code {exec_result.return_code}."
        except subprocess.TimeoutExpired as exc:
            state = "TIMED_OUT"
            exec_result = ToolResult(False, req.action_type, req.agent_id, req.working_dir,
                                     error=str(exc), reason="Tool process timed out and was terminated.",
                                     correlation_id=req.correlation_id)
        except Exception as exc:
            state = "NEEDS_RECONCILIATION"
            exec_result = ToolResult(False, req.action_type, req.agent_id, req.working_dir,
                                     error=repr(exc), reason="Tool outcome uncertain after execution error.",
                                     correlation_id=req.correlation_id)
        outcome = {"allowed": exec_result.allowed, "reason": exec_result.reason,
                   "stdout": exec_result.stdout, "stderr": exec_result.stderr,
                   "return_code": exec_result.return_code, "error": exec_result.error,
                   "state": state}
        audit_id = self.mail_store.record_attempt_outcome(attempt_id, execution_owner, generation, state, outcome)
        if audit_id is None:
            return self._attempt_denial(req, attempt_id, "Execution fence was lost; outcome requires reconciliation.")
        exec_result.audit_event_id = audit_id
        exec_result.attempt_id = attempt_id
        return exec_result

    @staticmethod
    def _result_from_outcome(request: ToolRequest, attempt: Dict[str, Any]) -> ToolResult:
        outcome = attempt["outcome"]
        return ToolResult(
            allowed=bool(outcome.get("allowed")), action_type=request.action_type,
            agent_id=request.agent_id, working_dir=request.working_dir,
            stdout=outcome.get("stdout") or "", stderr=outcome.get("stderr") or "",
            return_code=outcome.get("return_code"), error=outcome.get("error"),
            reason=outcome.get("reason"), audit_event_id=attempt["audit_id"],
            correlation_id=request.correlation_id, attempt_id=attempt["attempt_id"],
        )

    def _attempt_denial(self, request: ToolRequest, attempt_id: str, reason: str) -> ToolResult:
        return ToolResult(False, request.action_type, request.agent_id, request.working_dir,
                          error=reason, reason=reason, correlation_id=request.correlation_id,
                          attempt_id=attempt_id)

    def _execute_allowed(self, request: ToolRequest, payload: Dict[str, Any], attempt_id: str,
                         owner_id: str, generation: int,
                         cancel_event: Optional[threading.Event]) -> ToolResult:
        if request.action_type == ToolActionType.RUN_CMD:
            argv = payload.get("argv", [])
            if not isinstance(argv, list) or not argv:
                raise ValueError("RUN_CMD requires normalized argv list.")
            result = self._run_process(argv, request.working_dir, attempt_id, owner_id,
                                       generation, cancel_event)
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
            add_res = self._run_process(add_cmd, request.working_dir, attempt_id, owner_id,
                                        generation, cancel_event)
            if add_res.returncode != 0:
                return ToolResult(True, request.action_type, request.agent_id, request.working_dir,
                                  stdout=add_res.stdout, stderr=add_res.stderr,
                                  return_code=add_res.returncode, reason="GIT_COMMIT add failed.")
            commit_res = self._run_process(["git", "commit", "-m", message], request.working_dir,
                                           attempt_id, owner_id, generation, cancel_event)
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
            diff_res = self._run_process(cmd, request.working_dir, attempt_id, owner_id,
                                         generation, cancel_event)
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

    def _run_process(self, argv: list[str], cwd: str, attempt_id: str, owner_id: str,
                     generation: int, cancel_event: Optional[threading.Event]) -> subprocess.CompletedProcess[str]:
        options: Dict[str, Any] = {"cwd": cwd, "text": True, "stdout": subprocess.PIPE,
                                   "stderr": subprocess.PIPE, "shell": False}
        if os.name == "nt":
            options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            options["start_new_session"] = True
        process = subprocess.Popen(argv, **options)
        job_handle = None
        if os.name == "nt":
            try:
                job_handle = self._attach_windows_job(process)
            except Exception:
                self._terminate_tree(process)
                raise
        deadline = time.monotonic() + self.command_timeout_seconds
        interval = max(0.03, min(1.0, self.mail_store.lease_seconds / 3.0))
        try:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise RuntimeError("Worker event lease was lost during execution.")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(argv, self.command_timeout_seconds)
                try:
                    stdout, stderr = process.communicate(timeout=min(interval, remaining))
                    return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)
                except subprocess.TimeoutExpired:
                    if not self.mail_store.renew_attempt_lease(
                        attempt_id, owner_id, generation, self.mail_store.lease_seconds
                    ):
                        raise RuntimeError("Execution lease/fence was lost during subprocess execution.")
        except BaseException:
            self._terminate_tree(process)
            raise
        finally:
            if job_handle is not None:
                import ctypes
                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.CloseHandle.argtypes = [ctypes.c_void_p]
                kernel.CloseHandle(job_handle)

    @staticmethod
    def _attach_windows_job(process: subprocess.Popen[str]) -> int:
        """Kill the launched Windows process tree when the worker/job handle closes."""
        import ctypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                        ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", ctypes.c_uint32),
                        ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t),
                        ("ActiveProcessLimit", ctypes.c_uint32),
                        ("Affinity", ctypes.c_size_t),
                        ("PriorityClass", ctypes.c_uint32),
                        ("SchedulingClass", ctypes.c_uint32)]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BasicLimits),
                        ("IoInfo", ctypes.c_uint64 * 6),
                        ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        kernel.CreateJobObjectW.restype = ctypes.c_void_p
        kernel.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                                    ctypes.c_void_p, ctypes.c_uint32]
        kernel.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.CreateJobObjectW(None, None)
        if not handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x00002000
        if not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.get_last_error()
            kernel.CloseHandle(handle)
            raise OSError(error, "SetInformationJobObject failed")
        if not kernel.AssignProcessToJobObject(handle, int(process._handle)):
            error = ctypes.get_last_error()
            kernel.CloseHandle(handle)
            raise OSError(error, "AssignProcessToJobObject failed")
        return handle

    @staticmethod
    def _terminate_tree(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        if os.name == "nt":
            killed = subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                    capture_output=True, text=True, timeout=5, check=False)
            if killed.returncode != 0 and process.poll() is None:
                process.kill()
                raise RuntimeError("Windows process tree termination could not be confirmed.")
        else:
            os.killpg(process.pid, signal.SIGKILL)
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)

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

    def _authority_error(self, request: ToolRequest, workspace_root: Path) -> Optional[str]:
        required = {
            "authority_id": request.authority_id,
            "worker_id": request.agent_id,
            "source_request_id": request.source_request_id,
            "workspace_id": request.workspace_id,
            "requested_operation": request.requested_operation,
            "created_at": request.created_at,
        }
        missing = [name for name, value in required.items() if not isinstance(value, str) or not value.strip()]
        if missing:
            return f"Execution authority incomplete; required fields missing: {', '.join(missing)}."

        authority_id = str(request.authority_id).strip().casefold()
        if authority_id in {"approved", "authorized", "validated", "admin", "chief", "command"}:
            return "Execution authority must use an opaque authority_id, not a display label."

        expected_workspace = self.workspace_identity(request.agent_id, workspace_root)
        if request.workspace_id != expected_workspace:
            return "Execution authority workspace_id does not match the registered worker worktree."

        if request.requested_operation != request.action_type.value:
            return "Execution authority requested_operation does not match action_type."

        try:
            datetime.fromisoformat(str(request.created_at).replace("Z", "+00:00"))
        except ValueError:
            return "Execution authority created_at must be an ISO-8601 timestamp."
        return None

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
                authority_id=(
                    str(request.get("authority_id"))
                    if request.get("authority_id") is not None
                    else None
                ),
                source_request_id=(
                    str(request.get("source_request_id"))
                    if request.get("source_request_id") is not None
                    else None
                ),
                workspace_id=(
                    str(request.get("workspace_id"))
                    if request.get("workspace_id") is not None
                    else None
                ),
                requested_operation=(
                    str(request.get("requested_operation"))
                    if request.get("requested_operation") is not None
                    else None
                ),
                created_at=(
                    str(request.get("created_at"))
                    if request.get("created_at") is not None
                    else None
                ),
                source_event_id=(
                    int(request["source_event_id"])
                    if request.get("source_event_id") is not None
                    else None
                ),
                reply_to=(
                    str(request.get("reply_to"))
                    if request.get("reply_to") is not None
                    else None
                ),
            )
        raise TypeError(f"Unsupported tool request type: {type(request)!r}")
