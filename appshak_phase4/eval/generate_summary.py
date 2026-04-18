from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping

from appshak_inspection.store import InspectionIndexStore
from appshak_integrity.store import IntegrityReportStore
from appshak_projection.view_store import ProjectionViewStore

from appshak_phase4.orchestrator import Phase4Orchestrator
from appshak_phase4.writers.inspection_writer import InspectionWriter
from appshak_phase4.writers.integrity_writer import IntegrityWriter


def generate_summary_markdown(
    *,
    projection_view_path: str | Path = "appshak_state/projection/view.json",
    inspection_root: str | Path = "appshak_state/inspection",
    integrity_root: str | Path = "appshak_state/integrity",
    output_path: str | Path = "docs/phase4/PHASE4_EVAL_SUMMARY.md",
    run_tests: bool = True,
) -> str:
    started_at = datetime.now(timezone.utc)
    projection_store = ProjectionViewStore(projection_view_path)
    inspection_store = InspectionIndexStore(inspection_root)
    integrity_store = IntegrityReportStore(integrity_root)

    snapshot = projection_store.load()
    inspection = inspection_store.load_latest()
    integrity = integrity_store.load_latest()

    run_id = _first_non_empty(
        _read_path(inspection, "phase4", "run_id"),
        _read_path(integrity, "phase4", "run_id"),
        "unknown",
    )
    timestamp = _first_non_empty(
        str(inspection.get("generated_at", "")),
        str(integrity.get("generated_at", "")),
        str(snapshot.get("timestamp", "")),
        "unknown",
    )

    projection_ok = _bool_status(bool(snapshot))
    extraction_ok = _bool_status(bool(inspection) and bool(integrity))
    normalization_ok = _bool_status("phase4" in inspection and "phase4" in integrity)
    validation_ok = _bool_status(
        isinstance(_read_path(inspection, "phase4", "anomalies"), list)
        and isinstance(_read_path(integrity, "phase4", "violations"), list)
    )
    inspection_write_ok = _bool_status(bool(inspection) and str(inspection.get("index_hash", "")).strip() != "")
    integrity_write_ok = _bool_status(bool(integrity) and str(integrity.get("report_hash", "")).strip() != "")

    anomalies = _read_path(inspection, "phase4", "anomalies")
    if not isinstance(anomalies, list):
        anomalies = []
    coverage = _read_path(inspection, "phase4", "coverage")
    if not isinstance(coverage, Mapping):
        coverage = {}
    coverage_score = _coverage_score(coverage)
    top_issues = _render_issue_lines(anomalies)

    consistency_score = _safe_float(
        _first_non_empty(
            _read_path(integrity, "phase4", "consistency_score"),
            integrity.get("consistency_score", 0.0),
            0.0,
        )
    )
    violations = _read_path(integrity, "phase4", "violations")
    if not isinstance(violations, list):
        violations = []
    violation_lines = _render_issue_lines(violations)

    runtime_context = _read_path(inspection, "phase4", "runtime")
    replay = _build_replay_hashes(
        snapshot=snapshot,
        runtime_context=runtime_context if isinstance(runtime_context, Mapping) else None,
    )
    original_inspection_hash = str(inspection.get("index_hash", "")).strip()
    original_integrity_hash = str(integrity.get("report_hash", "")).strip()
    original_hash = f"inspection={original_inspection_hash}; integrity={original_integrity_hash}"
    replay_hash = f"inspection={replay['inspection_hash']}; integrity={replay['integrity_hash']}"
    replay_match = (
        bool(original_inspection_hash)
        and bool(original_integrity_hash)
        and replay["inspection_hash"] == original_inspection_hash
        and replay["integrity_hash"] == original_integrity_hash
    )
    audit_binding = _read_path(inspection, "phase4", "runtime", "audit_binding")
    if not isinstance(audit_binding, Mapping):
        audit_binding = {}
    state_graph_snapshot_hash = str(audit_binding.get("state_graph_snapshot_hash", "")).strip()
    run_commit_binding_hash = str(audit_binding.get("run_commit_binding_hash", "")).strip()
    bound_commit_sha = str(audit_binding.get("commit_sha", "")).strip()
    bound_run_id = str(audit_binding.get("run_id", "")).strip()
    audit_hardening_state = (
        "COMPLETE"
        if state_graph_snapshot_hash and run_commit_binding_hash and bound_commit_sha and bound_run_id
        else "INCOMPLETE"
    )

    if run_tests:
        phase4_test = _run_pytest("tests/test_phase4_integrity_and_inspection.py")
        projection_test = _run_pytest("tests/test_projection_layer.py")
    else:
        phase4_test = "SKIP"
        projection_test = "SKIP"

    ended_at = datetime.now(timezone.utc)
    duration_seconds = max(0.0, (ended_at - started_at).total_seconds())

    certification_pass = (
        projection_ok == "OK"
        and extraction_ok == "OK"
        and normalization_ok == "OK"
        and validation_ok == "OK"
        and inspection_write_ok == "OK"
        and integrity_write_ok == "OK"
        and replay_match
        and phase4_test == "PASS"
        and projection_test == "PASS"
    )

    notes = _notes_block(
        replay_match=replay_match,
        anomalies=anomalies,
        violations=violations,
        phase4_test=phase4_test,
        projection_test=projection_test,
        audit_hardening_state=audit_hardening_state,
    )

    markdown = "\n".join(
        [
            "# Phase 4 Evaluation Summary",
            "",
            "## Run Metadata",
            f"- Run ID: {run_id}",
            f"- Timestamp: {timestamp}",
            f"- Duration: {duration_seconds:.3f}s",
            "",
            "## Pipeline Status",
            f"- Projection Input: {projection_ok}",
            f"- Extraction: {extraction_ok}",
            f"- Normalization: {normalization_ok}",
            f"- Validation: {validation_ok}",
            f"- Inspection Write: {inspection_write_ok}",
            f"- Integrity Write: {integrity_write_ok}",
            "",
            "## Inspection Results",
            f"- Total Anomalies: {len(anomalies)}",
            f"- Coverage Score: {coverage_score:.3f}",
            "- Top Issues:",
            *top_issues,
            "",
            "## Integrity Results",
            f"- Consistency Score: {consistency_score:.6f}",
            "- Violations:",
            *violation_lines,
            "",
            "## Determinism Check",
            f"- Replay Match: {'YES' if replay_match else 'NO'}",
            "- Hash Comparison:",
            f"  - Original: {original_hash}",
            f"  - Replay: {replay_hash}",
            "",
            "## Audit Hardening",
            f"- State Graph Snapshot Hash: {state_graph_snapshot_hash or 'missing'}",
            f"- Run/Commit Binding Hash: {run_commit_binding_hash or 'missing'}",
            f"- Bound Commit SHA: {bound_commit_sha or 'missing'}",
            f"- Bound Run ID: {bound_run_id or 'missing'}",
            f"- AUDIT HARDENING STATE: {audit_hardening_state}",
            "",
            "## Test Results",
            f"- test_phase4_integrity_and_inspection: {phase4_test}",
            f"- test_projection_layer: {projection_test}",
            "",
            "## Certification Readiness",
            f"- Status: {'PASS' if certification_pass else 'FAIL'}",
            "",
            "## Notes",
            f"- Observations: {notes['observations']}",
            f"- Weak Points: {notes['weak_points']}",
            f"- Next Actions: {notes['next_actions']}",
            "",
        ]
    )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")
    return markdown


