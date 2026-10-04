from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.database import get_db
from app.models import Incident
from app.schemas import (
    IncidentDetailResponse,
    IncidentKpiSummary,
    DisciplineKpiItem,
    PlantKpiItem,
    StatusKpiItem
)

router = APIRouter(prefix="/api/incidents", tags=["incidents"])

DISCIPLINE_META = {
    "ROT": {"name": "Rotating Equipment", "color": "#2563EB"},
    "INS": {"name": "Instrumentation & Control", "color": "#059669"},
    "STA": {"name": "Static Equipment & Piping", "color": "#D97706"},
    "ELE": {"name": "Electrical Systems", "color": "#8B5CF6"},
}

STATUS_COLORS = {
    "RISK CLOSED": "#059669",
    "CA/PA EXECUTION": "#D97706",
    "RCA PROCESS": "#2563EB",
    "MONITORING RESULT": "#0284C7",
    "NEW REGISTERED": "#E11D48",
    "RISK CANCELED": "#64748B",
}

def compute_incident_kpi_summary(db: Session) -> IncidentKpiSummary:
    total_incidents = db.query(func.count(Incident.id)).scalar() or 0
    historical_count = db.query(func.count(Incident.id)).filter(Incident.is_synthetic == False).scalar() or 0
    synthetic_count = db.query(func.count(Incident.id)).filter(Incident.is_synthetic == True).scalar() or 0

    total_downtime = db.query(func.sum(Incident.downtime_h)).scalar() or 0.0
    total_loss = db.query(func.sum(Incident.act_loss_k_usd)).scalar() or 0.0

    avg_loss = (total_loss / total_incidents) if total_incidents > 0 else 0.0
    avg_downtime = (total_downtime / total_incidents) if total_incidents > 0 else 0.0

    # Discipline Breakdown
    disc_rows = (
        db.query(
            Incident.discipline,
            func.count(Incident.id).label("cnt"),
            func.sum(Incident.act_loss_k_usd).label("loss")
        )
        .group_by(Incident.discipline)
        .order_by(desc("cnt"))
        .all()
    )

    by_discipline = []
    for d, cnt, loss in disc_rows:
        meta = DISCIPLINE_META.get(d, {"name": d, "color": "#64748B"})
        pct_cnt = f"{(cnt / total_incidents * 100):.1f}%" if total_incidents > 0 else "0.0%"
        pct_l = f"{(loss / total_loss * 100):.1f}%" if total_loss > 0 else "0.0%"
        by_discipline.append(
            DisciplineKpiItem(
                discipline=d,
                name=meta["name"],
                count=cnt,
                loss_k_usd=round(loss or 0.0, 1),
                pct_count=pct_cnt,
                pct_loss=pct_l,
                color=meta["color"]
            )
        )

    # Plant Breakdown (Top 10)
    plant_rows = (
        db.query(
            Incident.plant,
            func.count(Incident.id).label("cnt"),
            func.sum(Incident.act_loss_k_usd).label("loss"),
            func.sum(Incident.downtime_h).label("dt")
        )
        .group_by(Incident.plant)
        .order_by(desc("loss"))
        .limit(10)
        .all()
    )

    by_plant = [
        PlantKpiItem(
            plant=p,
            count=cnt,
            loss_k_usd=round(loss or 0.0, 1),
            downtime_h=round(dt or 0.0, 1)
        )
        for p, cnt, loss, dt in plant_rows
    ]

    # Status Breakdown
    status_rows = (
        db.query(
            Incident.status,
            func.count(Incident.id).label("cnt")
        )
        .group_by(Incident.status)
        .order_by(desc("cnt"))
        .all()
    )

    by_status = [
        StatusKpiItem(
            status=s,
            count=cnt,
            pct=f"{(cnt / total_incidents * 100):.1f}%" if total_incidents > 0 else "0.0%",
            color=STATUS_COLORS.get(s, "#64748B")
        )
        for s, cnt in status_rows
    ]

    # Top 5 loss incidents
    top_incidents = (
        db.query(Incident)
        .order_by(desc(Incident.act_loss_k_usd))
        .limit(5)
        .all()
    )
    top_5_res = [IncidentDetailResponse.model_validate(inc) for inc in top_incidents]

    return IncidentKpiSummary(
        total_incidents=total_incidents,
        historical_count=historical_count,
        synthetic_count=synthetic_count,
        total_downtime_h=round(total_downtime, 1),
        total_loss_k_usd=round(total_loss, 1),
        avg_loss_per_incident_k_usd=round(avg_loss, 1),
        avg_downtime_per_incident_h=round(avg_downtime, 1),
        by_discipline=by_discipline,
        by_plant=by_plant,
        by_status=by_status,
        top_5_loss_incidents=top_5_res
    )

@router.get("/kpi", response_model=IncidentKpiSummary)
def get_incident_kpi_summary(db: Session = Depends(get_db)):
    """
    Mengembalikan ringkasan KPI insiden keandalan pabrik:
    Total kejadian, akumulasi downtime, total kerugian finansial,
    distribusi disiplin ilmu, sebaran per plant, dan status penanganan RCA/CAPA.
    """
    return compute_incident_kpi_summary(db)

@router.get("")
def list_incidents(
    plant: Optional[str] = Query(None, description="Filter kode plant"),
    discipline: Optional[str] = Query(None, description="Filter disiplin (ROT, INS, STA, ELE)"),
    status: Optional[str] = Query(None, description="Filter status"),
    is_synthetic: Optional[bool] = Query(None, description="Filter data sintetis vs historis"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    Daftar rekaman insiden dengan dukungan filter multidimensi dan paginasi.
    """
    query = db.query(Incident)

    if plant:
        query = query.filter(Incident.plant == plant.upper())
    if discipline:
        query = query.filter(Incident.discipline == discipline.upper())
    if status:
        query = query.filter(Incident.status == status)
    if is_synthetic is not None:
        query = query.filter(Incident.is_synthetic == is_synthetic)

    total = query.count()
    items = query.order_by(desc(Incident.date_occurred), desc(Incident.id)).offset(offset).limit(limit).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [IncidentDetailResponse.model_validate(item) for item in items]
    }
