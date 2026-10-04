import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_full_live_server():
    # 1. Test Static index.html root
    print("Testing GET / ...")
    r = client.get("/")
    assert r.status_code == 200
    assert "<title>ONEVIEW — Intelligent Manufacturing Command Center</title>" in r.text
    print("GET / returned HTML successfully (size:", len(r.text), "bytes)")

    # 2. Test Executive KPI
    print("\nTesting GET /api/kpi/executive ...")
    r = client.get("/api/kpi/executive")
    assert r.status_code == 200
    kpi = r.json()
    assert kpi["totalMonitored"] == 11
    assert kpi["activeAlarmCount"] == 6
    assert kpi["criticalCount"] == 2
    assert kpi["warningCount"] == 4
    assert kpi["tripCount"] == 2
    assert kpi["overdueCount"] == 1
    print("Executive KPI counts verified:", kpi["activeAlarmCount"], "active alarms")

    # 3. Test Alarms list
    print("\nTesting GET /api/alarms ...")
    r = client.get("/api/alarms")
    assert r.status_code == 200
    alarms = r.json()
    assert len(alarms) == 11
    assert alarms[0]["tag"] == "KO-3201" # Lowest health (28%)
    assert alarms[0]["health"] == 28
    print("Alarms list verified: First asset is", alarms[0]["tag"], "with health", alarms[0]["health"])

    # 4. Test Alarms query filters
    print("\nTesting GET /api/alarms?severity=CRITICAL ...")
    r = client.get("/api/alarms?severity=CRITICAL")
    assert r.status_code == 200
    crit_alarms = r.json()
    assert len(crit_alarms) == 2
    print("Filtered critical alarms:", [a["tag"] for a in crit_alarms])

    # 5. Test Performance restored
    print("\nTesting GET /api/performance/restored ...")
    r = client.get("/api/performance/restored")
    assert r.status_code == 200
    perf = r.json()
    assert len(perf) == 8
    print("Performance restored count:", len(perf))

    # 6. Test Energy 24h & 30d
    print("\nTesting GET /api/energy?days=30 ...")
    r = client.get("/api/energy?days=30")
    assert r.status_code == 200
    energy = r.json()
    assert len(energy["load24h"]) == 13
    assert len(energy["days30"]) == 30
    print("Energy readings verified: 24H points =", len(energy["load24h"]), ", 30D points =", len(energy["days30"]))

    print("\nALL LIVE SERVER TESTS COMPLETED WITH 100% SUCCESS!")

if __name__ == "__main__":
    test_full_live_server()