def _build_replay_hashes(
    *,
    snapshot: Mapping[str, Any],
    runtime_context: Mapping[str, Any] | None = None,
) -> Dict[str, str]:
    with tempfile.TemporaryDirectory(prefix="phase4_eval_replay_") as temp_dir:
        root = Path(temp_dir)
        orchestrator = Phase4Orchestrator(
            inspection_writer=InspectionWriter(InspectionIndexStore(root / "inspection")),
            integrity_writer=IntegrityWriter(IntegrityReportStore(root / "integrity")),
        )
        orchestrator.run_phase4_cycle(
            replay_snapshot=dict(snapshot),
            runtime_context=dict(runtime_context) if isinstance(runtime_context, Mapping) else None,
        )
        replay_inspection = InspectionIndexStore(root / "inspection").load_latest()
        replay_integrity = IntegrityReportStore(root / "integrity").load_latest()
        return {
            "inspection_hash": str(replay_inspection.get("index_hash", "")),
            "integrity_hash": str(replay_integrity.get("report_hash", "")),
        }


def _run_pytest(test_path: str) -> str:
    command = [sys.executable, "-m", "pytest", test_path, "-q"]
    result = subprocess.run(command, capture_output=True, text=True)
    return "PASS" if result.returncode == 0 else "FAIL"


