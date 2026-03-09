from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

OUTCOME_SET = {"DENIED", "BLOCKED", "APPROVED", "EXECUTED", "FAILED"}
ACTIVITY_SET = {"START", "ACTIVE", "FINISH", "IDLE", "RECOVERY"}
ORIGIN_ROLE_ALLOWLIST = {"KERNEL", "SCOUT", "BUILDER", "CHIEF", "SAFEGUARD", "BOSS"}
SEVERITY_SET = {"INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL", "UNKNOWN"}

WARNING_ORDER = {
    "UNKNOWN_ORIGIN_ROLE": 1,
    "UNKNOWN_SEVERITY": 2,
    "INVALID_ACTIVITY": 3,
    "INVALID_OUTCOME": 4,
}


@dataclass(frozen=True)
class NormResult:
    value: Optional[str]
    warning: Optional[str]
    raw: Optional[str]


def _norm_upper(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    return text.upper()


def norm_origin_role(v: Any) -> NormResult:
    raw = v if isinstance(v, str) else None
    normalized = _norm_upper(v)
    if normalized is None:
        return NormResult(value=None, warning="UNKNOWN_ORIGIN_ROLE", raw=raw)
    if normalized not in ORIGIN_ROLE_ALLOWLIST:
        return NormResult(value="UNKNOWN", warning="UNKNOWN_ORIGIN_ROLE", raw=raw)
    return NormResult(value=normalized, warning=None, raw=raw)


def norm_severity(v: Any) -> NormResult:
    raw = v if isinstance(v, str) else None
    normalized = _norm_upper(v)
    if normalized is None:
        return NormResult(value="UNKNOWN", warning="UNKNOWN_SEVERITY", raw=raw)
    if normalized not in SEVERITY_SET:
        return NormResult(value="UNKNOWN", warning="UNKNOWN_SEVERITY", raw=raw)
    return NormResult(value=normalized, warning=None, raw=raw)


def norm_outcome(v: Any) -> NormResult:
    raw = v if isinstance(v, str) else None
    normalized = _norm_upper(v)
    if normalized is None:
        return NormResult(value=None, warning=None, raw=raw)
    if normalized not in OUTCOME_SET:
        return NormResult(value=None, warning="INVALID_OUTCOME", raw=raw)
    return NormResult(value=normalized, warning=None, raw=raw)


def norm_activity(v: Any) -> NormResult:
    raw = v if isinstance(v, str) else None
    normalized = _norm_upper(v)
    if normalized is None:
        return NormResult(value=None, warning=None, raw=raw)
    if normalized not in ACTIVITY_SET:
        return NormResult(value=None, warning="INVALID_ACTIVITY", raw=raw)
    return NormResult(value=normalized, warning=None, raw=raw)


def sort_warnings(warnings: list[dict]) -> list[dict]:
    def key(warning: dict) -> tuple:
        code = warning.get("code") or ""
        return (WARNING_ORDER.get(code, 999), code, warning.get("message") or "")

    return sorted(warnings, key=key)
