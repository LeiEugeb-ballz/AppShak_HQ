from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from .models import validate_viz_event
from .src.io_ndjson import read_ndjson, write_json
from .src.reducer import ProjectionState, initial_state, reduce_event
from .src.replay import _hash_json_obj
from .src.replay_summary import build_replay_summary, to_dict as summary_to_dict


def export_viz_feed(*, run_id: str, output_dir: Path | str, feed_root: Path | str = "appshak_viz_feed") -> Dict[str, Any]:
    root = Path(feed_root)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    events = load_viz_events(root=root, run_id=run_id)
    projection_snapshot = build_projection_snapshot(events, mode="REPLAY")
    replay_summary = build_expected_snapshot(events)
    replay_report = build_replay_report(events)
    coverage = collect_dataset_coverage(events)
    dataset_requirements = evaluate_dataset_requirements(coverage)

    _write_ndjson(out_dir / "events_redacted.ndjson", events)
    _write_ndjson(out_dir / "sample_excerpt.ndjson", select_excerpt(events))
    write_json(str(out_dir / "projection_snapshot.json"), projection_snapshot)
    write_json(str(out_dir / "expected_snapshot.json"), replay_summary)
    write_json(str(out_dir / "replay_report.json"), replay_report)

    manifest = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_events_path": str((root / "runs" / run_id / "events.ndjson").resolve()),
        "event_count": len(events),
        "coverage": coverage,
        "dataset_requirements": dataset_requirements,
        "files": {
            "events_redacted": "events_redacted.ndjson",
            "sample_excerpt": "sample_excerpt.ndjson",
            "expected_snapshot": "expected_snapshot.json",
            "projection_snapshot": "projection_snapshot.json",
            "replay_report": "replay_report.json",
        },
    }
    write_json(str(out_dir / "manifest.json"), manifest)
    return manifest


def load_viz_events(*, root: Path, run_id: str) -> List[Dict[str, Any]]:
    path = root / "runs" / run_id / "events.ndjson"
    if not path.exists():
        raise FileNotFoundError(f"Viz feed not found for run_id={run_id}: {path}")

    events: List[Dict[str, Any]] = []
    for event in read_ndjson(str(path)):
        errors = validate_viz_event(event)
        if errors:
            raise ValueError(f"Malformed viz event in {path}: {errors}")
        events.append(dict(event))
    events.sort(key=lambda item: (str(item.get("run_id", "")), int(item.get("seq", 0))))
    return events


def build_projection_snapshot(events: Iterable[Mapping[str, Any]], *, mode: str = "REPLAY") -> Dict[str, Any]:
    st = initial_state(mode=mode)
    for event in events:
        st = reduce_event(st, dict(event))
    return _projection_snapshot_from_state(st)


