from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from appshak_governance.ledger import GovernanceAuditLedger

from .utils import (
    canonical_hash,
    nested_contains,
    parse_iso_datetime,
    parse_window_spec,
    utc_now_iso,
)


def load_snapshot(path: Path | str) -> Dict[str, Any]:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_integrity_report(path: Path | str | None) -> Dict[str, Any]:
    if path is None:
        return {}
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_governance_entries(path: Path | str) -> List[Dict[str, Any]]:
    source = Path(path)
    ledger = GovernanceAuditLedger(source)
    return ledger.read_entries()


def build_integrity_report(
    *,
    window: str,
    projection_snapshot: Mapping[str, Any],
    governance_entries: Iterable[Mapping[str, Any]],
    replay_result: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> Dict[str, Any]:
    generated = generated_at or utc_now_iso()
    generated_dt = parse_iso_datetime(generated) or datetime.now(timezone.utc)
    entries = [dict(entry) for entry in governance_entries if isinstance(entry, Mapping)]
    entries_in_window = _entries_for_window(entries, window=window, now=generated_dt)

    arbitration_entries = [entry for entry in entries_in_window if _entry_type(entry) == "ARBITRATION_OUTCOME"]
    trust_change_entries = [entry for entry in entries_in_window if _entry_type(entry) == "TRUST_CHANGE"]
    stability_entries = [entry for entry in entries_in_window if _entry_type(entry) == "TRUST_STABILITY_METRIC"]
    lesson_entries = [entry for entry in entries_in_window if _entry_type(entry) == "WATER_COOLER_LESSON"]

    arbitration_metrics = _arbitration_metrics(arbitration_entries)
    trust_metrics = _trust_metrics(trust_change_entries, stability_entries)
    propagation_metrics = _propagation_metrics(entries_in_window, lesson_entries)
    efficiency_metrics = _proxy_efficiency_metrics(
        projection_snapshot=projection_snapshot,
        trust_change_entries=trust_change_entries,
        arbitration_entries=arbitration_entries,
    )
    diagnostics = _diagnostics(
        generated_at=generated,
        projection_snapshot=projection_snapshot,
        entries=entries_in_window,
        replay_result=replay_result or {},
    )

    report = {
        "window": str(window),
        "generated_at": generated,
        "arbitration": arbitration_metrics,
        "trust": trust_metrics,
        "propagation": propagation_metrics,
        "efficiency": efficiency_metrics,
        "diagnostics": diagnostics,
    }
    report["report_hash"] = canonical_hash(report)
    return report


def _entry_type(entry: Mapping[str, Any]) -> str:
    return str(entry.get("entry_type", "")).strip().upper()


def _entries_for_window(entries: List[Dict[str, Any]], *, window: str, now: datetime) -> List[Dict[str, Any]]:
    duration = parse_window_spec(window, now=now)
    cutoff = now - duration
    filtered: List[Dict[str, Any]] = []
    for entry in entries:
        timestamp = parse_iso_datetime(entry.get("timestamp"))
        if timestamp is None:
            filtered.append(entry)
            continue
        if timestamp >= cutoff:
            filtered.append(entry)
    filtered.sort(key=lambda row: int(row.get("seq", 0)))
    return filtered


def _arbitration_metrics(arbitration_entries: List[Mapping[str, Any]]) -> Dict[str, Any]:
    approvals = 0
    aggregate_scores: List[float] = []
    revision_distribution: Dict[str, int] = {}
    score_deltas: List[float] = []
    resolution_steps: List[int] = []

    for entry in arbitration_entries:
        payload = entry.get("payload")
        if not isinstance(payload, Mapping):
            continue
        approved = bool(payload.get("approved", False))
        if approved:
            approvals += 1
        try:
            aggregate_scores.append(float(payload.get("aggregate_score", 0.0)))
        except Exception:
            aggregate_scores.append(0.0)

        revisions = _safe_int(payload.get("revisions_before_execute"), default=0)
        revision_distribution[str(revisions)] = revision_distribution.get(str(revisions), 0) + 1
        current_score = _safe_float(payload.get("aggregate_score"), default=0.0)
        previous_score = _safe_float(payload.get("previous_aggregate_score"), default=current_score)
        score_deltas.append(current_score - previous_score)
        resolution_steps.append(max(1, revisions + 1))

    total = len(arbitration_entries)
    approval_rate = float(approvals) / float(total) if total else 0.0
    avg_aggregate = sum(aggregate_scores) / float(len(aggregate_scores)) if aggregate_scores else 0.0
    mean_score_delta = sum(score_deltas) / float(len(score_deltas)) if score_deltas else 0.0
    mean_resolution_steps = sum(resolution_steps) / float(len(resolution_steps)) if resolution_steps else 0.0

    return {
        "count": total,
        "approval_rate": approval_rate,
        "arbitration_efficiency_score": (approval_rate + avg_aggregate) / 2.0 if total else 0.0,
        "revisions_before_execute_distribution": revision_distribution,
        "mean_decision_score_delta_per_revision": mean_score_delta,
        "resolution_time": {
            "unit": "event_steps",
            "mean": mean_resolution_steps,
        },
        "convergence_speed": {
            "unit": "event_steps",
            "mean_revisions": mean_resolution_steps,
        },
    }


def _trust_metrics(
    trust_change_entries: List[Mapping[str, Any]],
    stability_entries: List[Mapping[str, Any]],
) -> Dict[str, Any]:
    reputation_deltas: List[float] = []
    for entry in trust_change_entries:
        payload = entry.get("payload")
        if not isinstance(payload, Mapping):
            continue
        reputation_deltas.append(_safe_float(payload.get("reputation_delta"), default=0.0))

    stability_values: List[float] = []
    for entry in stability_entries:
        payload = entry.get("payload")
        if not isinstance(payload, Mapping):
            continue
        stability_values.append(_safe_float(payload.get("global_variance"), default=0.0))

    rolling_slope = _rolling_slope(stability_values, window=5)
    rolling_variance = _rolling_variance(stability_values, window=5)
    volatility = sum(abs(value) for value in reputation_deltas) / float(len(reputation_deltas)) if reputation_deltas else 0.0
    drift_indicator = sum(reputation_deltas)

    return {
        "change_count": len(reputation_deltas),
        "trust_volatility_score": volatility,
        "governance_drift_indicator": drift_indicator,
        "trend": {
            "rolling_slope": rolling_slope,
            "rolling_variance": rolling_variance,
            "anomaly_flags": {
                "slope_band_exceeded": abs(rolling_slope) > 0.05,
                "variance_band_exceeded": rolling_variance > 0.02,
            },
        },
    }


def _propagation_metrics(
    entries: List[Mapping[str, Any]],
    lesson_entries: List[Mapping[str, Any]],
) -> Dict[str, Any]:
    lessons: List[Dict[str, Any]] = []
    for entry in lesson_entries:
        payload = entry.get("payload")
        if not isinstance(payload, Mapping):
            continue
        lesson = payload.get("lesson")
        if isinstance(lesson, Mapping) and lesson.get("lesson_id"):
            lessons.append(
                {
                    "lesson_id": str(lesson.get("lesson_id")),
                    "source_seq": _safe_int(entry.get("seq"), default=0),
                    "source_agent": str(lesson.get("source_agent", "")),
                    "recipients": [str(item) for item in lesson.get("recipients", []) if isinstance(item, str)],
                }
            )

    if not lessons:
        signature_rule = "signature = (source_event_type, source_event_id, source_agent)"
        return {
            "mode": "signature_fallback",
            "signature_rule": signature_rule,
            "lessons_total": 0,
            "time_to_reuse": {"unit": "event_steps", "mean": 0.0},
            "cross_agent_reuse_count": 0,
            "propagation_depth": 0,
        }

    entry_rows = [dict(item) for item in entries]
    time_to_reuse_steps: List[int] = []
    cross_agent_reuse = 0
    depth_values: List[int] = []

    for lesson in lessons:
        lesson_id = lesson["lesson_id"]
        source_seq = lesson["source_seq"]
        source_agent = lesson["source_agent"]
        consumers = set()
        first_reuse_step: int | None = None
        for row in entry_rows:
            seq = _safe_int(row.get("seq"), default=0)
            if seq <= source_seq:
                continue
            payload = row.get("payload")
            if not isinstance(payload, Mapping):
                continue
            if not nested_contains(payload, lesson_id):
                continue
            step_delta = seq - source_seq
            if first_reuse_step is None or step_delta < first_reuse_step:
                first_reuse_step = step_delta

            consumer = _extract_consumer(payload)
            if consumer:
                consumers.add(consumer)

        if first_reuse_step is not None:
            time_to_reuse_steps.append(first_reuse_step)
        if source_agent:
            cross_agent_reuse += len([agent for agent in consumers if agent != source_agent])
        depth_values.append(len(consumers))

    mean_reuse_steps = sum(time_to_reuse_steps) / float(len(time_to_reuse_steps)) if time_to_reuse_steps else 0.0
    mean_depth = sum(depth_values) / float(len(depth_values)) if depth_values else 0.0

    return {
        "mode": "explicit_lessons",
        "signature_rule": "lesson_id exact match",
        "lessons_total": len(lessons),
        "time_to_reuse": {"unit": "event_steps", "mean": mean_reuse_steps},
        "cross_agent_reuse_count": cross_agent_reuse,
        "propagation_depth": mean_depth,
        "knowledge_propagation_velocity": 0.0 if mean_reuse_steps <= 0 else 1.0 / mean_reuse_steps,
    }


def _extract_consumer(payload: Mapping[str, Any]) -> str:
    for key in ("agent_id", "subject_id", "target_agent"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return ""


def _proxy_efficiency_metrics(
    *,
    projection_snapshot: Mapping[str, Any],
    trust_change_entries: List[Mapping[str, Any]],
    arbitration_entries: List[Mapping[str, Any]],
) -> Dict[str, Any]:
    tool_counts = projection_snapshot.get("tool_audit_counts", {})
    if isinstance(tool_counts, Mapping):
        tool_invocations = _safe_int(tool_counts.get("allowed"), default=0) + _safe_int(tool_counts.get("denied"), default=0)
    else:
        tool_invocations = 0

    successes = 0
    failures = 0
    for entry in trust_change_entries:
        payload = entry.get("payload")
        if not isinstance(payload, Mapping):
            continue
        outcome = str(payload.get("outcome", "")).strip().upper()
        if outcome == "SUCCESS":
            successes += 1
        elif outcome == "FAILURE":
            failures += 1

    governance_cycles = len(trust_change_entries) + len(arbitration_entries)
    execution_events = _safe_int(projection_snapshot.get("events_processed"), default=0)

    return {
        "label": "proxy",
        "tool_invocations_per_success": _ratio(tool_invocations, successes),
        "retries_per_success": _ratio(failures, successes),
        "governance_cycles_per_execution_event": _ratio(governance_cycles, execution_events),
    }


def _diagnostics(
    *,
    generated_at: str,
    projection_snapshot: Mapping[str, Any],
    entries: List[Mapping[str, Any]],
    replay_result: Mapping[str, Any],
) -> Dict[str, Any]:
    snapshot_time = projection_snapshot.get("timestamp")
    last_snapshot_time = snapshot_time if isinstance(snapshot_time, str) else None

    ledger_time = None
    if entries:
        timestamp = entries[-1].get("timestamp")
        if isinstance(timestamp, str):
            ledger_time = timestamp

    replay_hash_equal = bool(replay_result.get("hashes_equal", False))
    warnings: List[str] = []
    if not replay_hash_equal and replay_result:
        warnings.append("replay_hash_mismatch")
    if not entries:
        warnings.append("governance_ledger_empty")

    return {
        "generated_at": generated_at,
        "integrity_summary": "measurement_only",
        "last_snapshot_time": last_snapshot_time,
        "last_governance_ledger_time": ledger_time,
        "determinism_checks": {
            "replay_hash_equal": replay_hash_equal,
            "chain_valid": bool(replay_result.get("chain_valid", False)),
        },
        "stability_warnings": warnings,
    }


def _rolling_slope(values: List[float], *, window: int) -> float:
    if len(values) < 2:
        return 0.0
    subset = values[-max(2, window) :]
    n = len(subset)
    x_values = list(range(n))
    mean_x = sum(x_values) / float(n)
    mean_y = sum(subset) / float(n)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_values, subset))
    denominator = sum((x - mean_x) ** 2 for x in x_values)
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _rolling_variance(values: List[float], *, window: int) -> float:
    subset = values[-max(2, window) :]
    if len(subset) < 2:
        return 0.0
    mean = sum(subset) / float(len(subset))
    return sum((value - mean) ** 2 for value in subset) / float(len(subset))


def _safe_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)
