from __future__ import annotations

import asyncio
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from appshak_observability.server import build_standalone_app
from appshak_projection.office_state import read_office_state
from appshak_substrate.s1_certification import certify


def _office_endpoint(app):
    return next(route.endpoint for route in app.routes
                if getattr(route, "path", None) == "/api/office/state")


class TestS1Certification(unittest.TestCase):
    def test_real_slice_restart_and_canonical_office_api(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appshak_s1_cert_") as temp_dir:
            result = certify(temp_dir)
            self.assertEqual(result["status"], "PASS", result.get("error"))
            self.assertEqual(len(result["checks"]), 9)
            db = Path(result["database"])
            state = read_office_state(db)
            self.assertEqual(state["source"], "canonical_sqlite")
            task = next(item for item in state["tasks"] if item["task_id"] == result["task_id"])
            baton = next(item for item in state["batons"] if item["baton_id"] == "BATON-0008")
            self.assertEqual(task["state"], "COMPLETE")
            self.assertEqual(task["validations"][0]["status"], "PASSED")
            self.assertEqual(baton["verification_status"], "VERIFIED")
            self.assertEqual(baton["dispatch_status"], "WAITING_FOR_CAPABILITY")
            app = build_standalone_app(mailstore_db=db,
                projection_view_path=Path(temp_dir) / "view.json")
            self.assertEqual(asyncio.run(_office_endpoint(app)()), state)

    def test_office_api_missing_database_fails_without_creating_it(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appshak_s1_missing_") as temp_dir:
            missing = Path(temp_dir) / "missing.db"
            app = build_standalone_app(mailstore_db=missing,
                projection_view_path=Path(temp_dir) / "view.json")
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(_office_endpoint(app)())
            self.assertEqual(raised.exception.status_code, 503)
            self.assertFalse(missing.exists())

    def test_swarm_startup_refuses_implicit_database_recreation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appshak_s1_startup_") as temp_dir:
            missing = Path(temp_dir) / "missing.db"
            result = subprocess.run([sys.executable, "-m", "appshak_substrate.run_swarm",
                "--db-path", str(missing), "--duration-seconds", "0"],
                capture_output=True, text=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--initialize-db", result.stderr)
            self.assertFalse(missing.exists())
