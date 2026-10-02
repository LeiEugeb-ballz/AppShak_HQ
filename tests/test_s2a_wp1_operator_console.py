from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from appshak_observability.server import build_standalone_app
from appshak_substrate.s1_certification import certify


class TestOperatorConsoleProjection(unittest.TestCase):
    def test_s1_certification_truth_is_exposed_by_read_only_office_api(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appshak_s2a_api_") as temp_dir:
            result = certify(temp_dir)
            self.assertEqual(result["status"], "PASS", result.get("error"))
            app = build_standalone_app(
                mailstore_db=Path(result["database"]),
                projection_view_path=Path(temp_dir) / "view.json",
            )
            office_route = next(route for route in app.routes
                                if getattr(route, "path", None) == "/api/office/state")
            self.assertEqual(office_route.methods, {"GET"})
            state = asyncio.run(office_route.endpoint())
            self.assertEqual(state["source"], "canonical_sqlite")
            complete = next(task for task in state["tasks"] if task["task_id"] == result["task_id"])
            self.assertEqual(complete["state"], "COMPLETE")
            self.assertEqual(complete["validations"][-1]["status"], "PASSED")
            self.assertTrue(any(task["state"] == "NEEDS_RECONCILIATION" for task in state["tasks"]))
            self.assertTrue(any(any(run["status"] == "FAILED" for run in task["validations"])
                                for task in state["tasks"]))
            baton = next(baton for baton in state["batons"] if baton["baton_id"] == "BATON-0008")
            self.assertEqual(baton["verification_status"], "VERIFIED")
            self.assertEqual(baton["dispatch_status"], "WAITING_FOR_CAPABILITY")
            self.assertIsNone(baton["target_id"])
