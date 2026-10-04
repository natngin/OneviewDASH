import os
import sys
import unittest
import math

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Incident

class TestIncidentsKpi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_01_db_incidents_count_and_integrity(self):
        db = SessionLocal()
        try:
            total = db.query(Incident).count()
            self.assertEqual(total, 500, f"Expected 500 incidents in SQL, got {total}")

            historical = db.query(Incident).filter(Incident.is_synthetic == False).count()
            synthetic = db.query(Incident).filter(Incident.is_synthetic == True).count()

            self.assertEqual(historical, 380, f"Expected 380 historical records, got {historical}")
            self.assertEqual(synthetic, 120, f"Expected 120 synthetic records, got {synthetic}")

            # Verify integrity
            invalid_dt = db.query(Incident).filter(Incident.downtime_h < 0).count()
            self.assertEqual(invalid_dt, 0, "Found negative downtime values")

            invalid_loss = db.query(Incident).filter(Incident.act_loss_k_usd < 0).count()
            self.assertEqual(invalid_loss, 0, "Found negative loss values")

            print("PASSED: Database incidents count (380 hist + 120 synth = 500) and integrity verified.")
        finally:
            db.close()

    def test_02_incidents_kpi_endpoint(self):
        resp = self.client.get("/api/incidents/kpi")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["total_incidents"], 500)
        self.assertEqual(data["historical_count"], 380)
        self.assertEqual(data["synthetic_count"], 120)

        self.assertGreater(data["total_downtime_h"], 2000.0)
        self.assertGreater(data["total_loss_k_usd"], 60000.0)
        self.assertGreater(data["avg_loss_per_incident_k_usd"], 0)

        # Check disciplines
        disc_names = {d["discipline"] for d in data["by_discipline"]}
        self.assertTrue({"ROT", "STA", "INS", "ELE"}.issubset(disc_names))
        disc_sum = sum(d["count"] for d in data["by_discipline"])
        self.assertEqual(disc_sum, 500, "Sum of discipline counts must equal 500")

        # Check top 5 loss
        self.assertEqual(len(data["top_5_loss_incidents"]), 5)
        top_losses = [inc["act_loss_k_usd"] for inc in data["top_5_loss_incidents"]]
        self.assertEqual(top_losses, sorted(top_losses, reverse=True), "Top loss incidents not sorted descending")

        print("PASSED: /api/incidents/kpi calculations and aggregations verified.")

    def test_03_incidents_filters(self):
        # Filter by ROT discipline
        r_rot = self.client.get("/api/incidents?discipline=ROT&limit=200")
        self.assertEqual(r_rot.status_code, 200)
        items_rot = r_rot.json()["items"]
        for it in items_rot:
            self.assertEqual(it["discipline"], "ROT")

        # Filter by synthetic
        r_synth = self.client.get("/api/incidents?is_synthetic=true&limit=200")
        self.assertEqual(r_synth.status_code, 200)
        self.assertEqual(r_synth.json()["total"], 120)

        # Filter by historical
        r_hist = self.client.get("/api/incidents?is_synthetic=false&limit=10")
        self.assertEqual(r_hist.status_code, 200)
        self.assertEqual(r_hist.json()["total"], 380)

        print("PASSED: /api/incidents filtering by discipline, synthetic status verified.")

if __name__ == "__main__":
    unittest.main()
