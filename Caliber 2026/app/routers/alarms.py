import json
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc

from app.database import get_db
from app.models import Alarm, AlarmTelemetry, AlarmCapa, AlarmHistory, ActionPlan, ActionLibrary
from app.schemas import AlarmResponse, TelemetryItem, ImpactInfo, CapaInfo, IncidentItem
from actions.engine import get_or_create_plan_for_alarm

router = APIRouter(prefix="/api/alarms", tags=["alarms"])

def format_alarm_dict(al: Alarm, db: Optional[Session] = None) -> dict:
    telemetry_list = [
        {
            "param": t.parameter,
            "current": t.nilai,
            "threshold": t.threshold_raw,
            "status": t.status
        }
        for t in al.telemetry
    ]

    immediate_capa = next((c.teks for c in al.capa if c.tipe == "immediate"), None)
    preventive_capa = next((c.teks for c in al.capa if c.tipe == "preventive"), None)
    first_capa = al.capa[0] if al.capa else None
    priority = first_capa.prioritas if first_capa else "High"
    pic = first_capa.pic if first_capa else "Unassigned"

    capa_info = {
        "immediate": immediate_capa,
        "preventive": preventive_capa,
        "priority": priority,
        "pic": pic
    }

    incidents_list = [
        {
            "date": h.tanggal,
            "ar": h.ar_no,
            "event": h.deskripsi,
            "loss": h.kerugian,
            "dt": h.downtime,
            "status": h.status
        }
        for h in al.history
    ]

    # Resolve Action Plan
    plan_status = "DRAFT"
    plan_id = None
    is_overdue = False
    hypothesis = None
    source_ar = None
    possible_failure_summary = al.possible_failure

    if db is not None:
        plan = db.query(ActionPlan).filter(
            ActionPlan.tag == al.tag,
            ActionPlan.is_sandbox == False,
            ActionPlan.status.in_(["DRAFT", "APPROVED", "DISPATCHED", "DONE", "VERIFIED"])
        ).order_by(desc(ActionPlan.revision)).first()

        if not plan:
            # Auto create initial plan
            primary_param = al.telemetry[0].parameter if al.telemetry else "Radial Vibration"
            unit = al.telemetry[0].unit if (al.telemetry and al.telemetry[0].unit) else "µm"
            try:
                curr_v = float(str(al.telemetry[0].nilai).split()[0]) if al.telemetry else 40.0
            except Exception:
                curr_v = 40.0

            plan = get_or_create_plan_for_alarm(
                db=db,
                tag=al.tag,
                alarm_ref=str(al.id),
                severity=al.severity or "WARNING",
                parameter=primary_param,
                unit=unit,
                current_val=curr_v,
                expected_val=curr_v * 0.7,
                residual_z=3.2,
                slope=0.45,
                pct_to_trip=65.0,
                days_in_alarm_str=al.lead_time_weeks or "2 Weeks",
                ttt_range_str="48-72 jam",
                plant=al.plant or "PLANT-01",
                is_sandbox=False
            )

        if plan:
            plan_status = plan.status
            plan_id = plan.id
            now_utc = datetime.now(timezone.utc)
            due_utc = plan.due_at if plan.due_at.tzinfo else plan.due_at.replace(tzinfo=timezone.utc)
            is_overdue = (now_utc > due_utc) and (plan.status in ("DRAFT", "APPROVED", "DISPATCHED"))
            if plan.library:
                hypothesis = plan.library.hypothesis
                source_ar = plan.library.source_ar
            try:
                ev_data = json.loads(plan.evidence_json)
                if "summary" in ev_data:
                    possible_failure_summary = ev_data["summary"]
            except Exception:
                pass

    return {
        "tag": al.tag,
        "namaAset": al.nama_aset,
        "plant": al.plant,
        "cls": al.cls,
        "health": float(al.health_pct),
        "healthStatus": al.health_status,
        "posibleFailure": al.possible_failure,
        "severity": al.severity,
        "leadTime": al.lead_time_weeks,
        "rootCause": al.root_cause,
        "telemetry": telemetry_list,
        "impact": {
            "downtime": al.impact_downtime,
            "lossTons": al.impact_loss_tons,
            "financialLoss": al.impact_financial_loss
        },
        "capa": capa_info,
        "incidents": incidents_list,
        "plan_status": plan_status,
        "plan_id": plan_id,
        "is_overdue": is_overdue,
        "hypothesis": hypothesis,
        "source_ar": source_ar,
        "evidence_summary": possible_failure_summary,
        "priority_score": 1000.0 if al.severity == "CRITICAL" else (500.0 if al.severity == "WARNING" else 200.0)
    }

@router.get("", response_model=List[AlarmResponse])
def get_alarms(
    severity: Optional[str] = Query(None, description="Filter by severity: CRITICAL, WARNING, WATCHLIST"),
    plant: Optional[str] = Query(None, description="Filter by plant code"),
    q: Optional[str] = Query(None, description="Search term for tag, name, or failure"),
    db: Session = Depends(get_db)
):
    query = db.query(Alarm)

    if severity:
        query = query.filter(Alarm.severity.ilike(severity))
    if plant:
        query = query.filter(Alarm.plant.ilike(plant))
    if q:
        search_filter = or_(
            Alarm.tag.ilike(f"%{q}%"),
            Alarm.nama_aset.ilike(f"%{q}%"),
            Alarm.possible_failure.ilike(f"%{q}%"),
            Alarm.root_cause.ilike(f"%{q}%")
        )
        query = query.filter(search_filter)

    alarms = query.all()
    # Order: severity (CRITICAL > WARNING > WATCHLIST > NORMAL) then health ascending
    sev_rank = {"CRITICAL": 0, "WARNING": 1, "WATCHLIST": 2, "NORMAL": 3}
    alarms.sort(key=lambda a: (sev_rank.get(a.severity.upper() if a.severity else "", 4), a.health_pct))

    return [format_alarm_dict(al, db) for al in alarms]

@router.get("/{alarm_id_or_tag}", response_model=AlarmResponse)
def get_alarm_by_id_or_tag(alarm_id_or_tag: str, db: Session = Depends(get_db)):
    alarm = None
    if alarm_id_or_tag.isdigit():
        alarm = db.query(Alarm).filter(Alarm.id == int(alarm_id_or_tag)).first()
    if not alarm:
        alarm = db.query(Alarm).filter(Alarm.tag == alarm_id_or_tag).first()

    if not alarm:
        raise HTTPException(status_code=404, detail="Alarm record not found")

    return format_alarm_dict(alarm, db)

