import os
import sys
import json
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi.testclient import TestClient
from app.main import app

SEED_DIR = os.path.join(PROJECT_ROOT, "seed")

def load_seed(filename):
    with open(os.path.join(SEED_DIR, filename), "r", encoding="utf-8") as f:
        return json.load(f)

class TestParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.seed_alarms = load_seed("PREDICTIVE_ALARM_DATA.json")
        cls.seed_equipment = load_seed("DETAILED_EQUIPMENT_DATA.json")
        cls.seed_pie_status = load_seed("PIE_STATUS_DATA.json")
        cls.seed_energy_24h = load_seed("energy_24h.json")
        cls.seed_energy_30d = load_seed("energy_30d.json")

    def test_01_alarms_parity(self):
        resp = self.client.get("/api/alarms")
        self.assertEqual(resp.status_code, 200)
        api_alarms = resp.json()

        self.assertEqual(len(api_alarms), len(self.seed_alarms), "Alarms count mismatch")

        # Map by tag for field-by-field verification
        api_map = {a["tag"]: a for a in api_alarms}
        seed_map = {a["tag"]: a for a in self.seed_alarms}

        for tag, seed_al in seed_map.items():
            self.assertIn(tag, api_map, f"Tag {tag} missing in API response")
            api_al = api_map[tag]

            self.assertEqual(api_al["tag"], seed_al["tag"])
            self.assertEqual(api_al["namaAset"], seed_al["namaAset"])
            self.assertEqual(api_al["plant"], seed_al["plant"])
            self.assertEqual(api_al["cls"], seed_al["cls"])
            self.assertEqual(api_al["health"], seed_al["health"])
            self.assertEqual(api_al["healthStatus"], seed_al["healthStatus"])
            self.assertEqual(api_al["posibleFailure"], seed_al["posibleFailure"])
            self.assertEqual(api_al["severity"], seed_al["severity"])
            self.assertEqual(api_al["leadTime"], seed_al["leadTime"])
            self.assertEqual(api_al["rootCause"], seed_al["rootCause"])

            # Impact
            self.assertEqual(api_al["impact"]["downtime"], seed_al["impact"]["downtime"])
            self.assertEqual(api_al["impact"]["lossTons"], seed_al["impact"]["lossTons"])
            self.assertEqual(api_al["impact"]["financialLoss"], seed_al["impact"]["financialLoss"])

            # Telemetry
            self.assertEqual(len(api_al["telemetry"]), len(seed_al["telemetry"]))
            for at, st in zip(api_al["telemetry"], seed_al["telemetry"]):
                self.assertEqual(at["param"], st["param"])
                self.assertEqual(at["current"], st["current"])
                self.assertEqual(at["status"], st["status"])

            # Incidents
            self.assertEqual(len(api_al["incidents"]), len(seed_al.get("incidents", [])))
            for ai, si in zip(api_al["incidents"], seed_al.get("incidents", [])):
                self.assertEqual(ai["date"], si["date"])
                self.assertEqual(ai["ar"], si["ar"])
                self.assertEqual(ai["event"], si["event"])
                self.assertEqual(ai["loss"], si["loss"])

        # Check sorting: lowest health first
        health_scores = [a["health"] for a in api_alarms]
        self.assertEqual(health_scores, sorted(health_scores), "Alarms not sorted by health ascending")
        print(f"PASSED: Alarms parity verified for all {len(api_alarms)} records.")

    def test_02_performance_parity(self):
        resp = self.client.get("/api/performance/restored")
        self.assertEqual(resp.status_code, 200)
        api_perf = resp.json()

        self.assertEqual(len(api_perf), len(self.seed_equipment), "Equipment count mismatch")

        api_map = {e["tag"]: e for e in api_perf}
        seed_map = {e["tag"]: e for e in self.seed_equipment}

        for tag, seed_eq in seed_map.items():
            self.assertIn(tag, api_map, f"Equipment tag {tag} missing in API response")
            api_eq = api_map[tag]

            self.assertEqual(api_eq["tag"], seed_eq["tag"])
            self.assertEqual(api_eq["name"], seed_eq["name"])
            self.assertEqual(api_eq["plant"], seed_eq["plant"])
            self.assertEqual(api_eq["cls"], seed_eq["cls"])
            self.assertEqual(api_eq["category"], seed_eq["category"])
            self.assertAlmostEqual(api_eq["tripPct"], seed_eq["tripPct"], places=1)
            self.assertAlmostEqual(api_eq["downtime"], seed_eq["downtime"], places=1)
            self.assertAlmostEqual(api_eq["avail"], seed_eq["avail"], places=2)
            self.assertAlmostEqual(api_eq["mtbf"], seed_eq["mtbf"], places=1)
            self.assertAlmostEqual(api_eq["mttr"], seed_eq["mttr"], places=1)
            self.assertAlmostEqual(api_eq["lossTons"], seed_eq["lossTons"], places=1)
            self.assertAlmostEqual(api_eq["lossK"], seed_eq["lossK"], places=1)
            self.assertAlmostEqual(api_eq["pmComp"], seed_eq["pmComp"], places=1)
            self.assertEqual(api_eq["alarmWeeks"], seed_eq["alarmWeeks"])
            self.assertEqual(api_eq["monitoredParameter"], seed_eq.get("monitoredParameter"))
            self.assertEqual(api_eq["currentVal"], seed_eq.get("currentVal"))
            self.assertEqual(api_eq["tripTelemetry"], seed_eq.get("tripTelemetry"))
            self.assertEqual(api_eq["threshold"], seed_eq.get("threshold"))
            self.assertEqual(api_eq["failDate"], seed_eq.get("failDate"))
            self.assertEqual(api_eq["failMechanism"], seed_eq.get("failMechanism"))
            self.assertEqual(api_eq["restoredDate"], seed_eq.get("restoredDate"))
            self.assertEqual(api_eq["daysSinceRestore"], seed_eq.get("daysSinceRestore"))
            self.assertEqual(api_eq["currentStatus"], seed_eq.get("currentStatus"))
            self.assertEqual(api_eq["capaStatus"], seed_eq.get("capaStatus"))
            self.assertEqual(api_eq["capaOwner"], seed_eq.get("capaOwner"))
            self.assertEqual(api_eq["recurrence"], seed_eq.get("recurrence", 0))

            # 26-week timeline parity
            self.assertEqual(len(api_eq["timeline"]), len(seed_eq["timeline"]), f"Timeline length mismatch for {tag}")
            self.assertEqual(api_eq["timeline"], seed_eq["timeline"], f"Timeline content mismatch for {tag}")

        print(f"PASSED: Equipment performance parity verified for all {len(api_perf)} records.")

    def test_03_energy_parity(self):
        resp = self.client.get("/api/energy?days=30")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        load24h = data["load24h"]
        days30 = data["days30"]

        self.assertEqual(len(load24h), len(self.seed_energy_24h))
        self.assertEqual(len(days30), len(self.seed_energy_30d))

        for a, s in zip(load24h, self.seed_energy_24h):
            self.assertEqual(a["t"], s["t"])
            self.assertEqual(a["actual"], s["actual"])
            self.assertEqual(a["limit"], s["limit"])

        for a, s in zip(days30, self.seed_energy_30d):
            self.assertEqual(a["day"], s["day"])
            self.assertEqual(a["date"], s["date"])
            self.assertAlmostEqual(a["totalMwh"], s["totalMwh"], places=1)
            self.assertEqual(a["peakKwh"], s["peakKwh"])
            self.assertEqual(a["limit"], s["limit"])
            self.assertAlmostEqual(a["intensity"], s["intensity"], places=1)
            self.assertAlmostEqual(a["cost"], s["cost"], places=1)
            self.assertAlmostEqual(a["co2e"], s["co2e"], places=1)
            self.assertAlmostEqual(a["compressors"], s["compressors"], places=1)
            self.assertAlmostEqual(a["pumps"], s["pumps"], places=1)
            self.assertAlmostEqual(a["blowers"], s["blowers"], places=1)
            self.assertAlmostEqual(a["auxiliary"], s["auxiliary"], places=1)
            self.assertEqual(a["isAlert"], s["isAlert"])

        print(f"PASSED: Energy parity verified for 24H ({len(load24h)} pts) and 30D ({len(days30)} pts).")

    def test_04_executive_kpi_parity(self):
        resp = self.client.get("/api/kpi/executive")
        self.assertEqual(resp.status_code, 200)
        kpi = resp.json()

        self.assertEqual(kpi["totalMonitored"], len(self.seed_alarms))
        self.assertEqual(kpi["criticalCount"], 2)
        self.assertEqual(kpi["warningCount"], 4)
        self.assertEqual(kpi["watchlistCount"], 5)
        self.assertEqual(kpi["activeAlarmCount"], 6)
        self.assertEqual(kpi["tripCount"], 2)
        self.assertEqual(kpi["overdueCount"], 1)

        # Pie status parity
        seed_pie_map = {p["name"]: p for p in self.seed_pie_status}
        for p in kpi["pieStatus"]:
            self.assertIn(p["name"], seed_pie_map)
            self.assertEqual(int(p["value"]), int(seed_pie_map[p["name"]]["value"]))
            self.assertEqual(p["pct"], seed_pie_map[p["name"]]["pct"])

        print("PASSED: Executive KPI calculations and summary parity verified.")

if __name__ == "__main__":
    unittest.main()
