from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from appshak_substrate.types import ToolActionType, ToolRequest


@dataclass(slots=True)
class PolicyDecision:
    allowed: bool
    reason: str
    normalized_payload: Dict[str, Any] = field(default_factory=dict)


class ToolPolicy:
    """Mechanical policy checks for tool execution requests."""

    _SHELL_METACHAR_PATTERN = re.compile(r"[;&|><`$]")

    DEFAULT_ALLOWED_COMMAND_PREFIXES: Tuple[Tuple[str, ...], ...] = (
        ("git", "status"),
        ("git", "diff"),
        ("git", "add"),
        ("git", "commit"),
        ("git", "apply"),
        ("git", "format-patch"),
        ("git", "rev-parse"),
        ("pytest",),
        ("python", "-m", "pytest"),
        ("python", "-m", "unittest"),
    )

    _MUTATING_ACTIONS = {
        ToolActionType.RUN_CMD,
        ToolActionType.WRITE_FILE,
        ToolActionType.GIT_COMMIT,
        ToolActionType.OPEN_PR,
    }

    def __init__(
        self,
        *,
        chief_agent_id: str = "command",
        allowed_command_prefixes: Optional[Iterable[Sequence[str]]] = None,
    ) -> None:
        self.chief_agent_id = chief_agent_id
        prefixes = allowed_command_prefixes or self.DEFAULT_ALLOWED_COMMAND_PREFIXES
        self.allowed_command_prefixes: Tuple[Tuple[str, ...], ...] = tuple(
            tuple(str(item) for item in prefix) for prefix in prefixes
        )

    def validate(self, request: ToolRequest, *, worktree_root: Path) -> PolicyDecision:
        root = worktree_root.resolve()
        working_dir = Path(request.working_dir).resolve()
        if not self._is_subpath(working_dir, root):
            return PolicyDecision(False, "working_dir must be inside agent worktree.")
        if not working_dir.exists() or not working_dir.is_dir():
            return PolicyDecision(False, "working_dir must exist and be a directory.")

        if request.action_type in self._MUTATING_ACTIONS:
            if request.agent_id != self.chief_agent_id and request.authorized_by != self.chief_agent_id:
                return PolicyDecision(
                    False,
                    "Mutating external actions require Chief authorization.",
                )

        payload = dict(request.payload)
        if request.action_type == ToolActionType.RUN_CMD:
            cmd_decision = self._validate_command_payload(payload)
            if not cmd_decision.allowed:
                return cmd_decision
            payload.update(cmd_decision.normalized_payload)
            return PolicyDecision(True, "RUN_CMD policy checks passed.", payload)

        if request.action_type in {ToolActionType.WRITE_FILE, ToolActionType.READ_FILE}:
            path_value = payload.get("path")
            if not isinstance(path_value, str) or not path_value.strip():
                return PolicyDecision(False, "File actions require a non-empty payload.path.")
            resolved = self.resolve_path(root, path_value)
            if resolved is None:
                return PolicyDecision(False, "File path escapes worktree root.")
            payload["path"] = str(resolved)
            return PolicyDecision(True, "File path policy checks passed.", payload)

        if request.action_type == ToolActionType.GIT_COMMIT:
            message = payload.get("message")
            if not isinstance(message, str) or not message.strip():
                return PolicyDecision(False, "GIT_COMMIT requires a non-empty commit message.")
            paths = payload.get("paths", [])
            if not isinstance(paths, list):
                return PolicyDecision(False, "GIT_COMMIT payload.paths must be a list.")
            normalized_paths: List[str] = []
            for item in paths:
                if not isinstance(item, str) or not item.strip():
                    return PolicyDecision(False, "GIT_COMMIT paths entries must be non-empty strings.")
                resolved = self.resolve_path(root, item)
                if resolved is None:
                    return PolicyDecision(False, f"GIT_COMMIT path escapes worktree root: {item}")
                normalized_paths.append(str(resolved))
            payload["paths"] = normalized_paths
            return PolicyDecision(True, "GIT_COMMIT policy checks passed.", payload)

        if request.action_type == ToolActionType.GIT_DIFF:
            return PolicyDecision(True, "GIT_DIFF policy checks passed.", payload)

        if request.action_type == ToolActionType.OPEN_PR:
            return PolicyDecision(True, "OPEN_PR policy checks passed.", payload)

        return PolicyDecision(False, f"Unsupported action type: {request.action_type.value}")

    def _validate_command_payload(self, payload: Dict[str, Any]) -> PolicyDecision:
        argv = payload.get("argv")
        if argv is None:
            command = payload.get("command")
            if not isinstance(command, str) or not command.strip():
                return PolicyDecision(False, "RUN_CMD requires payload.argv or payload.command.")
            try:
                argv = shlex.split(command, posix=False)
            except ValueError:
                return PolicyDecision(False, "RUN_CMD payload.command could not be parsed safely.")
        if not isinstance(argv, list) or not argv:
            return PolicyDecision(False, "RUN_CMD payload.argv must be a non-empty list.")

        normalized: List[str] = []
        for arg in argv:
            if not isinstance(arg, str) or not arg.strip():
                return PolicyDecision(False, "RUN_CMD argv entries must be non-empty strings.")
            if self._SHELL_METACHAR_PATTERN.search(arg):
                return PolicyDecision(False, f"RUN_CMD denied due to shell metacharacters in argument: {arg}")
            normalized.append(arg)

        if not self._command_is_whitelisted(normalized):
            return PolicyDecision(False, f"RUN_CMD denied: command not in whitelist ({normalized[0]}).")

        return PolicyDecision(True, "RUN_CMD command policy checks passed.", {"argv": normalized})

    def _command_is_whitelisted(self, argv: Sequence[str]) -> bool:
        for prefix in self.allowed_command_prefixes:
            if len(argv) < len(prefix):
                continue
            if tuple(argv[: len(prefix)]) == prefix:
                return True
        return False

    @staticmethod
    def resolve_path(root: Path, requested: str) -> Optional[Path]:
        candidate = (root / requested).resolve()
        return candidate if ToolPolicy._is_subpath(candidate, root) else None

    @staticmethod
    def _is_subpath(candidate: Path, root: Path) -> bool:
        try:
            candidate.relative_to(root)
            return True
        except ValueError:
            return False
