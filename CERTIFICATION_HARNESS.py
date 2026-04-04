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
    4. Launches observability server in background
    5. Runs stability harness for --hours
    6. Generates integrity report
    7. Builds inspection index
    8. Validates all evidence criteria
    9. Writes signed manifest + pass/fail verdict

Evidence bundle contents:
    - stability_result.json
    - integrity_report.json
    - inspection_index.json
    - pre_flight_results.json
    - run_log.txt
    - MANIFEST.json  (pass/fail verdict + hash summary)
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
INTEGRITY_ROOT = "appshak_state/integrity"
INSPECTION_ROOT = "appshak_state/inspection"
STABILITY_ROOT = "appshak_state/stability"
OBS_HOST = "127.0.0.1"
OBS_PORT = 8010

AGENTS = ["recon", "forge", "command"]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def log(msg: str, level: str = "INFO") -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] [{level}] {msg}"
    print(line)
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


# ─── Process Management ───────────────────────────────────────────────────────

class ProcessGroup:
    """Manages background processes for the certification run."""

    def __init__(self):
        self._procs: list[subprocess.Popen] = []

    def start(self, args: list[str], label: str) -> None:
        log(f"Starting: {label}")
        p = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self._procs.append(p)
        log(f"  PID {p.pid}: {label}")

    def stop_all(self) -> None:
        log("Stopping all background processes...")
        for p in self._procs:
            try:
                p.send_signal(signal.SIGTERM)
            except Exception:
                pass
        time.sleep(2)
        for p in self._procs:
            try:
                if p.poll() is None:
                    p.kill()
            except Exception:
                pass
        log("All background processes stopped.")


# ─── Evidence Validation ──────────────────────────────────────────────────────

