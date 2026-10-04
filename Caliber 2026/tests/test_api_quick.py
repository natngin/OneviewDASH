import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_endpoints():
    print("Testing /api/health...")
    r = client.get("/api/health")
    assert r.status_code == 200, f"Health failed: {r.text}"
    print("Health response:", r.json())

    print("\nTesting /api/kpi/executive...")
    r = client.get("/api/kpi/executive")
    assert r.status_code == 200, f"KPI failed: {r.text}"
    kpi_data = r.json()
    print("KPI totalMonitored:", kpi_data["totalMonitored"])
    print("KPI activeAlarmCount:", kpi_data["activeAlarmCount"])
    print("KPI top5Alarms length:", len(kpi_data["top5Alarms"]))
    print("KPI top5 first asset health:", kpi_data["top5Alarms"][0]["tag"], kpi_data["top5Alarms"][0]["health"])

    print("\nTesting /api/alarms...")
    r = client.get("/api/alarms")
    assert r.status_code == 200, f"Alarms failed: {r.text}"
    alarms = r.json()
    print("Alarms count:", len(alarms))
    print("Lowest health alarm:", alarms[0]["tag"], f"{alarms[0]['health']}%")

    print("\nTesting /api/performance/restored...")
    r = client.get("/api/performance/restored")
    assert r.status_code == 200, f"Performance failed: {r.text}"
    perf = r.json()
    print("Performance records:", len(perf))
    print("First performance record:", perf[0]["tag"], "Loss:", perf[0]["lossK"], "Timeline len:", len(perf[0]["timeline"]))

    print("\nTesting /api/assets/KO-3201/timeline...")
    r = client.get("/api/assets/KO-3201/timeline")
    assert r.status_code == 200, f"Timeline failed: {r.text}"
    print("KO-3201 timeline length:", len(r.json()["timeline"]))

    print("\nTesting /api/energy?days=30...")
    r = client.get("/api/energy?days=30")
    assert r.status_code == 200, f"Energy failed: {r.text}"
    energy = r.json()
    print("Energy 24h count:", len(energy["load24h"]))
    print("Energy 30d count:", len(energy["days30"]))

    print("\nALL QUICK TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_endpoints()
