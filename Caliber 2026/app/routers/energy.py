from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import EnergyReading

router = APIRouter(prefix="/api/energy", tags=["energy"])

def format_24h(r: EnergyReading) -> dict:
    return {
        "t": r.time_slot,
        "actual": r.actual_kwh,
        "limit": r.limit_kwh
    }

def format_30d(r: EnergyReading) -> dict:
    return {
        "day": r.day_id,
        "date": r.date_label,
        "totalMwh": r.total_mwh,
        "peakKwh": int(r.peak_kwh) if r.peak_kwh is not None else 0,
        "limit": int(r.limit_kwh) if r.limit_kwh is not None else 16200,
        "intensity": r.intensity,
        "cost": r.cost_usd,
        "co2e": r.co2e_tons,
        "compressors": r.compressors_mwh,
        "pumps": r.pumps_mwh,
        "blowers": r.blowers_mwh,
        "auxiliary": r.auxiliary_mwh,
        "isAlert": r.is_alert
    }

@router.get("")
def get_energy_data(days: int = Query(30, description="Days of energy history"), db: Session = Depends(get_db)):
    readings_24h = (
        db.query(EnergyReading)
        .filter(EnergyReading.series_type == "24h")
        .order_by(EnergyReading.id.asc())
        .all()
    )
    readings_30d = (
        db.query(EnergyReading)
        .filter(EnergyReading.series_type == "30d")
        .order_by(EnergyReading.id.asc())
        .limit(days)
        .all()
    )
    return {
        "load24h": [format_24h(r) for r in readings_24h],
        "days30": [format_30d(r) for r in readings_30d]
    }

@router.get("/24h")
def get_energy_24h(db: Session = Depends(get_db)):
    readings = (
        db.query(EnergyReading)
        .filter(EnergyReading.series_type == "24h")
        .order_by(EnergyReading.id.asc())
        .all()
    )
    return [format_24h(r) for r in readings]

@router.get("/30d")
def get_energy_30d(days: int = Query(30), db: Session = Depends(get_db)):
    readings = (
        db.query(EnergyReading)
        .filter(EnergyReading.series_type == "30d")
        .order_by(EnergyReading.id.asc())
        .limit(days)
        .all()
    )
    return [format_30d(r) for r in readings]
