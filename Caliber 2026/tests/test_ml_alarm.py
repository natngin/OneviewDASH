import os
import sys
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi.testclient import TestClient
from app.main import app

class TestMLEarlyAlarm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_01_early_alarm_endpoint(self):
        resp = self.client.get("/api/ml/early-alarm")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertIn("metadata", data)
        meta = data["metadata"]
        self.assertTrue(meta["is_dummy"])
        self.assertIn("DUMMY DATA", meta["dummy_badge"])
        self.assertIn("LANTAI KESELAMATAN", meta["safety_floor_rule"])

        self.assertIn("assets", data)
        self.assertEqual(len(data["assets"]), 5)

        tags = [a["tag"] for a in data["assets"]]
        expected_tags = ["KO-3201", "PM-4405B", "HE-3301", "BL-5702", "PU-2101B"]
        for et in expected_tags:
            self.assertIn(et, tags)

        for a in data["assets"]:
            self.assertIn("tag", a)
            self.assertIn("parameter", a)
            self.assertIn("current_value", a)
            self.assertIn("expected_value", a)
            self.assertIn("residual_zscore", a)
            self.assertIn("rule_alert_threshold", a)
            self.assertIn("rule_trip_threshold", a)
            self.assertIn("combined_status", a)
            self.assertIn("lead_time_hours", a)
            self.assertIn("source_info", a)
            self.assertTrue(a["source_info"]["is_dummy"])

            if a["rule_status"] == "TRIP":
                self.assertEqual(a["combined_status"], "CRITICAL TRIP")
            elif a["rule_status"] == "ALERT":
                self.assertEqual(a["combined_status"], "WARNING ALERT")

        print("PASSED: /api/ml/early-alarm returns 5 assets, verified safety floor and metadata.")

    def test_02_thresholds_endpoint(self):
        resp = self.client.get("/api/ml/thresholds")
        self.assertEqual(resp.status_code, 200)
        cfg = resp.json()
        self.assertEqual(len(cfg), 5)
        for tag in ["KO-3201", "PM-4405B", "HE-3301", "BL-5702", "PU-2101B"]:
            self.assertIn(tag, cfg)
            self.assertIn("alert", cfg[tag])
            self.assertIn("trip", cfg[tag])
            self.assertIn("source", cfg[tag])
            self.assertIn("needs_confirmation", cfg[tag])
        print("PASSED: /api/ml/thresholds verified single source of truth.")

if __name__ == "__main__":
    unittest.main()