def validate_evidence(output_dir: Path, stability_result: dict) -> dict:
    """
    Validates the 3B certification criteria against collected evidence.
    Returns a dict with per-criterion results and overall pass/fail.
    """
    criteria = {}

    # 1. Run requirements — no crashes, watchdog OK
    run_ok = stability_result.get("passed", False)
    criteria["no_crash_watchdog_ok"] = {
        "pass": run_ok,
        "detail": stability_result.get("summary", "No summary available"),
    }

    # 2. Data integrity — projection populated
    proj_path = PROJECTION_VIEW
    proj_data = None
    if os.path.exists(proj_path):
        try:
            with open(proj_path) as f:
                proj_data = json.load(f)
        except Exception as e:
            proj_data = None
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

    # 3. Event continuity — check stability result for gaps
    gaps = stability_result.get("event_gaps", 0)
    criteria["event_continuity_no_gaps"] = {
        "pass": gaps == 0,
        "detail": f"Event gaps detected: {gaps}" if gaps else "No event gaps detected",
    }

    # 4. Integrity fields present
    integrity_reports = list(Path(INTEGRITY_ROOT).glob("*.json")) if Path(INTEGRITY_ROOT).exists() else []
    criteria["integrity_fields_present"] = {
        "pass": len(integrity_reports) > 0,
        "detail": f"Integrity reports found: {len(integrity_reports)}" if integrity_reports else "No integrity reports found",
    }

    # 5. Governance — decisions traceable (ledger exists and non-empty)
    ledger_path = GOVERNANCE_LEDGER
    ledger_lines = 0
    if os.path.exists(ledger_path):
        with open(ledger_path) as f:
            ledger_lines = sum(1 for _ in f)
    criteria["decisions_traceable"] = {
        "pass": ledger_lines > 0,
        "detail": f"Governance ledger entries: {ledger_lines}",
    }

    # 6. Replay determinism — check stability result
    replay_ok = stability_result.get("replay_deterministic", None)
    criteria["replay_deterministic"] = {
        "pass": replay_ok is True,
        "detail": "Replay hash equality confirmed" if replay_ok else "Replay not confirmed or failed",
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
    """Builds the MANIFEST.json with file hashes and verdict."""
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
        "schema_version": "3B.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_meta": run_meta,
        "verdict": "PASS" if validation["overall_pass"] else "FAIL",
        "certification_criteria": validation["criteria"],
        "overall_pass": validation["overall_pass"],
        "preflight_pass": preflight["passed"],
        "file_hashes": file_hashes,
        "human_signoff": None,  # To be filled in manually
        "notes": "",
    }

    return manifest


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="AppShak Phase 3B Certification Harness")
    parser.add_argument("--hours", type=float, default=DEFAULT_HOURS)
    parser.add_argument("--quick", action="store_true", help="Run 5-minute smoke test instead of full 6h run")
    parser.add_argument("--output-dir", type=str, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    hours = QUICK_HOURS if args.quick else args.hours
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_start = datetime.now(timezone.utc)
    run_meta = {
        "start_time": run_start.isoformat(),
        "planned_hours": hours,
        "quick_mode": args.quick,
    }

    log("=" * 60)
    log(f"AppShak Phase 3B Certification Harness")
    log(f"Mode: {'QUICK (5min)' if args.quick else f'FULL ({hours}h)'}")
    log(f"Output: {output_dir.resolve()}")
    log("=" * 60)

    # ── Pre-flight ─────────────────────────────────────────────
    log("STEP 1/6 — Pre-flight checks")
    preflight = run_preflight()
    with open(output_dir / "pre_flight_results.json", "w") as f:
        json.dump(preflight, f, indent=2)

    if not preflight["passed"]:
        log("PRE-FLIGHT FAILED. Fix all chamber/test failures before certifying.", "ERROR")
        log("Evidence written to: " + str(output_dir))
        sys.exit(1)

    log("Pre-flight PASSED. Proceeding to certification run.")

    # ── Launch background services ─────────────────────────────
    log("STEP 2/6 — Starting background services")
    procs = ProcessGroup()

    procs.start([
        sys.executable, "-m", "appshak_substrate.run_swarm",
        "--agents", *AGENTS,
        "--durable", "--worktrees",
        "--duration-seconds", str(int(hours * 3600 + 120)),  # slightly longer than stability run
    ], "Swarm supervisor")

    time.sleep(3)  # let swarm initialise

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

    # ── Stability run ──────────────────────────────────────────
    log(f"STEP 3/6 — Running stability harness ({hours}h)...")
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

    stability_result = {}
    try:
        stability_result = json.loads(stability_out)
    except json.JSONDecodeError:
        log(f"Could not parse stability output as JSON. Raw output:\n{stability_out}", "WARN")
        stability_result = {"passed": stability_rc == 0, "raw_output": stability_out}

    with open(output_dir / "stability_result.json", "w") as f:
        json.dump(stability_result, f, indent=2)
    log(f"Stability run complete. Exit code: {stability_rc}")

    # ── Stop background services ───────────────────────────────
    procs.stop_all()

    # ── Integrity report ───────────────────────────────────────
    log("STEP 4/6 — Generating integrity report")
    ir_rc, ir_out = run_cmd([
        sys.executable, "-m", "appshak_integrity.run_report",
        "--window", "7d",
        "--projection-view", PROJECTION_VIEW,
        "--governance-ledger", GOVERNANCE_LEDGER,
        "--output-dir", INTEGRITY_ROOT,
    ])
    integrity_data = {}
    try:
        integrity_data = json.loads(ir_out)
    except Exception:
        integrity_data = {"raw": ir_out}
    with open(output_dir / "integrity_report.json", "w") as f:
        json.dump(integrity_data, f, indent=2)

    # ── Inspection index ───────────────────────────────────────
    log("STEP 5/6 — Building inspection index")
    ii_rc, ii_out = run_cmd([
        sys.executable, "-m", "appshak_inspection.run_index",
    ])
    inspection_data = {}
    try:
        inspection_data = json.loads(ii_out)
    except Exception:
        inspection_data = {"raw": ii_out}
    with open(output_dir / "inspection_index.json", "w") as f:
        json.dump(inspection_data, f, indent=2)

    # ── Run log ────────────────────────────────────────────────
    run_end = datetime.now(timezone.utc)
    run_meta["end_time"] = run_end.isoformat()
    run_meta["elapsed_seconds"] = (run_end - run_start).total_seconds()

    with open(output_dir / "run_log.txt", "w") as f:
        f.write(f"AppShak Phase 3B Certification Run Log\n")
        f.write(f"Started:  {run_meta['start_time']}\n")
        f.write(f"Ended:    {run_meta['end_time']}\n")
        f.write(f"Elapsed:  {run_meta['elapsed_seconds']:.0f}s\n")
        f.write(f"Mode:     {'QUICK' if args.quick else 'FULL'}\n")
        f.write(f"Hours:    {hours}\n\n")
        f.write("--- STABILITY OUTPUT ---\n")
        f.write(stability_out + "\n\n")
        f.write("--- INTEGRITY OUTPUT ---\n")
        f.write(ir_out + "\n\n")
        f.write("--- INSPECTION OUTPUT ---\n")
        f.write(ii_out + "\n")

    # ── Evidence validation + manifest ─────────────────────────
    log("STEP 6/6 — Validating evidence and writing manifest")
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

    sys.exit(0 if manifest["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
