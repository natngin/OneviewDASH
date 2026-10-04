import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_alarm_board_endpoint_structure():
    response = client.get("/api/ml/alarm-board")
    assert response.status_code == 200
    data = response.json()

    assert "metadata" in data
    assert "summary" in data
    assert "repair" in data
    assert "watchlist" in data

    assert data["metadata"]["is_dummy"] is True
    assert data["summary"]["total_assets"] == 11
    assert data["summary"]["repair_count"] >= 1
    assert data["summary"]["watchlist_count"] >= 1
    # User requirement: sembunyikan aset yang normal
    assert data["summary"]["normal_hidden_count"] >= 1
    assert "EX-1105" in data["summary"]["normal_hidden_tags"]

def test_alarm_board_safety_floor_and_causes():
    response = client.get("/api/ml/alarm-board")
    assert response.status_code == 200
    data = response.json()

    repair_tags = [a["tag"] for a in data["repair"]]
    watchlist_tags = [a["tag"] for a in data["watchlist"]]

    # Intersection must be empty (mutually exclusive)
    assert set(repair_tags).isdisjoint(set(watchlist_tags))

    # All repair assets must have dominant sensor cause, reasons, priority, and actions
    for a in data["repair"]:
        assert "tag" in a
        assert "asset_name" in a
        assert "status" in a
        assert a["status"] in ("CRITICAL TRIP", "ALERT", "EARLY WARNING")
        assert len(a["reasons"]) >= 1
        assert "dominant" in a
        dom = a["dominant"]
        assert "param_label" in dom
        assert "current_value" in dom
        assert "expected_value" in dom
        assert "rolling_zscore" in dom
        assert "failure_mode" in dom
        assert "actions" in a
        assert "immediate" in a["actions"]
        assert "pic" in a["actions"]

    # Verify safety floor: no asset in watchlist has rule_status TRIP or ALERT
    for a in data["watchlist"]:
        for p in a.get("parameters", []):
            assert p.get("rule_status") not in ("TRIP", "ALERT")
        # Dominant cause exists
        assert "dominant" in a or "reason" in a

def test_alarm_board_series_downsampling():
    # Test with series enabled
    r1 = client.get("/api/ml/alarm-board?include_series=true&step=5")
    assert r1.status_code == 200
    d1 = r1.json()
    first_repair = d1["repair"][0]
    assert "series" in first_repair["dominant"]
    assert len(first_repair["dominant"]["series"]) > 0

    # Test with series disabled
    r2 = client.get("/api/ml/alarm-board?include_series=false")
    assert r2.status_code == 200
    d2 = r2.json()
    first_repair_no_series = d2["repair"][0]
    assert len(first_repair_no_series["dominant"]["series"]) == 0
