"""
API Router for Action Recommendation (CAPA) Workflow.
Complies with Stage 2C requirements:
- Deterministic action library
- Strict state transitions
- Audit logging
- Work Order simulation
- Roster & SLA labels
"""
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models import ActionPlan, ActionItem, ActionEvent, WorkOrder, ActionLibrary, Alarm, SensorReading
from actions.config import SLA_HOURS, SLA_LABELS, LABEL_SLA, LABEL_ROSTER, VERIFICATION_NORMAL_DAYS, WO_PREFIX, WO_STATUS
from actions.engine import (
    get_or_create_plan_for_alarm,
    approve_action_plan,
    toggle_action_item,
    dispatch_action_plan,
    complete_action_plan,
    verify_action_plan,
    calculate_action_kpis
)

router = APIRouter(prefix="/api", tags=["actions"])


def format_plan_response(plan: ActionPlan, as_of_dt: Optional[datetime] = None) -> Dict[str, Any]:
    now_dt = as_of_dt or datetime.now(timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)

    due = plan.due_at
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)

    is_overdue = (now_dt > due) and (plan.status in ("DRAFT", "APPROVED", "DISPATCHED"))
    remaining_h = round((due - now_dt).total_seconds() / 3600.0, 1)

    try:
        evidence_dict = json.loads(plan.evidence_json)
    except Exception:
        evidence_dict = {"summary": "Telemetry evidence not available"}

    items_list = [
        {
            "id": it.id,
            "tipe": it.tipe,
            "teks": it.teks,
            "owner_role": it.owner_role,
            "owner_name": it.owner_name or LABEL_ROSTER,
            "done": it.done,
            "done_at": it.done_at.isoformat() if it.done_at else None
        }
        for it in plan.items
    ]

    events_list = [
        {
            "id": ev.id,
            "ts": ev.ts.isoformat() if ev.ts else None,
            "user": ev.user,
            "event": ev.event,
            "from_status": ev.from_status,
            "to_status": ev.to_status,
            "note": ev.note
        }
        for ev in plan.events
    ]

    wos = [
        {
            "id": wo.id,
            "wo_no": wo.wo_no,
            "status": wo.status,
            "created_at": wo.created_at.isoformat() if wo.created_at else None
        }
        for wo in plan.work_orders
    ]

    lib = plan.library
    lib_dict = {
        "id": lib.id if lib else "LIB-FALLBACK",
        "title": lib.title if lib else "Langkah Triase Umum",
        "hypothesis": lib.hypothesis if lib else "Pustaka tindakan belum memuat parameter ini; perlu dilengkapi",
        "source_ar": lib.source_ar if lib else "AR-FALLBACK-0000",
        "source_note": lib.source_note if lib else "",
        "owner_role": lib.owner_role if lib else "REL",
        "is_fallback": (lib.id == "LIB-FALLBACK") if lib else True
    }

    return {
        "id": plan.id,
        "alarm_ref": plan.alarm_ref,
        "tag": plan.tag,
        "severity": plan.severity_at_creation,
        "revision": plan.revision,
        "status": plan.status,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "due_at": plan.due_at.isoformat() if plan.due_at else None,
        "sla_hours": plan.sla_hours,
        "sla_label": SLA_LABELS.get(plan.severity_at_creation, f"{plan.sla_hours:.0f} Jam ({LABEL_SLA})"),
        "is_overdue": is_overdue,
        "remaining_hours": remaining_h,
        "library_id": plan.library_id,
        "library": lib_dict,
        "evidence": evidence_dict,
        "items": items_list,
        "events": events_list,
        "work_orders": wos,
        "latest_work_order": wos[-1]["wo_no"] if wos else None,
        "roster_label": LABEL_ROSTER,
        "sla_tag": LABEL_SLA
    }


