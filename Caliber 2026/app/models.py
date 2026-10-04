from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Text, Boolean, DateTime, ForeignKey
)
from sqlalchemy.orm import relationship
from .database import Base

def utc_now():
    return datetime.now(timezone.utc)

class Asset(Base):
    __tablename__ = "assets"

    tag = Column(String(50), primary_key=True, index=True)
    nama = Column(String(200), nullable=False)
    plant = Column(String(50), nullable=False, index=True)
    kelas = Column(String(50), nullable=False)
    tipe = Column(String(100), nullable=True)
    komponen = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    # Relationships
    events = relationship("EquipmentEvent", back_populates="asset", cascade="all, delete-orphan")
    condition_strips = relationship("ConditionWeekly", back_populates="asset", cascade="all, delete-orphan")
    alarms = relationship("Alarm", back_populates="asset", cascade="all, delete-orphan")


class EquipmentEvent(Base):
    __tablename__ = "equipment_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tag = Column(String(50), ForeignKey("assets.tag"), nullable=False, index=True)
    tanggal_gagal = Column(String(50), nullable=True)         # // DUMMY: breakdown date
    mekanisme = Column(Text, nullable=True)                    # // DUMMY: failure mechanism
    downtime_h = Column(Float, nullable=False, default=0.0)
    mttr_h = Column(Float, nullable=False, default=0.0)
    kerugian_k_usd = Column(Float, nullable=False, default=0.0)
    kerugian_ton = Column(Float, nullable=False, default=0.0)
    avail_pct = Column(Float, nullable=False, default=100.0)
    reliability_h = Column(Float, nullable=False, default=4320.0)
    pm_compliance_pct = Column(Float, nullable=False, default=100.0)
    telemetri_text = Column(Text, nullable=True)               # // DUMMY: trip telemetry
    limit_text = Column(Text, nullable=True)                   # // DUMMY: alert/trip threshold
    monitored_param = Column(Text, nullable=True)
    current_val = Column(Text, nullable=True)                  # // DUMMY: post-repair telemetry
    trip_pct = Column(Float, nullable=False, default=0.0)
    restored_date = Column(String(50), nullable=True)          # // DUMMY: restoration date
    days_since_restore = Column(Integer, nullable=True, default=0) # // DUMMY: days restored
    current_status = Column(String(50), nullable=True)         # // DUMMY: 'RESTORED' | 'TIGHT MONITORING'
    capa_status = Column(String(50), nullable=True)            # // DUMMY: 'COMPLETED-VERIFIED' | 'COMPLETED' | 'PENDING'
    capa_owner = Column(String(100), nullable=True)            # // DUMMY: CAPA owner
    recurrence = Column(Integer, nullable=False, default=0)    # // DUMMY: post-restore recurrence
    alarm_weeks = Column(Integer, nullable=False, default=0)
    status = Column(String(100), nullable=True)
    category = Column(String(50), nullable=False, default="monitored") # 'rca' | 'monitored'
    created_at = Column(DateTime, default=utc_now, nullable=False)

    asset = relationship("Asset", back_populates="events")


class ConditionWeekly(Base):
    __tablename__ = "condition_weekly"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tag = Column(String(50), ForeignKey("assets.tag"), nullable=False, index=True)
    week_number = Column(Integer, nullable=False)              # 1 through 26
    status = Column(String(1), nullable=False)                 # 'N' | 'A' | 'T'
    created_at = Column(DateTime, default=utc_now, nullable=False)

    asset = relationship("Asset", back_populates="condition_strips")


class Alarm(Base):
    __tablename__ = "alarms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tag = Column(String(50), ForeignKey("assets.tag"), nullable=False, index=True)
    nama_aset = Column(String(200), nullable=False)
    plant = Column(String(50), nullable=False, index=True)
    cls = Column(String(100), nullable=False)
    severity = Column(String(50), nullable=False, index=True)  # 'CRITICAL' | 'WARNING' | 'WATCHLIST'
    health_pct = Column(Integer, nullable=False, index=True)   # Health percentage (lowest first)
    health_status = Column(String(100), nullable=False)
    possible_failure = Column(Text, nullable=False)
    lead_time_weeks = Column(String(100), nullable=False)
    root_cause = Column(Text, nullable=False)
    impact_downtime = Column(String(100), nullable=True)
    impact_loss_tons = Column(String(100), nullable=True)
    impact_financial_loss = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    asset = relationship("Asset", back_populates="alarms")
    telemetry = relationship("AlarmTelemetry", back_populates="alarm", cascade="all, delete-orphan")
    capa = relationship("AlarmCapa", back_populates="alarm", cascade="all, delete-orphan")
    history = relationship("AlarmHistory", back_populates="alarm", cascade="all, delete-orphan")


