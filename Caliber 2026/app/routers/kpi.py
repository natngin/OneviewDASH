from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import Alarm, AlarmCapa, FleetStatus, EquipmentEvent, EnergyReading
from app.routers.alarms import format_alarm_dict
from app.schemas import ExecutiveKpiResponse, PieItem

router = APIRouter(prefix="/api/kpi", tags=["kpi"])

@router.get("/executive", response_model=ExecutiveKpiResponse)
def get_executive_kpi(db: Session = Depends(get_db)):
    # 1. Alarms calculations directly from alarms table
    all_alarms = db.query(Alarm).order_by(Alarm.health_pct.asc()).all()
    total_monitored = len(all_alarms)

    critical_count = sum(1 for a in all_alarms if a.severity == "CRITICAL")
    warning_count = sum(1 for a in all_alarms if a.severity == "WARNING")
    watchlist_count = sum(1 for a in all_alarms if a.severity == "WATCHLIST")
    active_alarm_count = critical_count + warning_count

    # Trip: health < 40 or health_status contains 'critical'
    trip_count = sum(
        1 for a in all_alarms
        if a.health_pct < 40 or "critical" in (a.health_status or "").lower()
    )

    # Overdue CAPA count
    overdue_count = 0
    for a in all_alarms:
        has_overdue_inc = any("overdue" in (h.status or "").lower() for h in a.history)
        has_overdue_capa = any("overdue" in (c.prioritas or "").lower() for c in a.capa)
        if has_overdue_inc or has_overdue_capa:
            overdue_count += 1

    top5_alarms = [format_alarm_dict(a) for a in all_alarms[:5]]

    # 2. Fleet status from fleet_status table
    fleet_rows = db.query(FleetStatus).all()
    pie_status = [
        PieItem(
            name=f.status,
            value=float(f.jumlah),
            color=f.color,
            pct=f.pct
        )
        for f in fleet_rows
    ]

    # 3. Equipment summary from equipment_events
    events = db.query(EquipmentEvent).all()
    if events:
        fleet_avail = round(sum(e.avail_pct for e in events) / len(events), 2)
        total_dt = round(sum(e.downtime_h for e in events), 1)
        total_loss = round(sum(e.kerugian_k_usd for e in events), 1)
        pm_comp = round(sum(e.pm_compliance_pct for e in events) / len(events), 1)
    else:
        fleet_avail = 99.64
        total_dt = 74.0
        total_loss = 2693.1
        pm_comp = 92.5

    # 4. Pie Loss
    loss_events = (
        db.query(EquipmentEvent)
        .order_by(EquipmentEvent.kerugian_k_usd.desc())
        .limit(5)
        .all()
    )
    total_top_loss = sum(e.kerugian_k_usd for e in loss_events) or 1.0
    colors = ["#E11D48", "#D97706", "#0284C7", "#8B5CF6", "#059669"]

    pie_loss = []
    for idx, e in enumerate(loss_events):
        pct_val = f"{(e.kerugian_k_usd / total_top_loss * 100):.1f}%"
        pie_loss.append(
            PieItem(
                name=f"{e.tag} ({e.asset.nama if e.asset else ''})",
                value=e.kerugian_k_usd,
                color=colors[idx % len(colors)],
                pct=pct_val
            )
        )

    # 5. Energy readings
    latest_24h = (
        db.query(EnergyReading)
        .filter(EnergyReading.series_type == "24h")
        .order_by(EnergyReading.id.desc())
        .first()
    )
    current_energy_load = latest_24h.actual_kwh if latest_24h else 14400.0

    peak_reading = (
        db.query(func.max(EnergyReading.actual_kwh))
        .filter(EnergyReading.series_type == "24h")
        .scalar()
    )
    peak_energy_load = peak_reading if peak_reading else 15100.0

    return ExecutiveKpiResponse(
        totalMonitored=total_monitored,
        criticalCount=critical_count,
        warningCount=warning_count,
        watchlistCount=watchlist_count,
        activeAlarmCount=active_alarm_count,
        tripCount=trip_count,
        overdueCount=overdue_count,
        top5Alarms=top5_alarms,
        fleetAvailability=fleet_avail,
        totalDowntime=total_dt,
        totalLoss=total_loss,
        pmCompliance=pm_comp,
        pieStatus=pie_status,
        pieLoss=pie_loss,
        currentEnergyLoad=current_energy_load,
        peakEnergyLoad=peak_energy_load
    )
