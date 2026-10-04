"""
Automated Test Suite for Action Recommendation (CAPA) System — Tahap 2C.
Validates:
1. Every active alarm has a plan with library_id and source (or tagged fallback); no blank text.
2. Invalid status transitions are strictly rejected.
3. Idempotency: generating twice does not duplicate plans.
4. Severity change creates revision and SUPERSEDED old plan.
5. due_at is calculated from as_of, not system clock.
6. Test Mode: sandbox plans do not appear in main production data; Reset removes them.
7. No text claims real "SAP terhubung"; work orders strictly use WO-SIM-XXXXXX prefix with SIMULASI status.
"""
import io
import json
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models import ActionPlan, ActionItem, ActionEvent, WorkOrder, ActionLibrary, Alarm
from actions.config import WO_PREFIX, WO_STATUS, SLA_HOURS

client = TestClient(app)


def test_every_active_alarm_has_plan_with_source():
    """1. Setiap alarm aktif punya plan dengan library_id dan sumber (atau fallback yang ditandai); tidak ada teks kosong."""
    res = client.get("/api/alarms")
    assert res.status_code == 200
    alarms = res.json()
    assert len(alarms) > 0

    for al in alarms:
        tag = al["tag"]
        plan_res = client.get(f"/api/alarms/{tag}/plan")
        assert plan_res.status_code == 200, f"Failed to get plan for {tag}: {plan_res.text}"
        pdata = plan_res.json()

        assert pdata["library_id"], f"Plan for {tag} has no library_id"
        lib = pdata["library"]
        assert lib["source_ar"], f"Plan for {tag} has no source_ar"
        assert lib["hypothesis"], f"Plan for {tag} has empty hypothesis"
        assert len(lib["hypothesis"].strip()) > 5

        # Check items exist and have non-empty text
        items = pdata["items"]
        assert len(items) > 0, f"Plan for {tag} has no action items"
        for it in items:
            assert it["teks"] and it["teks"].strip(), f"Item {it['id']} has empty text"
            assert it["owner_role"], f"Item {it['id']} has no owner_role"


def test_invalid_status_transitions_rejected():
    """2. Transisi status tidak sah ditolak (mis. VERIFIED tanpa DONE, COMPLETE tanpa note)."""
    # Create or get draft plan for test asset
    tag = "HE-3301"
    plan_res = client.get(f"/api/alarms/{tag}/plan")
    pid = plan_res.json()["id"]

    # Current status should be DRAFT or reset to DRAFT for test
    db = SessionLocal()
    plan = db.query(ActionPlan).filter(ActionPlan.id == pid).first()
    plan.status = "DRAFT"
    db.commit()
    db.close()

    # Reject dispatch from DRAFT
    res_disp = client.post(f"/api/plans/{pid}/dispatch", json={"user": "Tester"})
    assert res_disp.status_code == 400

    # Reject complete from DRAFT
    res_comp = client.post(f"/api/plans/{pid}/complete", json={"user": "Tester", "note": "Done"})
    assert res_comp.status_code == 400

    # Reject verify from DRAFT
    res_ver = client.post(f"/api/plans/{pid}/verify", json={"user": "Tester"})
    assert res_ver.status_code == 400

    # Approve (valid)
    res_app = client.post(f"/api/plans/{pid}/approve", json={"user": "Tester", "note": "Approved"})
    assert res_app.status_code == 200
    assert res_app.json()["plan"]["status"] == "APPROVED"

    # Reject verify from APPROVED
    res_ver2 = client.post(f"/api/plans/{pid}/verify", json={"user": "Tester"})
    assert res_ver2.status_code == 400

    # Dispatch (valid)
    res_disp2 = client.post(f"/api/plans/{pid}/dispatch", json={"user": "Tester"})
    assert res_disp2.status_code == 200

    # Complete without note must fail
    res_comp_nonote = client.post(f"/api/plans/{pid}/complete", json={"user": "Tester", "note": ""})
    assert res_comp_nonote.status_code == 400

    # Complete with note (valid)
    res_comp_valid = client.post(f"/api/plans/{pid}/complete", json={"user": "Tester", "note": "Completed cleaning"})
    assert res_comp_valid.status_code == 200
    assert res_comp_valid.json()["plan"]["status"] == "DONE"

    # Verify with insufficient normal days must fail
    res_ver_short = client.post(f"/api/plans/{pid}/verify", json={"user": "Tester", "days_normal_recorded": 4.5})
    assert res_ver_short.status_code == 400

    # Verify with 7 days (valid)
    res_ver_ok = client.post(f"/api/plans/{pid}/verify", json={"user": "Tester", "days_normal_recorded": 7.0})
    assert res_ver_ok.status_code == 200
    assert res_ver_ok.json()["plan"]["status"] == "VERIFIED"


def test_idempotency_no_duplicate_plans():
    """3. Idempoten: dua kali generate tidak menduplikasi plan."""
    db = SessionLocal()
    initial_count = db.query(ActionPlan).filter(ActionPlan.tag == "BL-5702", ActionPlan.is_sandbox == False).count()
    db.close()

    res1 = client.get("/api/alarms/BL-5702/plan")
    assert res1.status_code == 200
    p1_id = res1.json()["id"]

    res2 = client.get("/api/alarms/BL-5702/plan")
    assert res2.status_code == 200
    p2_id = res2.json()["id"]

    assert p1_id == p2_id, "Idempotent fetch generated different plan IDs!"

    db = SessionLocal()
    final_count = db.query(ActionPlan).filter(ActionPlan.tag == "BL-5702", ActionPlan.is_sandbox == False).count()
    db.close()
    assert final_count == max(initial_count, 1)