class AlarmTelemetry(Base):
    __tablename__ = "alarm_telemetry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alarm_id = Column(Integer, ForeignKey("alarms.id"), nullable=False, index=True)
    parameter = Column(String(150), nullable=False)
    nilai = Column(String(100), nullable=False)
    normal = Column(String(100), nullable=True)
    alert = Column(String(100), nullable=True)
    trip = Column(String(100), nullable=True)
    unit = Column(String(50), nullable=True)
    threshold_raw = Column(String(200), nullable=True)
    status = Column(String(50), nullable=False)                # 'CRITICAL', 'DANGER', etc.
    created_at = Column(DateTime, default=utc_now, nullable=False)

    alarm = relationship("Alarm", back_populates="telemetry")


class AlarmCapa(Base):
    __tablename__ = "alarm_capa"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alarm_id = Column(Integer, ForeignKey("alarms.id"), nullable=False, index=True)
    tipe = Column(String(50), nullable=False)                  # 'immediate' | 'preventive'
    teks = Column(Text, nullable=False)
    pic = Column(String(150), nullable=False)
    prioritas = Column(String(100), nullable=False)
    status = Column(String(50), nullable=True, default="Open")
    created_at = Column(DateTime, default=utc_now, nullable=False)

    alarm = relationship("Alarm", back_populates="capa")


class AlarmHistory(Base):
    __tablename__ = "alarm_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alarm_id = Column(Integer, ForeignKey("alarms.id"), nullable=False, index=True)
    tanggal = Column(String(50), nullable=False)
    ar_no = Column(String(100), nullable=False)
    deskripsi = Column(Text, nullable=False)
    kerugian = Column(String(100), nullable=False)
    downtime = Column(String(100), nullable=True)
    status = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    alarm = relationship("Alarm", back_populates="history")


class FleetStatus(Base):
    __tablename__ = "fleet_status"

    id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(String(50), nullable=False)                # 'NORMAL' | 'ALARM' | 'TRIP'
    jumlah = Column(Integer, nullable=False)                   # // DUMMY: seed dummy count
    pct = Column(String(20), nullable=False)                   # // DUMMY: seed percentage
    color = Column(String(20), nullable=False)                 # // DUMMY: hex color
    created_at = Column(DateTime, default=utc_now, nullable=False)


class EnergyReading(Base):
    __tablename__ = "energy_readings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, nullable=False, index=True)          # ISO-8601 UTC
    series_type = Column(String(20), nullable=False, index=True) # '24h' | '30d'
    time_slot = Column(String(20), nullable=True)              # '00:00', '02:00', etc.
    day_id = Column(String(20), nullable=True)                 # 'D1', 'D2', etc.
    date_label = Column(String(50), nullable=True)             # 'Sep 2', 'Sep 3', etc.
    actual_kwh = Column(Float, nullable=True)
    limit_kwh = Column(Float, nullable=True)
    total_mwh = Column(Float, nullable=True)
    peak_kwh = Column(Float, nullable=True)
    intensity = Column(Float, nullable=True)
    cost_usd = Column(Float, nullable=True)
    co2e_tons = Column(Float, nullable=True)
    compressors_mwh = Column(Float, nullable=True)
    pumps_mwh = Column(Float, nullable=True)
    blowers_mwh = Column(Float, nullable=True)
    auxiliary_mwh = Column(Float, nullable=True)
    is_alert = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class ConditionHourly(Base):
    __tablename__ = "condition_hourly"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    tag = Column(String(50), ForeignKey("assets.tag"), nullable=False, index=True)
    plant = Column(String(50), nullable=False)
    parameter_name = Column(String(100), nullable=False)
    parameter_value = Column(Float, nullable=False)
    unit = Column(String(20), nullable=False)
    load_rate_ton_hr = Column(Float, nullable=True)
    motor_current_amp = Column(Float, nullable=True)
    power_kw = Column(Float, nullable=True)
    run_status = Column(String(20), nullable=False, default="ON")
    is_interpolated = Column(Boolean, nullable=False, default=False)
    source_resolution = Column(String(20), nullable=False, default="hourly")
    created_at = Column(DateTime, default=utc_now, nullable=False)

    asset = relationship("Asset")