def build_expected_snapshot(events: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    return summary_to_dict(build_replay_summary([dict(event) for event in events]))


def build_replay_report(events: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    ordered = [dict(event) for event in events]
    projection_snapshot = build_projection_snapshot(ordered, mode="REPLAY")
    replay_summary = build_expected_snapshot(ordered)
    projection_snapshot_b = build_projection_snapshot(ordered, mode="REPLAY")
    return {
        "deterministic": _hash_json_obj(projection_snapshot) == _hash_json_obj(projection_snapshot_b),
        "snapshot_hash_a": _hash_json_obj(projection_snapshot),
        "snapshot_hash_b": _hash_json_obj(projection_snapshot_b),
        "blocked_event_count": len(replay_summary.get("blocked_event_ids") or []),
    }


def collect_dataset_coverage(events: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    ordered = [dict(event) for event in events]
    replay_summary = build_expected_snapshot(ordered)
    job_spans = replay_summary.get("job_spans") or {}
    complete_jobs = [
        job_id
        for job_id, span in job_spans.items()
        if int(span.get("event_count", 0)) >= 2
        and any(phase in {"APPROVAL", "BLOCKED", "ERROR"} for phase in span.get("phases") or [])
    ]
    blocked_case_count = len(replay_summary.get("blocked_event_ids") or [])
    errors = [
        event
        for event in ordered
        if str(((event.get("payload") or {}).get("phase") or "")).upper() == "ERROR"
    ]
    recoveries = [
        event
        for event in ordered
        if str(((event.get("payload") or {}).get("phase") or "")).upper() == "RECOVERY"
    ]
    origins_with_recovery = {
        str(recovery.get("origin_id") or "")
        for recovery in recoveries
        if any(str(error.get("origin_id") or "") == str(recovery.get("origin_id") or "") for error in errors)
    }
    return {
        "complete_jobs": sorted(complete_jobs),
        "complete_job_count": len(complete_jobs),
        "overlap_count": len(replay_summary.get("overlap_pairs") or []),
        "blocked_case_count": blocked_case_count,
        "agent_error_recovery_count": len(origins_with_recovery),
        "kernel_restart_or_recovery_present": any(
            str(event.get("type") or "") == "KERNEL_RECOVERY"
            or str(((event.get("payload") or {}).get("phase") or "")).upper() == "RECOVERY"
            for event in ordered
        ),
    }


def evaluate_dataset_requirements(coverage: Mapping[str, Any]) -> Dict[str, Any]:
    complete_job_count = int(coverage.get("complete_job_count", 0))
    overlap_count = int(coverage.get("overlap_count", 0))
    blocked_case_count = int(coverage.get("blocked_case_count", 0))
    agent_error_recovery_count = int(coverage.get("agent_error_recovery_count", 0))
    restart_present = bool(coverage.get("kernel_restart_or_recovery_present", False))
    requirements = {
        "complete_jobs_3_to_5": 3 <= complete_job_count <= 5,
        "overlapping_jobs_at_least_2": overlap_count >= 2,
        "blocked_case_present": blocked_case_count >= 1,
        "agent_error_and_recovery_present": agent_error_recovery_count >= 1,
        "restart_or_run_boundary_present": restart_present,
    }
    requirements["all_satisfied"] = all(requirements.values())
    return requirements


def dataset_gate_satisfied(manifest_or_path: Mapping[str, Any] | Path | str) -> bool:
    if isinstance(manifest_or_path, Mapping):
        manifest = dict(manifest_or_path)
    else:
        manifest = json.loads(Path(manifest_or_path).read_text(encoding="utf-8"))
    dataset_requirements = manifest.get("dataset_requirements")
    if not isinstance(dataset_requirements, Mapping):
        return False
    return bool(dataset_requirements.get("all_satisfied") is True)


def select_excerpt(events: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    if len(events) <= 50:
        return [dict(event) for event in events]

    picked: List[Dict[str, Any]] = []
    seen: set[str] = set()
    coverage_candidates = [
        event
        for event in events
        if str(((event.get("payload") or {}).get("phase") or "")).upper() in {"BLOCKED", "ERROR", "RECOVERY"}
    ]
    for event in coverage_candidates:
        key = str(event.get("event_id") or "")
        if key and key not in seen:
            picked.append(dict(event))
            seen.add(key)
        if len(picked) >= 20:
            break

    step = max(1, len(events) // max(20, min(50, len(events))))
    for index in range(0, len(events), step):
        event = events[index]
        key = str(event.get("event_id") or "")
        if key in seen:
            continue
        picked.append(dict(event))
        seen.add(key)
        if len(picked) >= 50:
            break

    picked.sort(key=lambda item: (str(item.get("run_id", "")), int(item.get("seq", 0))))
    return picked[:50]


def _projection_snapshot_from_state(st: ProjectionState) -> Dict[str, Any]:
    return {
        "schema_version": st.schema_version,
        "run_id": st.run_id,
        "last_seq_processed": st.last_seq_processed,
        "viewer": st.viewer,
        "agents": st.agents,
        "jobs": st.jobs,
        "room_occupancy": st.room_occupancy,
        "alerts": st.alerts,
        "blocked_events": st.blocked_events,
        "warnings": st.warnings,
    }


def _write_ndjson(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            handle.write("\n")