def _coverage_score(coverage: Mapping[str, Any]) -> float:
    checks = [
        _safe_int(coverage.get("agent_count")) > 0,
        _safe_int(coverage.get("event_count")) > 0,
        _safe_int(coverage.get("events_processed")) > 0,
    ]
    return float(sum(1 for item in checks if item)) / float(len(checks))


def _render_issue_lines(items: List[Any]) -> List[str]:
    if not items:
        return ["  - none"]
    output: List[str] = []
    for item in items[:5]:
        if isinstance(item, Mapping):
            code = str(item.get("code", "issue")).strip() or "issue"
            message = str(item.get("message", "")).strip() or "no-message"
            output.append(f"  - {code}: {message}")
        else:
            output.append(f"  - {str(item)}")
    return output


def _notes_block(
    *,
    replay_match: bool,
    anomalies: List[Any],
    violations: List[Any],
    phase4_test: str,
    projection_test: str,
    audit_hardening_state: str,
) -> Dict[str, str]:
    observations = (
        "Phase 4 pipeline wrote deterministic replay artifacts with audit binding."
        if replay_match and audit_hardening_state == "COMPLETE"
        else "Replay parity or audit binding is incomplete."
    )
    weak_points = []
    if anomalies:
        weak_points.append(f"{len(anomalies)} anomaly records present")
    if violations:
        weak_points.append(f"{len(violations)} integrity violations present")
    if phase4_test != "PASS":
        weak_points.append("phase4 test module failing")
    if projection_test != "PASS":
        weak_points.append("projection layer test module failing")
    if audit_hardening_state != "COMPLETE":
        weak_points.append("audit hardening fields missing")
    weak_points_text = ", ".join(weak_points) if weak_points else "No critical weak points detected in current run."

    if phase4_test == "PASS" and projection_test == "PASS" and replay_match and audit_hardening_state == "COMPLETE":
        next_actions = "Proceed with immutable baseline signoff (v2 audit hardening aligned)."
    else:
        next_actions = "Resolve failing checks, rerun generator, and re-evaluate certification readiness."
    return {
        "observations": observations,
        "weak_points": weak_points_text,
        "next_actions": next_actions,
    }


def _read_path(payload: Mapping[str, Any], *keys: str) -> Any:
    value: Any = payload
    for key in keys:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if isinstance(value, str):
            if value.strip():
                return value
        elif value is not None:
            return value
    return ""


def _bool_status(value: bool) -> str:
    return "OK" if bool(value) else "FAIL"


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate Phase 4 certification summary markdown.")
    parser.add_argument("--projection-view", type=str, default="appshak_state/projection/view.json")
    parser.add_argument("--inspection-root", type=str, default="appshak_state/inspection")
    parser.add_argument("--integrity-root", type=str, default="appshak_state/integrity")
    parser.add_argument("--output", type=str, default="docs/phase4/PHASE4_EVAL_SUMMARY.md")
    parser.add_argument("--skip-tests", action="store_true")
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    generate_summary_markdown(
        projection_view_path=args.projection_view,
        inspection_root=args.inspection_root,
        integrity_root=args.integrity_root,
        output_path=args.output,
        run_tests=not args.skip_tests,
    )


if __name__ == "__main__":
    main()
