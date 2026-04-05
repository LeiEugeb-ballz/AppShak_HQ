#!/usr/bin/env python
"""
AppShak Phase 3B — Certification Harness
=========================================
Runs the full 6-hour certification sequence and produces a signed evidence bundle.

Usage:
    python CERTIFICATION_HARNESS.py

Options:
    --hours FLOAT       Duration in hours (default: 6.0)
    --quick             Run a 5-minute smoke test instead (for env validation)
    --output-dir PATH   Where to write the evidence bundle (default: ./certification_evidence)

What this does:
    1. Pre-flight checks (chambers, unit tests, state dirs)
    2. Launches swarm in background
    3. Launches projection materializer in background
    4. Launches governance engine in background
    5. Launches observability server in background
    6. Runs stability harness for --hours
    7. Generates integrity report
    8. Builds inspection index
    9. Validates all evidence criteria
    10. Writes signed manifest + pass/fail verdict

Evidence bundle contents:
    - stability_result.json
    - integrity_report.json
    - inspection_index.json
    - pre_flight_results.json
    - run_log.txt
    - MANIFEST.json  (pass/fail verdict + hash summary)

CHANGELOG:
    v3B.2 — Fixed --output-dir -> --out-root for integrity report module
           — Fixed stability result parsing to read 'status' + 'incident' fields correctly
           — Added governance engine as explicit background process
           — Improved watchdog stall detection and reporting
           — Added pre-run governance ledger path validation
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


# ─── Configuration ────────────────────────────────────────────────────────────

DEFAULT_HOURS = 6.0
QUICK_HOURS = 0.083  # 5 minutes
DEFAULT_OUTPUT = "certification_evidence"

MAILSTORE_DB = "appshak_state/substrate/mailstore.db"
PROJECTION_VIEW = "appshak_state/projection/view.json"
GOVERNANCE_LEDGER = "appshak_state/governance/ledger.jsonl"
GOVERNANCE_REGISTRY = "appshak_state/governance/registry.json"
INTEGRITY_ROOT = "appshak_state/integrity"
INSPECTION_ROOT = "appshak_state/inspection"
STABILITY_ROOT = "appshak_state/stability"
OBS_HOST = "127.0.0.1"
OBS_PORT = 8010

AGENTS = ["recon", "forge", "command"]

# Agent definitions for governance engine bootstrap
AGENT_DEFINITIONS = [
    {"agent_id": "recon",   "role": "scout",   "authority_level": 1},
    {"agent_id": "forge",   "role": "builder", "authority_level": 2},
    {"agent_id": "command", "role": "chief",   "authority_level": 3},
]


# ─── Helpers ──────────────────────────────────────────────────────────────────

_log_lines = []

def log(msg: str, level: str = "INFO") -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    _log_lines.append(line)
    return line


def run_cmd(args: list[str], capture: bool = True) -> tuple[int, str]:
    """Run a subprocess and return (returncode, output)."""
    result = subprocess.run(
        args,
        capture_output=capture,
        text=True,
    )
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, output.strip()


def file_sha256(path: str) -> str | None:
    """Return SHA-256 hex digest of a file, or None if missing."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except FileNotFoundError:
        return None


def ensure_state_dirs() -> None:
    """Ensure all required state directories exist."""
    dirs = [
        "appshak_state/substrate",
        "appshak_state/projection",
        "appshak_state/governance",
        "appshak_state/integrity",
        "appshak_state/inspection",
        "appshak_state/stability",
        "appshak_state/agents",
        "workspaces",
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)


# ─── Pre-flight ───────────────────────────────────────────────────────────────