class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    serial_no = Column(Integer, nullable=True)
    mto_no = Column(String(100), nullable=True)
    ar_no = Column(String(100), nullable=True, index=True)
    plant = Column(String(50), nullable=False, index=True)
    tag = Column(String(50), nullable=True, index=True)
    eq_class = Column(String(20), nullable=True)
    date_occurred = Column(String(50), nullable=True, index=True)
    title = Column(Text, nullable=True)
    highest_impact = Column(String(100), nullable=True)
    pre_risk = Column(String(20), nullable=True)
    risk_score = Column(Float, nullable=True)
    pic_rca = Column(String(150), nullable=True)
    status = Column(String(100), nullable=False, index=True)  # 'RISK CLOSED', 'CA/PA EXECUTION', 'RCA PROCESS', etc.
    discipline = Column(String(50), nullable=False, index=True)  # 'ROT', 'STA', 'INS', 'ELE'
    eq_type = Column(String(50), nullable=True, index=True)
    component = Column(String(100), nullable=True)
    failure_mechanism = Column(Text, nullable=True)
    downtime_h = Column(Float, nullable=False, default=0.0)
    act_loss_k_usd = Column(Float, nullable=False, default=0.0)
    pot_loss_k_usd = Column(Float, nullable=False, default=0.0)
    total_loss_k_usd = Column(Float, nullable=False, default=0.0)
    rca_due_date = Column(String(50), nullable=True)
    month_year = Column(String(50), nullable=True, index=True)
    is_synthetic = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class SensorReading(Base):
    """Data sensor 'kondisi terkini' multi-parameter (DUMMY) untuk Alarm Board ML.
    Terpisah dari condition_hourly agar backtest Tahap 2B tidak berubah."""
    __tablename__ = "sensor_readings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    tag = Column(String(50), nullable=False, index=True)
    parameter = Column(String(100), nullable=False, index=True)  # key di sensor_thresholds.json
    value = Column(Float, nullable=False)
    unit = Column(String(20), nullable=False)
    load_rate = Column(Float, nullable=True)
    is_dummy = Column(Boolean, nullable=False, default=True)
    scenario_note = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)


# ===========================================================================
# TAHAP 2C: Action Recommendation (CAPA) Models
# ===========================================================================

