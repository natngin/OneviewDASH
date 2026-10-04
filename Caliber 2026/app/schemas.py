from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict

class TelemetryItem(BaseModel):
    param: str
    current: str
    threshold: Optional[str] = None
    status: str

class ImpactInfo(BaseModel):
    downtime: Optional[str] = None
    lossTons: Optional[str] = None
    financialLoss: Optional[str] = None

class CapaInfo(BaseModel):
    immediate: Optional[str] = None
    preventive: Optional[str] = None
    priority: Optional[str] = None
    pic: Optional[str] = None

class IncidentItem(BaseModel):
    date: str
    ar: str
    event: str
    loss: str
    dt: Optional[str] = None
    status: Optional[str] = None

class AlarmResponse(BaseModel):
    tag: str
    namaAset: str
    plant: str
    cls: str
    health: float
    healthStatus: str
    posibleFailure: str
    severity: str
    leadTime: str
    rootCause: str
    telemetry: List[TelemetryItem]
    impact: ImpactInfo
    capa: CapaInfo
    incidents: List[IncidentItem]
    plan_status: Optional[str] = None
    plan_id: Optional[int] = None
    is_overdue: Optional[bool] = None
    hypothesis: Optional[str] = None
    source_ar: Optional[str] = None
    priority_score: Optional[float] = None
    evidence_summary: Optional[str] = None
    ml_diagnostics: Optional[Dict[str, Any]] = None

class EquipmentPerformanceResponse(BaseModel):
    tag: str
    name: str
    plant: str
    cls: str
    category: str
    tripPct: float
    downtime: float
    avail: float
    mtbf: float
    mttr: float
    lossTons: float
    lossK: float
    pmComp: float
    alarmWeeks: int
    status: Optional[str] = None
    monitoredParameter: Optional[str] = None
    currentVal: Optional[str] = None
    tripTelemetry: Optional[str] = None
    threshold: Optional[str] = None
    failDate: Optional[str] = None
    failMechanism: Optional[str] = None
    restoredDate: Optional[str] = None
    daysSinceRestore: Optional[int] = None
    currentStatus: Optional[str] = None
    capaStatus: Optional[str] = None
    capaOwner: Optional[str] = None
    recurrence: int
    timeline: List[str]

class PieItem(BaseModel):
    name: str
    value: float
    color: str
    pct: str

class ExecutiveKpiResponse(BaseModel):
    totalMonitored: int
    criticalCount: int
    warningCount: int
    watchlistCount: int
    activeAlarmCount: int
    tripCount: int
    overdueCount: int
    top5Alarms: List[AlarmResponse]
    fleetAvailability: float
    totalDowntime: float
    totalLoss: float
    pmCompliance: float
    pieStatus: List[PieItem]
    pieLoss: List[PieItem]
    currentEnergyLoad: float
    peakEnergyLoad: float
    incidentSummary: Optional[Any] = None

class IncidentDetailResponse(BaseModel):
    id: int
    serial_no: Optional[int] = None
    mto_no: Optional[str] = None
    ar_no: Optional[str] = None
    plant: str
    tag: Optional[str] = None
    eq_class: Optional[str] = None
    date_occurred: Optional[str] = None
    title: Optional[str] = None
    highest_impact: Optional[str] = None
    pre_risk: Optional[str] = None
    risk_score: Optional[float] = None
    pic_rca: Optional[str] = None
    status: str
    discipline: str
    eq_type: Optional[str] = None
    component: Optional[str] = None
    failure_mechanism: Optional[str] = None
    downtime_h: float
    act_loss_k_usd: float
    pot_loss_k_usd: float
    total_loss_k_usd: float
    rca_due_date: Optional[str] = None
    month_year: Optional[str] = None
    is_synthetic: bool

    model_config = ConfigDict(from_attributes=True)

class DisciplineKpiItem(BaseModel):
    discipline: str
    name: str
    count: int
    loss_k_usd: float
    pct_count: str
    pct_loss: str
    color: str

class PlantKpiItem(BaseModel):
    plant: str
    count: int
    loss_k_usd: float
    downtime_h: float

class StatusKpiItem(BaseModel):
    status: str
    count: int
    pct: str
    color: str

class IncidentKpiSummary(BaseModel):
    total_incidents: int
    historical_count: int
    synthetic_count: int
    total_downtime_h: float
    total_loss_k_usd: float
    avg_loss_per_incident_k_usd: float
    avg_downtime_per_incident_h: float
    by_discipline: List[DisciplineKpiItem]
    by_plant: List[PlantKpiItem]
    by_status: List[StatusKpiItem]
    top_5_loss_incidents: List[IncidentDetailResponse]