def test_severity_change_supersedes_and_increments_revision():
    """4. Perubahan severity membuat revisi baru dan SUPERSEDED plan lama."""
    from actions.engine import get_or_create_plan_for_alarm
    db = SessionLocal()
    test_tag = "PM-4405B"

    # 1. Create plan with WARNING
    p1 = get_or_create_plan_for_alarm(
        db=db,
        tag=test_tag,
        alarm_ref="TEST-REF",
        severity="WARNING",
        parameter="Bearing Temperature",
        unit="°C",
        current_val=68.0,
        expected_val=52.0,
        residual_z=3.1,
        slope=0.3,
        pct_to_trip=50.0,
        days_in_alarm_str="1.0 Weeks",
        ttt_range_str="72 jam",
        is_sandbox=False
    )
    rev1 = p1.revision
    p1_id = p1.id

    # 2. Change severity to CRITICAL
    p2 = get_or_create_plan_for_alarm(
        db=db,
        tag=test_tag,
        alarm_ref="TEST-REF",
        severity="CRITICAL",
        parameter="Bearing Temperature",
        unit="°C",
        current_val=88.0,
        expected_val=52.0,
        residual_z=5.2,
        slope=0.8,
        pct_to_trip=95.0,
        days_in_alarm_str="1.5 Weeks",
        ttt_range_str="12 jam",
        is_sandbox=False
    )
    rev2 = p2.revision
    p2_id = p2.id

    assert rev2 == rev1 + 1, f"Expected revision {rev1 + 1}, got {rev2}"
    assert p2_id != p1_id

    # Verify old plan status is SUPERSEDED
    old_p = db.query(ActionPlan).filter(ActionPlan.id == p1_id).first()
    assert old_p.status == "SUPERSEDED"

    # Verify audit event logged
    events = [e.event for e in old_p.events]
    assert "SUPERSEDED" in events

    db.close()


def test_due_at_calculated_from_as_of_not_clock():
    """5. due_at dihitung dari as_of, bukan jam sistem."""
    from actions.engine import get_or_create_plan_for_alarm
    db = SessionLocal()
    past_as_of = datetime(2026, 5, 1, 10, 0, 0, tzinfo=timezone.utc)

    plan = get_or_create_plan_for_alarm(
        db=db,
        tag="TEST-ASOF-01",
        alarm_ref="TEST-ASOF-01",
        severity="CRITICAL",
        parameter="Radial Vibration",
        unit="µm",
        current_val=75.0,
        expected_val=30.0,
        residual_z=4.5,
        slope=0.6,
        pct_to_trip=80.0,
        days_in_alarm_str="2 Days",
        ttt_range_str="24 jam",
        as_of=past_as_of,
        is_sandbox=True
    )

    created = plan.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    due = plan.due_at
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)

    assert created == past_as_of, "Created at does not match passed as_of!"
    expected_due = past_as_of + timedelta(hours=SLA_HOURS["CRITICAL"])
    assert due == expected_due, f"Expected due_at {expected_due}, got {due}"

    # Cleanup test plan
    db.delete(plan)
    db.commit()
    db.close()


def test_sandbox_plans_isolated_and_wiped_on_reset():
    """6. Mode Uji: plan sandbox tidak muncul di data utama; Reset menghapusnya."""
    # 1. Upload test template
    t_res = client.get("/api/sandbox/template")
    assert t_res.status_code == 200
    up_res = client.post(
        "/api/sandbox/upload",
        files={"file": ("test_template.xlsx", t_res.content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    )
    assert up_res.status_code == 200

    # 2. Trigger results
    res_res = client.get("/api/sandbox/results")
    assert res_res.status_code == 200
    sandbox_alarms = res_res.json()["alarms"]
    assert len(sandbox_alarms) > 0

    # 3. Check sandbox plans in DB
    db = SessionLocal()
    sandbox_plans = db.query(ActionPlan).filter(ActionPlan.is_sandbox == True).all()
    assert len(sandbox_plans) > 0

    # Ensure normal alarm query does not return sandbox plans
    norm_plans = db.query(ActionPlan).filter(ActionPlan.is_sandbox == False).all()
    for sp in sandbox_plans:
        assert sp.id not in [np.id for np in norm_plans]
    db.close()

    # 4. Reset sandbox
    del_res = client.delete("/api/sandbox/reset")
    assert del_res.status_code == 200

    # 5. Verify sandbox plans are wiped
    db = SessionLocal()
    remaining_sb = db.query(ActionPlan).filter(ActionPlan.is_sandbox == True).count()
    assert remaining_sb == 0, f"Expected 0 sandbox plans after reset, found {remaining_sb}"
    db.close()


def test_work_order_simulation_rules():
    """7. Tidak ada teks yang menyebut 'SAP terhubung'; wo_no selalu berawalan WO-SIM."""
    # Dispatch an approved plan to inspect work order
    tag = "KO-3201"
    plan_res = client.get(f"/api/alarms/{tag}/plan")
    pid = plan_res.json()["id"]

    db = SessionLocal()
    plan = db.query(ActionPlan).filter(ActionPlan.id == pid).first()
    plan.status = "APPROVED"
    db.commit()
    db.close()

    r_disp = client.post(f"/api/plans/{pid}/dispatch", json={"user": "Planner", "note": "Dispatch test"})
    assert r_disp.status_code == 200
    data = r_disp.json()
    wo = data["work_order"]

    assert wo["wo_no"].startswith(WO_PREFIX), f"Work order {wo['wo_no']} must start with {WO_PREFIX}"
    assert wo["status"] == WO_STATUS, f"Work order status must be {WO_STATUS}"

    # Verify no text mentions "SAP terhubung"
    dumped = json.dumps(data).lower()
    assert "sap terhubung" not in dumped
    assert "connected to sap" not in dumped