class ActionLibrary(Base):
    """Pustaka tindakan terverifikasi dengan sumber AR definitif."""
    __tablename__ = "action_library"

    id = Column(String(50), primary_key=True)
    parameter = Column(String(100), nullable=False, index=True)
    pattern = Column(String(100), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    hypothesis = Column(Text, nullable=False)
    diagnostics_json = Column(Text, nullable=False)   # JSON list of strings
    immediate_json = Column(Text, nullable=False)     # JSON list of strings
    preventive_json = Column(Text, nullable=False)    # JSON list of strings
    owner_role = Column(String(50), nullable=False)   # 'REL, STA', 'ROT, REL', etc.
    source_ar = Column(String(50), nullable=False)    # 'AR-2026-ZCU-0142', etc.
    source_note = Column(Text, nullable=True)
    version = Column(String(20), nullable=False, default="1.0")
    created_at = Column(DateTime, default=utc_now, nullable=False)


class ActionPlan(Base):
    """Rencana tindakan per alarm aktif (DRAFT -> APPROVED -> DISPATCHED -> DONE -> VERIFIED)."""
    __tablename__ = "action_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alarm_ref = Column(String(100), nullable=False, index=True)
    tag = Column(String(50), nullable=False, index=True)
    severity_at_creation = Column(String(50), nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    status = Column(String(50), nullable=False, default="DRAFT", index=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    due_at = Column(DateTime, nullable=False)
    sla_hours = Column(Float, nullable=False)
    library_id = Column(String(50), ForeignKey("action_library.id"), nullable=False, index=True)
    evidence_json = Column(Text, nullable=False)      # JSON evidence payload
    is_sandbox = Column(Boolean, nullable=False, default=False, index=True)

    library = relationship("ActionLibrary")
    items = relationship("ActionItem", back_populates="plan", cascade="all, delete-orphan", order_by="ActionItem.id")
    events = relationship("ActionEvent", back_populates="plan", cascade="all, delete-orphan", order_by="ActionEvent.id")
    work_orders = relationship("WorkOrder", back_populates="plan", cascade="all, delete-orphan")


class ActionItem(Base):
    """Item tindakan individual (diagnostik, segera, pencegahan)."""
    __tablename__ = "action_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(Integer, ForeignKey("action_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    tipe = Column(String(20), nullable=False)         # 'diagnostic' | 'immediate' | 'preventive'
    teks = Column(Text, nullable=False)
    owner_role = Column(String(50), nullable=True)
    owner_name = Column(String(100), nullable=True)
    done = Column(Boolean, nullable=False, default=False)
    done_at = Column(DateTime, nullable=True)

    plan = relationship("ActionPlan", back_populates="items")


class ActionEvent(Base):
    """Jejak audit append-only untuk setiap perubahan status/aksi."""
    __tablename__ = "action_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(Integer, ForeignKey("action_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    ts = Column(DateTime, default=utc_now, nullable=False)
    user = Column(String(100), nullable=False)
    event = Column(String(50), nullable=False)
    from_status = Column(String(50), nullable=True)
    to_status = Column(String(50), nullable=True)
    note = Column(Text, nullable=True)

    plan = relationship("ActionPlan", back_populates="events")


class WorkOrder(Base):
    """Work Order simulasi (SAP PM terhubung adalah SIMULASI)."""
    __tablename__ = "work_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(Integer, ForeignKey("action_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    wo_no = Column(String(50), nullable=False, unique=True, index=True) # WO-SIM-000001
    status = Column(String(50), nullable=False, default="SIMULASI")
    created_at = Column(DateTime, default=utc_now, nullable=False)

    plan = relationship("ActionPlan", back_populates="work_orders")


class Roster(Base):
    """Data roster dummy PIC pemeliharaan per plant dan disiplin."""
    __tablename__ = "roster"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plant = Column(String(50), nullable=False, index=True)
    role = Column(String(50), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    is_dummy = Column(Boolean, nullable=False, default=True)


class MaintenanceIncident(Base):
    """Riwayat insiden pemeliharaan dari Incident Database.xlsx (Data dummy)."""
    __tablename__ = "incident"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_row = Column(Integer, nullable=False)
    serial_no = Column(Integer, nullable=False, index=True)
    mto_no = Column(String(100), nullable=False)
    ar_no = Column(String(100), nullable=True)
    plant = Column(String(50), nullable=False, index=True)
    tag = Column(String(50), nullable=False, index=True)
    eq_class = Column(String(20), nullable=False)
    tanggal = Column(String(50), nullable=False, index=True)
    title = Column(Text, nullable=False)
    highest_impact = Column(String(100), nullable=False)
    pre_risk = Column(String(20), nullable=False)
    risk_score = Column(Float, nullable=False)
    pic_rca = Column(String(150), nullable=False)
    status_rca = Column(String(50), nullable=False, index=True)
    discipline = Column(String(50), nullable=False, index=True)
    eq_type = Column(String(50), nullable=False)
    komponen = Column(String(100), nullable=False, index=True)
    f_mechanism = Column(String(100), nullable=False)
    downtime_h = Column(Float, nullable=False, default=0.0)
    act_loss_usd = Column(Float, nullable=False, default=0.0)
    pot_loss_usd = Column(Float, nullable=False, default=0.0)
    total_loss_usd = Column(Float, nullable=False, default=0.0)
    tenggat_rca = Column(String(50), nullable=True)
    month_year = Column(String(50), nullable=False)
    needs_review = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)