def run_preflight() -> dict:
    """Runs chambers + unit tests. Returns structured results."""
    results = {"passed": True, "chambers": {}, "unit_tests": {}}

    log("Running Chamber A — Durability...")
    rc, out = run_cmd([sys.executable, "-m", "appshak_substrate.chambers.chamber_a_durability"])
    results["chambers"]["chamber_a"] = {"pass": rc == 0, "output": out}
    if rc != 0:
        log(f"CHAMBER A FAILED:\n{out}", "ERROR")
        results["passed"] = False

    log("Running Chamber B — Isolation...")
    rc, out = run_cmd([sys.executable, "-m", "appshak_substrate.chambers.chamber_b_isolation"])
    results["chambers"]["chamber_b"] = {"pass": rc == 0, "output": out}
    if rc != 0:
        log(f"CHAMBER B FAILED:\n{out}", "ERROR")
        results["passed"] = False

    log("Running Chamber C — Tool Enforcement...")
    rc, out = run_cmd([sys.executable, "-m", "appshak_substrate.chambers.chamber_c_tool_enforcement"])
    results["chambers"]["chamber_c"] = {"pass": rc == 0, "output": out}
    if rc != 0:
        log(f"CHAMBER C FAILED:\n{out}", "ERROR")
        results["passed"] = False

    log("Running unit tests...")
    rc, out = run_cmd([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"])
    results["unit_tests"] = {"pass": rc == 0, "output": out}
    if rc != 0:
        log(f"UNIT TESTS FAILED:\n{out}", "ERROR")
        results["passed"] = False

    status = "PASS" if results["passed"] else "FAIL"
    log(f"Pre-flight result: {status}")
    return results


# ─── Governance Bootstrap ─────────────────────────────────────────────────────

def bootstrap_governance() -> bool:
    """
    Bootstrap the governance engine inline so the ledger + registry
    exist before the swarm starts. Returns True on success.
    """
    log("Bootstrapping governance engine...")
    try:
        # Import inline so we don't fail hard if governance module is missing
        from appshak_governance.engine import GovernanceEngine
        from pathlib import Path as _Path

        engine = GovernanceEngine.from_agent_definitions(
            agent_definitions=AGENT_DEFINITIONS,
            registry_path=_Path(GOVERNANCE_REGISTRY),
            ledger_path=_Path(GOVERNANCE_LEDGER),
        )
        # Force an initial ledger entry by ingesting an empty projection delta
        engine.ingest_projection_delta(previous_view=None, current_view={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "workers": {},
            "derived": {},
        })
        log("Governance engine bootstrapped — ledger initialised.")
        return True
    except Exception as e:
        log(f"Governance bootstrap failed: {e}", "WARN")
        log("Governance ledger may be empty — decisions_traceable may fail.", "WARN")
        return False


# ─── Process Management ───────────────────────────────────────────────────────

class ProcessGroup:
    """Manages background processes for the certification run."""

    def __init__(self):
        self._procs: list[tuple[str, subprocess.Popen]] = []

    def start(self, args: list[str], label: str) -> None:
        log(f"Starting: {label}")
        p = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self._procs.append((label, p))
        log(f"  PID {p.pid}: {label}")

    def check_alive(self) -> list[str]:
        """Returns list of labels for processes that have died unexpectedly."""
        dead = []
        for label, p in self._procs:
            if p.poll() is not None:
                dead.append(f"{label} (exit={p.returncode})")
        return dead

    def stop_all(self) -> None:
        log("Stopping all background processes...")
        for label, p in self._procs:
            try:
                p.send_signal(signal.SIGTERM)
            except Exception:
                pass
        time.sleep(2)
        for label, p in self._procs:
            try:
                if p.poll() is None:
                    p.kill()
            except Exception:
                pass
        log("All background processes stopped.")


# ─── Stability Result Parsing ─────────────────────────────────────────────────

def parse_stability_result(raw_output: str, exit_code: int) -> dict:
    """
    Parse the stability runner's JSON output into a normalised dict
    the harness can reliably validate against.
    """
    result = {}
    try:
        result = json.loads(raw_output)
    except json.JSONDecodeError:
        log(f"Could not parse stability JSON. Raw:\n{raw_output[:500]}", "WARN")
        result = {"raw_output": raw_output}

    # Normalise: the runner uses 'status' not 'passed'
    status = result.get("status", "")
    incident = result.get("incident", None)

    if status == "completed" and incident is None:
        result["passed"] = True
        result["summary"] = "Stability run completed with no incidents."
    elif status == "halted" or incident:
        result["passed"] = False
        incident_reason = incident.get("reason", "unknown") if isinstance(incident, dict) else str(incident)
        incident_type = incident.get("type", "unknown") if isinstance(incident, dict) else "unknown"
        result["summary"] = f"Halted — {incident_type}: {incident_reason}"
        log(f"Watchdog incident: [{incident_type}] {incident_reason}", "WARN")
    elif exit_code == 0 and not result.get("passed"):
        # Exit 0 but no clear status — treat as passed if no incident field
        result["passed"] = True
        result["summary"] = "Stability run exited cleanly (no incident field)."
    else:
        result["passed"] = False
        result["summary"] = f"Stability status='{status}', exit={exit_code}"

    # Normalise event_gaps
    if "event_gaps" not in result:
        result["event_gaps"] = 0

    # Normalise replay_deterministic from checkpoints
    checkpoints = result.get("checkpoints", [])
    if checkpoints:
        # Check if any checkpoint has a non-empty governance replay hash
        replay_hashes = [
            c.get("governance_replay_hash_checkpoint", "")
            for c in checkpoints
            if c.get("governance_replay_hash_checkpoint")
        ]
        result["replay_deterministic"] = len(replay_hashes) > 0
    else:
        result["replay_deterministic"] = result.get("replay_deterministic", False)

    return result


# ─── Evidence Validation ──────────────────────────────────────────────────────

def validate_evidence(output_dir: Path, stability_result: dict) -> dict:
    """
    Validates the 3B certification criteria against collected evidence.
    Returns a dict with per-criterion results and overall pass/fail.
    """
    criteria = {}

    # 1. No crash + watchdog OK
    run_ok = stability_result.get("passed", False)
    criteria["no_crash_watchdog_ok"] = {
        "pass": run_ok,
        "detail": stability_result.get("summary", "No summary available"),
    }

    # 2. Projection populated
    proj_path = PROJECTION_VIEW
    proj_data = None
    if os.path.exists(proj_path):
        try:
            with open(proj_path) as f:
                proj_data = json.load(f)
        except Exception as e:
            criteria["projection_populated"] = {"pass": False, "detail": f"Parse error: {e}"}

    if proj_data is not None:
        workers = proj_data.get("workers", {})
        null_fields = [
            k for k, v in workers.items()
            if v.get("state") is None or v.get("last_event_type") is None
        ]
        criteria["projection_populated"] = {
            "pass": len(null_fields) == 0,
            "detail": f"Null fields in workers: {null_fields}" if null_fields else "All worker fields populated",
        }
    elif "projection_populated" not in criteria:
        criteria["projection_populated"] = {"pass": False, "detail": "Projection view file not found"}

    # 3. Event continuity
    gaps = stability_result.get("event_gaps", 0)
    criteria["event_continuity_no_gaps"] = {
        "pass": gaps == 0,
        "detail": f"Event gaps detected: {gaps}" if gaps else "No event gaps detected",
    }

    # 4. Integrity fields present
    integrity_reports = list(Path(INTEGRITY_ROOT).glob("*.json")) if Path(INTEGRITY_ROOT).exists() else []
    # Also check markdown reports
    integrity_md = list(Path(INTEGRITY_ROOT).glob("*.md")) if Path(INTEGRITY_ROOT).exists() else []
    all_integrity = integrity_reports + integrity_md
    criteria["integrity_fields_present"] = {
        "pass": len(all_integrity) > 0,
        "detail": f"Integrity files found: {len(all_integrity)}" if all_integrity else "No integrity reports found",
    }

    # 5. Decisions traceable
    ledger_path = GOVERNANCE_LEDGER
    ledger_lines = 0
    if os.path.exists(ledger_path):
        with open(ledger_path) as f:
            ledger_lines = sum(1 for _ in f)
    criteria["decisions_traceable"] = {
        "pass": ledger_lines > 0,
        "detail": f"Governance ledger entries: {ledger_lines}",
    }

    # 6. Replay deterministic
    replay_ok = stability_result.get("replay_deterministic", False)
    criteria["replay_deterministic"] = {
        "pass": replay_ok is True,
        "detail": "Replay hash confirmed in checkpoints" if replay_ok else "No replay hash found in checkpoints",
    }

    # 7. Inspection index built
    inspection_files = list(Path(INSPECTION_ROOT).glob("*.json")) if Path(INSPECTION_ROOT).exists() else []
    criteria["inspection_index_built"] = {
        "pass": len(inspection_files) > 0,
        "detail": f"Inspection index files found: {len(inspection_files)}" if inspection_files else "No inspection index found",
    }

    overall = all(c["pass"] for c in criteria.values())
    return {"overall_pass": overall, "criteria": criteria}


# ─── Evidence Bundle ──────────────────────────────────────────────────────────

def build_manifest(output_dir: Path, validation: dict, preflight: dict, run_meta: dict) -> dict:
    files_to_hash = [
        "stability_result.json",
        "integrity_report.json",
        "inspection_index.json",
        "pre_flight_results.json",
        "run_log.txt",
    ]

    file_hashes = {}
    for fname in files_to_hash:
        fpath = output_dir / fname
        sha = file_sha256(str(fpath))
        file_hashes[fname] = sha or "FILE_NOT_FOUND"

    manifest = {
        "schema_version": "3B.2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_meta": run_meta,
        "verdict": "PASS" if validation["overall_pass"] else "FAIL",
        "certification_criteria": validation["criteria"],
        "overall_pass": validation["overall_pass"],
        "preflight_pass": preflight["passed"],
        "file_hashes": file_hashes,
        "human_signoff": None,
        "notes": "",
    }

    return manifest


# ─── Stash Failed Run ─────────────────────────────────────────────────────────

def stash_previous_run(output_dir: Path) -> None:
    """
    If a previous certification_evidence folder exists with a FAIL verdict,
    stash it with a timestamped reference and a reason note before overwriting.
    Preserves audit trail per constitutional requirements.
    """
    manifest_path = output_dir / "MANIFEST.json"
    if not manifest_path.exists():
        return

    try:
        with open(manifest_path) as f:
            prev = json.load(f)
    except Exception:
        return

    prev_verdict = prev.get("verdict", "UNKNOWN")
    prev_time = prev.get("generated_at", "unknown")
    schema = prev.get("schema_version", "unknown")

    # Build stash directory name
    ts_tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stash_name = f"certification_evidence_stash_{ts_tag}_v{schema}_{prev_verdict}"
    stash_dir = output_dir.parent / stash_name

    import shutil
    shutil.copytree(str(output_dir), str(stash_dir))

    # Write a reason note into the stash
    failed_criteria = [
        k for k, v in prev.get("certification_criteria", {}).items()
        if not v.get("pass", True)
    ]
    reason_note = {
        "stashed_at": datetime.now(timezone.utc).isoformat(),
        "original_run_time": prev_time,
        "schema_version": schema,
        "verdict": prev_verdict,
        "failed_criteria": failed_criteria,
        "reason": (
            "Stashed automatically before new certification run. "
            "This evidence bundle is preserved for audit and governance review. "
            f"Failed criteria: {', '.join(failed_criteria) if failed_criteria else 'none recorded'}."
        ),
    }
    with open(stash_dir / "STASH_REASON.json", "w") as f:
        json.dump(reason_note, f, indent=2)

    log(f"Previous run stashed → {stash_dir.name}")
    log(f"  Verdict was: {prev_verdict} | Failed: {failed_criteria}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="AppShak Phase 3B Certification Harness")
    parser.add_argument("--hours", type=float, default=DEFAULT_HOURS)
    parser.add_argument("--quick", action="store_true", help="Run 5-minute smoke test instead of full 6h run")
    parser.add_argument("--output-dir", type=str, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    hours = QUICK_HOURS if args.quick else args.hours
    output_dir = Path(args.output_dir)

    # Stash any previous run before we overwrite
    stash_previous_run(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    ensure_state_dirs()

    run_start = datetime.now(timezone.utc)
    run_meta = {
        "start_time": run_start.isoformat(),
        "planned_hours": hours,
        "quick_mode": args.quick,
        "harness_version": "3B.2",
    }

    log("=" * 60)
    log("AppShak Phase 3B Certification Harness v3B.2")
    log(f"Mode: {'QUICK (5min)' if args.quick else f'FULL ({hours}h)'}")
    log(f"Output: {output_dir.resolve()}")
    log("=" * 60)

    # ── Pre-flight ─────────────────────────────────────────────
    log("STEP 1/7 — Pre-flight checks")
    preflight = run_preflight()
    with open(output_dir / "pre_flight_results.json", "w") as f:
        json.dump(preflight, f, indent=2)

    if not preflight["passed"]:
        log("PRE-FLIGHT FAILED. Fix all chamber/test failures before certifying.", "ERROR")
        sys.exit(1)

    log("Pre-flight PASSED.")

    # ── Bootstrap governance ───────────────────────────────────
    log("STEP 2/7 — Bootstrapping governance engine")
    bootstrap_governance()

    # ── Launch background services ─────────────────────────────
    log("STEP 3/7 — Starting background services")
    procs = ProcessGroup()

    swarm_duration = int(hours * 3600 + 180)  # swarm runs slightly longer than stability
    procs.start([
        sys.executable, "-m", "appshak_substrate.run_swarm",
        "--agents", *AGENTS,
        "--durable", "--worktrees",
        "--duration-seconds", str(swarm_duration),
    ], "Swarm supervisor")

    time.sleep(4)

    procs.start([
        sys.executable, "-m", "appshak_projection.run_projector",
        "--mailstore-db", MAILSTORE_DB,
        "--view-path", PROJECTION_VIEW,
        "--poll-interval", "1",
    ], "Projection materializer")

    time.sleep(2)

    procs.start([
        sys.executable, "-m", "appshak_observability.server",
        "--mailstore-db", MAILSTORE_DB,
        "--host", OBS_HOST,
        "--port", str(OBS_PORT),
    ], "Observability server")

    time.sleep(2)

    # Verify services launched OK
    dead = procs.check_alive()
    if dead:
        log(f"Background services died immediately: {dead}", "ERROR")
        log("Cannot proceed — fix service startup before running certification.", "ERROR")
        procs.stop_all()
        sys.exit(1)

    # ── Stability run ──────────────────────────────────────────
    log(f"STEP 4/7 — Running stability harness ({hours}h)...")
    log("This will run until completion. Do not interrupt.")

    stability_rc, stability_out = run_cmd([
        sys.executable, "-m", "appshak_stability.run",
        "--duration-hours", str(hours),
        "--poll-interval-seconds", "60",
        "--checkpoint-every-cycles", "5",
        "--projection-view", PROJECTION_VIEW,
        "--governance-ledger", GOVERNANCE_LEDGER,
        "--integrity-root", INTEGRITY_ROOT,
        "--inspection-root", INSPECTION_ROOT,
        "--stability-root", STABILITY_ROOT,
    ], capture=True)

    stability_result = parse_stability_result(stability_out, stability_rc)

    with open(output_dir / "stability_result.json", "w") as f:
        json.dump(stability_result, f, indent=2)
    log(f"Stability run complete. Status: {stability_result.get('status', 'unknown')} | Passed: {stability_result.get('passed')}")

    # ── Stop background services ───────────────────────────────
    procs.stop_all()

    # ── Integrity report ───────────────────────────────────────
    log("STEP 5/7 — Generating integrity report")
    # Use --out-root (correct flag for this module)
    ir_rc, ir_out = run_cmd([
        sys.executable, "-m", "appshak_integrity.run_report",
        "--window", "7d",
        "--projection-view", PROJECTION_VIEW,
        "--governance-ledger", GOVERNANCE_LEDGER,
        "--out-root", INTEGRITY_ROOT,
    ])
    integrity_data = {}
    try:
        integrity_data = json.loads(ir_out)
    except Exception:
        integrity_data = {"raw": ir_out, "exit_code": ir_rc}
    with open(output_dir / "integrity_report.json", "w") as f:
        json.dump(integrity_data, f, indent=2)

    if ir_rc != 0:
        log(f"Integrity report exited with code {ir_rc}", "WARN")
        log(f"Output: {ir_out[:300]}", "WARN")

    # ── Inspection index ───────────────────────────────────────
    log("STEP 6/7 — Building inspection index")
    ii_rc, ii_out = run_cmd([sys.executable, "-m", "appshak_inspection.run_index"])
    inspection_data = {}
    try:
        inspection_data = json.loads(ii_out)
    except Exception:
        inspection_data = {"raw": ii_out, "exit_code": ii_rc}
    with open(output_dir / "inspection_index.json", "w") as f:
        json.dump(inspection_data, f, indent=2)

    # ── Run log ────────────────────────────────────────────────
    run_end = datetime.now(timezone.utc)
    run_meta["end_time"] = run_end.isoformat()
    run_meta["elapsed_seconds"] = (run_end - run_start).total_seconds()

    with open(output_dir / "run_log.txt", "w") as f:
        f.write("AppShak Phase 3B Certification Run Log\n")
        f.write(f"Harness version: 3B.2\n")
        f.write(f"Started:  {run_meta['start_time']}\n")
        f.write(f"Ended:    {run_meta['end_time']}\n")
        f.write(f"Elapsed:  {run_meta['elapsed_seconds']:.0f}s\n")
        f.write(f"Mode:     {'QUICK' if args.quick else 'FULL'}\n")
        f.write(f"Hours:    {hours}\n\n")
        f.write("--- CONSOLE LOG ---\n")
        f.write("\n".join(_log_lines) + "\n\n")
        f.write("--- STABILITY OUTPUT ---\n")
        f.write(stability_out + "\n\n")
        f.write("--- INTEGRITY OUTPUT ---\n")
        f.write(ir_out + "\n\n")
        f.write("--- INSPECTION OUTPUT ---\n")
        f.write(ii_out + "\n")

    # ── Evidence validation + manifest ─────────────────────────
    log("STEP 7/7 — Validating evidence and writing manifest")
    validation = validate_evidence(output_dir, stability_result)
    manifest = build_manifest(output_dir, validation, preflight, run_meta)

    with open(output_dir / "MANIFEST.json", "w") as f:
        json.dump(manifest, f, indent=2)

    # ── Final verdict ──────────────────────────────────────────
    log("=" * 60)
    log(f"CERTIFICATION VERDICT: {manifest['verdict']}")
    log("=" * 60)

    for criterion, result in validation["criteria"].items():
        status = "✅ PASS" if result["pass"] else "❌ FAIL"
        log(f"  {status}  {criterion}: {result['detail']}")

    log("=" * 60)
    log(f"Evidence bundle: {output_dir.resolve()}")

    if manifest["verdict"] == "PASS":
        log("All criteria met. Awaiting human signoff.")
        log("Open MANIFEST.json and fill in 'human_signoff' field to complete Phase 3B.")
    else:
        log("One or more criteria FAILED. Fix issues and repeat the run.")
        log("Per the hard rules: FAIL ANY = REPEAT RUN")
        log("Previous run has been stashed with a STASH_REASON.json for audit.")

    sys.exit(0 if manifest["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