# ---------------------------------------------------------------------------
# GET /api/alarms/{id_or_tag}/plan
# ---------------------------------------------------------------------------
@router.get("/alarms/{id_or_tag}/plan")
def get_alarm_plan(
    id_or_tag: str,
    as_of: Optional[str] = Query(None, description="ISO timestamp for as_of reference"),
    is_sandbox: Optional[bool] = Query(False, description="Filter sandbox plans"),
    db: Session = Depends(get_db)
):
    # Resolve tag
    tag = id_or_tag
    alarm = None
    if id_or_tag.isdigit():
        alarm = db.query(Alarm).filter(Alarm.id == int(id_or_tag)).first()
        if alarm:
            tag = alarm.tag
    if not alarm:
        alarm = db.query(Alarm).filter(Alarm.tag == tag).first()

    as_of_dt = None
    if as_of:
        try:
            as_of_dt = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        except Exception:
            as_of_dt = None

    # Find active plan for this tag and environment
    plan = db.query(ActionPlan).filter(
        ActionPlan.tag == tag,
        ActionPlan.is_sandbox == bool(is_sandbox),
        ActionPlan.status.in_(["DRAFT", "APPROVED", "DISPATCHED", "DONE"])
    ).order_by(desc(ActionPlan.revision)).first()

    # If no active plan, check latest plan (e.g. VERIFIED)
    if not plan:
        plan = db.query(ActionPlan).filter(
            ActionPlan.tag == tag,
            ActionPlan.is_sandbox == bool(is_sandbox)
        ).order_by(desc(ActionPlan.revision)).first()

    # If still no plan exists, auto-generate one if alarm exists
    if not plan and alarm:
        # Determine parameter and telemetry
        primary_param = "Radial Vibration"
        unit = "µm"
        curr_val = 40.0
        exp_val = 25.0
        curr_z = 3.5
        slope = 0.5
        pct_to_trip = 65.0
        if alarm.telemetry:
            t = alarm.telemetry[0]
            primary_param = t.parameter
            unit = t.unit or "µm"
            try:
                curr_val = float(str(t.nilai).split()[0])
            except Exception:
                curr_val = 50.0

        plan = get_or_create_plan_for_alarm(
            db=db,
            tag=tag,
            alarm_ref=str(alarm.id),
            severity=alarm.severity or "WARNING",
            parameter=primary_param,
            unit=unit,
            current_val=curr_val,
            expected_val=exp_val,
            residual_z=curr_z,
            slope=slope,
            pct_to_trip=pct_to_trip,
            days_in_alarm_str=alarm.lead_time_weeks or "2 Weeks",
            ttt_range_str="48-72 jam",
            plant=alarm.plant or "PLANT-01",
            as_of=as_of_dt,
            is_sandbox=bool(is_sandbox)
        )

    if not plan:
        # Fallback empty plan response or 404
        raise HTTPException(status_code=404, detail=f"Tidak ada rencana tindakan untuk aset {tag}")

    return format_plan_response(plan, as_of_dt)


# ---------------------------------------------------------------------------
# POST /api/plans/{id}/approve
# ---------------------------------------------------------------------------
@router.post("/plans/{id}/approve")
def approve_plan_endpoint(
    id: int,
    body: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db)
):
    user = body.get("user", "User Operator")
    note = body.get("note", "Persetujuan Rencana Tindakan")
    edited_items = body.get("items")
    try:
        plan = approve_action_plan(db, plan_id=id, user=user, note=note, edited_items=edited_items)
        return {"status": "success", "plan": format_plan_response(plan)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# POST /api/plans/{id}/items/{iid}/toggle
# ---------------------------------------------------------------------------
@router.post("/plans/{id}/items/{iid}/toggle")
def toggle_item_endpoint(
    id: int,
    iid: int,
    body: Dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db)
):
    user = body.get("user", "Field Operator")
    try:
        item = toggle_action_item(db, plan_id=id, item_id=iid, user=user)
        plan = db.query(ActionPlan).filter(ActionPlan.id == id).first()
        return {
            "status": "success",
            "item": {
                "id": item.id,
                "done": item.done,
                "done_at": item.done_at.isoformat() if item.done_at else None
            },
            "plan": format_plan_response(plan)
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# POST /api/plans/{id}/dispatch
# ---------------------------------------------------------------------------
@router.post("/plans/{id}/dispatch")
def dispatch_plan_endpoint(
    id: int,
    body: Dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db)
):
    user = body.get("user", "Maintenance Lead")
    note = body.get("note", "")
    try:
        plan, wo = dispatch_action_plan(db, plan_id=id, user=user, note=note)
        return {
            "status": "success",
            "message": f"Simulated Work Order {wo.wo_no} successfully generated.",
            "work_order": {
                "id": wo.id,
                "wo_no": wo.wo_no,
                "status": wo.status,
                "created_at": wo.created_at.isoformat()
            },
            "plan": format_plan_response(plan)
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# POST /api/plans/{id}/complete
# ---------------------------------------------------------------------------
@router.post("/plans/{id}/complete")
def complete_plan_endpoint(
    id: int,
    body: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db)
):
    user = body.get("user", "Maintenance Lead")
    note = body.get("note", "")
    try:
        plan = complete_action_plan(db, plan_id=id, user=user, note=note)
        return {"status": "success", "plan": format_plan_response(plan)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# POST /api/plans/{id}/verify
# ---------------------------------------------------------------------------
@router.post("/plans/{id}/verify")
def verify_plan_endpoint(
    id: int,
    body: Dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db)
):
    user = body.get("user", "Reliability Manager")
    note = body.get("note", "")
    days_normal = float(body.get("days_normal_recorded", 7.0))
    try:
        plan = verify_action_plan(db, plan_id=id, user=user, note=note, days_normal_recorded=days_normal)
        return {"status": "success", "plan": format_plan_response(plan)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# GET /api/actions/kpi
# ---------------------------------------------------------------------------
@router.get("/actions/kpi")
def get_actions_kpi_endpoint(
    as_of: Optional[str] = Query(None),
    is_sandbox: Optional[bool] = Query(False),
    db: Session = Depends(get_db)
):
    as_of_dt = None
    if as_of:
        try:
            as_of_dt = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        except Exception:
            as_of_dt = None

    kpis = calculate_action_kpis(db, as_of=as_of_dt, is_sandbox=bool(is_sandbox))
    return kpis
