from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from appshak_viz_feed.exporter import dataset_gate_satisfied
from appshak_viz_feed.src.normalize import sort_warnings
from appshak_viz_feed.src.reducer import initial_state, reduce_event


class TestVizReplayContract(unittest.TestCase):
    def test_module_entrypoint_exists(self) -> None:
        replay_path = Path(__file__).resolve().parents[1] / "replay.py"
        self.assertTrue(replay_path.exists())
        text = replay_path.read_text(encoding="utf-8")
        self.assertIn("from appshak_viz_feed.src.replay import main", text)

    def test_module_help_returns_zero(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "appshak_viz_feed.replay", "--help"],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("appshak_viz_feed.replay", result.stdout)

    def test_same_input_feed_produces_same_outputs(self) -> None:
        events = [
            _viz_event(seq=1, phase="INTAKE", outcome=None, activity="START", status="queued"),
            _viz_event(seq=2, phase="BUILD", outcome=None, activity="ACTIVE", status="running"),
            _viz_event(seq=3, phase="APPROVAL", outcome="EXECUTED", activity="FINISH", status="executed"),
        ]
        with tempfile.TemporaryDirectory(prefix="viz_contract_") as temp_dir:
            root = Path(temp_dir)
            events_path = root / "events.ndjson"
            _write_ndjson(events_path, events)
            out_a = root / "out-a"
            out_b = root / "out-b"

            for out_dir in (out_a, out_b):
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "appshak_viz_feed.replay",
                        "--run",
                        "run-demo",
                        "--events",
                        str(events_path),
                        "--out",
                        str(out_dir),
                        "--emit-projection-snapshot",
                        "--emit-replay-summary",
                        "--emit-report",
                    ],
                    cwd=Path(__file__).resolve().parents[2],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, msg=result.stderr)

            self.assertEqual(
                _read_json(out_a / "projection_snapshot.json"),
                _read_json(out_b / "projection_snapshot.json"),
            )
            self.assertEqual(
                _read_json(out_a / "expected_snapshot.json"),
                _read_json(out_b / "expected_snapshot.json"),
            )
            self.assertEqual(
                _read_json(out_a / "replay_report.json"),
                _read_json(out_b / "replay_report.json"),
            )

    def test_blocked_never_renders_executed(self) -> None:
        st = initial_state()
        st = reduce_event(
            st,
            _viz_event(
                seq=1,
                phase="APPROVAL",
                outcome="BLOCKED",
                activity="FINISH",
                status="blocked_by_safeguard",
                room_hint="boardroom",
            ),
        )
        self.assertEqual(st.jobs["job-1"]["status"], "BLOCKED")
        self.assertEqual(st.jobs["job-1"]["outcome"], "BLOCKED")
        self.assertEqual(st.agents["recon"]["room_id"], "quarantine")

    def test_invalid_outcome_never_coerces_terminal_governance_state(self) -> None:
        st = initial_state()
        st = reduce_event(
            st,
            _viz_event(
                seq=1,
                phase=None,
                outcome="executed-ish",
                activity=None,
                status="executed",
            ),
        )
        self.assertEqual(st.jobs["job-1"]["status"], "UNKNOWN")
        self.assertIsNone(st.jobs["job-1"]["outcome"])
        self.assertEqual(st.agents["recon"]["state"], "UNKNOWN")
        self.assertEqual(st.warnings[0]["code"], "INVALID_OUTCOME")

    def test_invalid_activity_never_drives_motion(self) -> None:
        st = initial_state()
        st = reduce_event(
            st,
            _viz_event(
                seq=1,
                phase=None,
                outcome=None,
                activity="busy-ish",
                status="running",
            ),
        )
        self.assertEqual(st.agents["recon"]["state"], "UNKNOWN")
        self.assertEqual(st.warnings[0]["code"], "INVALID_ACTIVITY")

    def test_warning_ordering_is_deterministic(self) -> None:
        ordered = sort_warnings(
            [
                {"code": "INVALID_OUTCOME", "message": "outcome"},
                {"code": "UNKNOWN_SEVERITY", "message": "severity"},
                {"code": "INVALID_ACTIVITY", "message": "activity"},
                {"code": "UNKNOWN_ORIGIN_ROLE", "message": "role"},
            ]
        )
        self.assertEqual(
            [warning["code"] for warning in ordered],
            ["UNKNOWN_ORIGIN_ROLE", "UNKNOWN_SEVERITY", "INVALID_ACTIVITY", "INVALID_OUTCOME"],
        )

    def test_dataset_gate_relies_on_manifest_flag(self) -> None:
        with tempfile.TemporaryDirectory(prefix="viz_manifest_") as temp_dir:
            manifest_path = Path(temp_dir) / "manifest.json"
            manifest_path.write_text(
                json.dumps({"dataset_requirements": {"all_satisfied": True}}),
                encoding="utf-8",
            )
            self.assertTrue(dataset_gate_satisfied(manifest_path))

            manifest_path.write_text(
                json.dumps({"dataset_requirements": {"all_satisfied": False}}),
                encoding="utf-8",
            )
            self.assertFalse(dataset_gate_satisfied(manifest_path))


def _viz_event(
    *,
    seq: int,
    phase: str | None,
    outcome: str | None,
    activity: str | None,
    status: str,
    room_hint: str | None = None,
) -> dict:
    payload = {
        "severity": "INFO",
        "status": status,
        "target_role": "builder",
    }
    if phase is not None:
        payload["phase"] = phase
    if room_hint is not None:
        payload["room_hint"] = room_hint
    if outcome is not None:
        payload["outcome"] = outcome
    if activity is not None:
        payload["activity"] = activity
    return {
        "schema_version": "viz_event/1.0",
        "event_id": f"evt-{seq}",
        "run_id": "run-demo",
        "seq": seq,
        "ts": f"2026-03-09T10:00:{seq:02d}+00:00",
        "type": "AGENT_STATUS",
        "origin_id": "recon",
        "origin_role": "SCOUT",
        "job_id": "job-1",
        "correlation_id": "corr-1",
        "payload": payload,
    }


def _write_ndjson(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
