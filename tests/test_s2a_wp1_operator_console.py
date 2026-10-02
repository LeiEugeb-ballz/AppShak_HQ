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
            database = Path(result["database"])
            before = database.read_bytes()
            state = asyncio.run(office_route.endpoint())
            self.assertEqual(database.read_bytes(), before)
            self.assertEqual(state["source"], "canonical_sqlite")
            complete = next(task for task in state["tasks"] if task["task_id"] == result["task_id"])
            self.assertEqual(complete["state"], "COMPLETE")
            self.assertTrue(complete["source_request_id"])
            self.assertTrue(complete["authority_id"])
            self.assertTrue(complete["created_at"])
            self.assertTrue(complete["attempts"][-1]["created_at"])
            self.assertIn("outcome", complete["attempts"][-1])
            self.assertTrue(complete["artifacts"][-1]["created_at"])
            self.assertTrue(complete["criteria"])
            self.assertEqual(complete["validations"][-1]["status"], "PASSED")
            self.assertTrue(complete["validations"][-1]["validator_id"])
            self.assertIsInstance(complete["validations"][-1]["evidence"], dict)
            self.assertTrue(complete["validations"][-1]["checks"])
            self.assertTrue(any(task["state"] == "NEEDS_RECONCILIATION" for task in state["tasks"]))
            self.assertTrue(any(any(run["status"] == "FAILED" for run in task["validations"])
                                for task in state["tasks"]))
            baton = next(baton for baton in state["batons"] if baton["baton_id"] == "BATON-0008")
            self.assertEqual(baton["verification_status"], "VERIFIED")
            self.assertEqual(baton["dispatch_status"], "WAITING_FOR_CAPABILITY")
            self.assertTrue(baton["verification_reason"])
            self.assertTrue(baton["dispatch_reason"])
            self.assertIsNone(baton["target_id"])
