"""
Recommendation Engine for ONEVIEW Action Recommendations (CAPA).
Deterministic, auditable, and SLA-aware.
"""
import json
import statistics
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, desc

from app.models import ActionLibrary, ActionPlan, ActionItem, ActionEvent, WorkOrder, Roster, utc_now
from actions.config import SLA_HOURS, SLA_LABELS, LABEL_SLA, LABEL_ROSTER, VERIFICATION_NORMAL_DAYS, WO_PREFIX, WO_STATUS, VALID_TRANSITIONS


def detect_pattern(
    parameter: str,
    slope: float,
    residual_z: float,
    ttt_hours: Optional[float],
    is_flatline: bool = False,
    load_correlated: bool = False,
    is_transient_spike: bool = False,
    hours_in_alert: float = 0.0
) -> str:
    """
    Menentukan pola anomali berdasarkan metrik ML kuantitatif.
    """
    if load_correlated or (abs(residual_z) < 1.5 and abs(slope) > 0.05):
        return "kenaikan_karena_beban"
    if is_transient_spike:
        return "spike_tanpa_precursor"
    if is_flatline or (hours_in_alert >= 24.0 and abs(slope) < 0.005 and ttt_hours is None):
        return "plateau_di_atas_alert"
    if "RMS" in parameter.upper() or "2X" in parameter.upper():
        return "harmonik_2x"
    if "FLOW" in parameter.upper() and slope < 0:
        return "arah_rendah"
    if slope > 0 or abs(residual_z) >= 1.5:
        return "tren_naik"
    return "default"


def match_action_library(db: Session, parameter: str, pattern: str) -> Tuple[ActionLibrary, bool]:
    """
    Mencari entri pustaka tindakan terbaik.
    Return (library_entry, is_fallback).
    """
    # 1. Exact match parameter & pattern
    entry = db.query(ActionLibrary).filter(
        ActionLibrary.parameter.ilike(parameter),
        ActionLibrary.pattern == pattern
    ).first()
    if entry:
        return entry, False

    # 2. Match special pattern wildcard
    if pattern in ("spike_tanpa_precursor", "plateau_di_atas_alert", "kenaikan_karena_beban"):
        entry = db.query(ActionLibrary).filter(
            ActionLibrary.parameter == "*",
            ActionLibrary.pattern == pattern
        ).first()
        if entry:
            return entry, False

    # 3. Match parameter keywords with action library entries
    param_clean = parameter.lower()
    if "radial" in param_clean or ("vibration" in param_clean and "compressor" in param_clean):
        entry = db.query(ActionLibrary).filter(ActionLibrary.id == "LIB-RADIAL-VIB-TREND").first()
        if entry:
            return entry, False
    elif "coupling" in param_clean or "2x" in param_clean or "rms" in param_clean:
        entry = db.query(ActionLibrary).filter(ActionLibrary.id == "LIB-VIB-RMS-2X").first()
        if entry:
            return entry, False
    elif "temp" in param_clean or "suhu" in param_clean or "bearing" in param_clean:
        entry = db.query(ActionLibrary).filter(ActionLibrary.id == "LIB-BEARING-TEMP-RISE").first()
        if entry:
            return entry, False
    elif "tube" in param_clean or "dp" in param_clean or "differential pressure" in param_clean:
        entry = db.query(ActionLibrary).filter(ActionLibrary.id == "LIB-TUBE-DP-RISE").first()
        if entry:
            return entry, False
    elif "seal" in param_clean or "flush" in param_clean:
        entry = db.query(ActionLibrary).filter(ActionLibrary.id == "LIB-SEAL-FLUSH-FLOW-LOW").first()
        if entry:
            return entry, False

    for row in db.query(ActionLibrary).all():
        if row.parameter != "*" and (row.parameter.lower() in param_clean or param_clean in row.parameter.lower()):
            return row, False

    # 4. Fallback entry
    fallback = db.query(ActionLibrary).filter(ActionLibrary.id == "LIB-FALLBACK").first()
    if fallback:
        return fallback, True

    # If DB not yet seeded, create emergency in-memory fallback
    emergency = ActionLibrary(
        id="LIB-FALLBACK",
        parameter="*",
        pattern="default",
        title="Langkah Triase Umum (Fallback Pustaka)",
        hypothesis="Pustaka tindakan belum memuat parameter ini; perlu dilengkapi",
        diagnostics_json=json.dumps(["Validasi sensor", "Lihat tren 24 jam", "Beri tahu engineer jaga"]),
        immediate_json=json.dumps(["Lakukan verifikasi lokal di lapangan"]),
        preventive_json=json.dumps(["Lengkapi pustaka tindakan untuk parameter ini"]),
        owner_role="REL",
        source_ar="AR-FALLBACK-0000",
        source_note="Fallback triase umum",
        version="1.0",
        created_at=utc_now()
    )
    return emergency, True


def resolve_roster_pic(db: Session, plant: str, owner_roles_str: str) -> Tuple[str, str]:
    """
    Mencari nama PIC dari tabel roster berdasarkan plant dan owner_role.
    Return (pic_name, chosen_role).
    """
    roles = [r.strip() for r in owner_roles_str.replace("/", ",").split(",") if r.strip()]
    primary_role = roles[0] if roles else "REL"

    # Try plant match
    roster_item = db.query(Roster).filter(
        Roster.plant.ilike(plant),
        Roster.role == primary_role
    ).first()

    # Try general fallback
    if not roster_item:
        roster_item = db.query(Roster).filter(
            Roster.role == primary_role
        ).first()

    if roster_item:
        return f"{roster_item.name}", primary_role
    return f"Engineer {primary_role} ({LABEL_ROSTER})", primary_role


def build_evidence_summary(
    parameter: str,
    unit: str,
    slope: float,
    residual_z: float,
    current_val: float,
    pct_to_trip: float
) -> str:
    """
    Menghasilkan ringkasan bukti objektif untuk kolom 'Possible Failure' di UI.
    Bukan klaim penyebab! Berdasarkan deviasi empiris ML.
    """
    unit_str = f" {unit}" if unit else ""
    if abs(slope) >= 0.01:
        slope_str = f"{slope:+.2f}{unit_str}/hr"
    else:
        slope_str = f"{slope:+.4f}{unit_str}/hr"

    z_str = f"{residual_z:+.1f}σ"

    # Concise, objective summary for UI column
    return f"{parameter} rising {slope_str}; {z_str} from baseline ({pct_to_trip:.0f}% to trip)"


def get_or_create_plan_for_alarm(
    db: Session,
    tag: str,
    alarm_ref: str,
    severity: str,
    parameter: str,
    unit: str,
    current_val: float,
    expected_val: float,
    residual_z: float,
    slope: float,
    pct_to_trip: float,
    days_in_alarm_str: str,
    ttt_range_str: str,
    plant: str = "PLANT-01",
    as_of: Optional[datetime] = None,
    is_sandbox: bool = False,
    is_flatline: bool = False,
    load_correlated: bool = False,
    is_transient_spike: bool = False,
    hours_in_alert: float = 0.0,
    ttt_hours: Optional[float] = None
) -> ActionPlan:
    """
    Idempoten: Mengambil rencana tindakan aktif atau membuat baru (DRAFT).
    Jika severity berubah, membatalkan (SUPERSEDED) plan lama dan membuat revisi baru (revision + 1).
    """
    as_of_dt = as_of or utc_now()
    if as_of_dt.tzinfo is None:
        as_of_dt = as_of_dt.replace(tzinfo=timezone.utc)

    # Search existing active plan
    active_plan = db.query(ActionPlan).filter(
        ActionPlan.tag == tag,
        ActionPlan.is_sandbox == is_sandbox,
        ActionPlan.status.in_(["DRAFT", "APPROVED", "DISPATCHED", "DONE"])
    ).order_by(desc(ActionPlan.revision)).first()

    summary_text = build_evidence_summary(parameter, unit, slope, residual_z, current_val, pct_to_trip)
    evidence_payload = {
        "parameter": parameter,
        "unit": unit,
        "current_val": f"{current_val:.2f} {unit}".strip(),
        "expected_val": f"{expected_val:.2f} {unit}".strip(),
        "residual_z": f"{residual_z:+.2f}σ",
        "residual_z_raw": round(residual_z, 2),
        "drift_slope": f"{slope:+.4f} {unit}/hr".strip(),
        "drift_slope_raw": round(slope, 4),
        "pct_to_trip": f"{pct_to_trip:.1f}%",
        "pct_to_trip_raw": round(pct_to_trip, 1),
        "days_in_alarm": days_in_alarm_str,
        "ttt_range": ttt_range_str,
        "summary": summary_text
    }

    if active_plan:
        if active_plan.severity_at_creation == severity:
            # Idempotent: return existing plan, just update evidence if needed
            active_plan.evidence_json = json.dumps(evidence_payload, ensure_ascii=False)
            db.commit()
            db.refresh(active_plan)
            return active_plan
        else:
            # Severity changed! Supersede old plan
            old_status = active_plan.status
            active_plan.status = "SUPERSEDED"
            evt = ActionEvent(
                plan_id=active_plan.id,
                ts=as_of_dt,
                user="SYSTEM (ML Engine)",
                event="SUPERSEDED",
                from_status=old_status,
                to_status="SUPERSEDED",
                note=f"Severity berubah dari {active_plan.severity_at_creation} menjadi {severity}. Revisi baru dibuka."
            )
            db.add(evt)
            next_rev = active_plan.revision + 1
    else:
        next_rev = 1

    # Detect pattern and match library
    pattern = detect_pattern(
        parameter=parameter,
        slope=slope,
        residual_z=residual_z,
        ttt_hours=ttt_hours,
        is_flatline=is_flatline,
        load_correlated=load_correlated,
        is_transient_spike=is_transient_spike,
        hours_in_alert=hours_in_alert
    )
    lib_entry, is_fallback = match_action_library(db, parameter, pattern)

    sla_hours = SLA_HOURS.get(severity.upper(), 72.0)
    due_at = as_of_dt + timedelta(hours=sla_hours)

    new_plan = ActionPlan(
        alarm_ref=alarm_ref,
        tag=tag,
        severity_at_creation=severity,
        revision=next_rev,
        status="DRAFT",
        created_at=as_of_dt,
        due_at=due_at,
        sla_hours=sla_hours,
        library_id=lib_entry.id,
        evidence_json=json.dumps(evidence_payload, ensure_ascii=False),
        is_sandbox=is_sandbox
    )
    db.add(new_plan)
    db.flush()

    # Create items
    pic_name, primary_role = resolve_roster_pic(db, plant, lib_entry.owner_role)

    # Diagnostic items
    try:
        diag_list = json.loads(lib_entry.diagnostics_json)
    except Exception:
        diag_list = ["Verifikasi fisik sensor", "Analisis tren DCS"]
    for text in diag_list:
        db.add(ActionItem(
            plan_id=new_plan.id,
            tipe="diagnostic",
            teks=text,
            owner_role=primary_role,
            owner_name=pic_name,
            done=False
        ))

    # Immediate items
    try:
        imm_list = json.loads(lib_entry.immediate_json)
    except Exception:
        imm_list = ["Verifikasi keamanan lokal di lapangan"]
    for text in imm_list:
        db.add(ActionItem(
            plan_id=new_plan.id,
            tipe="immediate",
            teks=text,
            owner_role=primary_role,
            owner_name=pic_name,
            done=False
        ))

    # Preventive items
    try:
        prev_list = json.loads(lib_entry.preventive_json)
    except Exception:
        prev_list = ["Lengkapi catatan pemeliharaan berkala"]
    for text in prev_list:
        db.add(ActionItem(
            plan_id=new_plan.id,
            tipe="preventive",
            teks=text,
            owner_role=primary_role,
            owner_name=pic_name,
            done=False
        ))

    # Initial event
    db.add(ActionEvent(
        plan_id=new_plan.id,
        ts=as_of_dt,
        user="SYSTEM (ML Engine)",
        event="CREATED",
        from_status=None,
        to_status="DRAFT",
        note=f"Rencana tindakan dibuat otomatis ({'Fallback pustaka' if is_fallback else 'Pustaka ' + lib_entry.source_ar})"
    ))

    db.commit()
    db.refresh(new_plan)
    return new_plan


def approve_action_plan(
    db: Session,
    plan_id: int,
    user: str,
    note: Optional[str] = None,
    edited_items: Optional[List[Dict[str, Any]]] = None
) -> ActionPlan:
    plan = db.query(ActionPlan).filter(ActionPlan.id == plan_id).first()
    if not plan:
        raise ValueError("Action plan tidak ditemukan")
    if plan.status != "DRAFT":
        raise ValueError(f"Tidak dapat menyetujui plan dengan status {plan.status}. Plan harus berstatus DRAFT.")

    if edited_items:
        for edit in edited_items:
            iid = edit.get("id")
            new_teks = edit.get("teks")
            if iid and new_teks:
                item = db.query(ActionItem).filter(ActionItem.id == iid, ActionItem.plan_id == plan.id).first()
                if item:
                    item.teks = new_teks.strip()

    from_st = plan.status
    plan.status = "APPROVED"
    db.add(ActionEvent(
        plan_id=plan.id,
        ts=utc_now(),
        user=user or "User",
        event="APPROVED",
        from_status=from_st,
        to_status="APPROVED",
        note=note or "Rencana tindakan disetujui untuk eksekusi simulasi"
    ))
    db.commit()
    db.refresh(plan)
    return plan


def toggle_action_item(db: Session, plan_id: int, item_id: int, user: str = "User") -> ActionItem:
    item = db.query(ActionItem).filter(ActionItem.id == item_id, ActionItem.plan_id == plan_id).first()
    if not item:
        raise ValueError("Item tindakan tidak ditemukan")

    item.done = not item.done
    item.done_at = utc_now() if item.done else None

    db.add(ActionEvent(
        plan_id=plan_id,
        ts=utc_now(),
        user=user,
        event="ITEM_TOGGLED",
        from_status=None,
        to_status=None,
        note=f"Item #{item.id} ({item.tipe}) ditandai {'Selesai' if item.done else 'Belum selesai'}"
    ))
    db.commit()
    db.refresh(item)
    return item


def dispatch_action_plan(db: Session, plan_id: int, user: str, note: Optional[str] = None) -> Tuple[ActionPlan, WorkOrder]:
    plan = db.query(ActionPlan).filter(ActionPlan.id == plan_id).first()
    if not plan:
        raise ValueError("Action plan tidak ditemukan")
    if plan.status != "APPROVED":
        raise ValueError(f"Tidak dapat dispatch plan dengan status {plan.status}. Plan harus berstatus APPROVED.")

    wo_count = db.query(WorkOrder).count() + 1
    wo_no = f"{WO_PREFIX}{wo_count:06d}"

    wo = WorkOrder(
        plan_id=plan.id,
        wo_no=wo_no,
        status=WO_STATUS,
        created_at=utc_now()
    )
    db.add(wo)

    from_st = plan.status
    plan.status = "DISPATCHED"
    db.add(ActionEvent(
        plan_id=plan.id,
        ts=utc_now(),
        user=user or "User",
        event="DISPATCHED",
        from_status=from_st,
        to_status="DISPATCHED",
        note=f"Work Order simulasi {wo_no} dibuat (Status: {WO_STATUS}). {note or ''}".strip()
    ))
    db.commit()
    db.refresh(plan)
    db.refresh(wo)
    return plan, wo


def complete_action_plan(db: Session, plan_id: int, user: str, note: str) -> ActionPlan:
    if not note or not note.strip():
        raise ValueError("Catatan penyelesaian (note) wajib diisi.")

    plan = db.query(ActionPlan).filter(ActionPlan.id == plan_id).first()
    if not plan:
        raise ValueError("Action plan tidak ditemukan")
    if plan.status != "DISPATCHED":
        raise ValueError(f"Tidak dapat menyelesaikan plan dengan status {plan.status}. Plan harus berstatus DISPATCHED.")

    from_st = plan.status
    plan.status = "DONE"
    db.add(ActionEvent(
        plan_id=plan.id,
        ts=utc_now(),
        user=user or "User",
        event="COMPLETED",
        from_status=from_st,
        to_status="DONE",
        note=note.strip()
    ))
    db.commit()
    db.refresh(plan)
    return plan


def verify_action_plan(
    db: Session,
    plan_id: int,
    user: str,
    note: Optional[str] = None,
    days_normal_recorded: float = 7.0
) -> ActionPlan:
    plan = db.query(ActionPlan).filter(ActionPlan.id == plan_id).first()
    if not plan:
        raise ValueError("Action plan tidak ditemukan")
    if plan.status != "DONE":
        raise ValueError(f"Tidak dapat memverifikasi plan dengan status {plan.status}. Plan harus berstatus DONE.")

    if days_normal_recorded < VERIFICATION_NORMAL_DAYS:
        raise ValueError(
            f"Kriteria verifikasi belum terpenuhi: Aset memerlukan minimal {VERIFICATION_NORMAL_DAYS:.0f} hari "
            f"berturut-turut dalam kondisi NORMAL pasca-perbaikan (tercatat: {days_normal_recorded:.1f} hari)."
        )

    from_st = plan.status
    plan.status = "VERIFIED"
    db.add(ActionEvent(
        plan_id=plan.id,
        ts=utc_now(),
        user=user or "User",
        event="VERIFIED",
        from_status=from_st,
        to_status="VERIFIED",
        note=note or f"Kondisi normal terverifikasi selama {days_normal_recorded:.1f} hari berturut-turut pasca-tindakan."
    ))
    db.commit()
    db.refresh(plan)
    return plan


def calculate_action_kpis(db: Session, as_of: Optional[datetime] = None, is_sandbox: bool = False) -> Dict[str, Any]:
    """
    Menghitung KPI ringkasan eksekutif rencana tindakan:
    - Tindakan terlambat (overdue)
    - Draft yang belum disetujui
    - Median waktu alarm -> persetujuan (jam)
    - Median waktu alarm -> dispatch (jam)
    - % dalam SLA
    """
    as_of_dt = as_of or utc_now()
    if as_of_dt.tzinfo is None:
        as_of_dt = as_of_dt.replace(tzinfo=timezone.utc)

    plans = db.query(ActionPlan).filter(
        ActionPlan.is_sandbox == is_sandbox,
        ActionPlan.status != "SUPERSEDED",
        ActionPlan.status != "CANCELLED"
    ).all()

    overdue_count = 0
    draft_count = 0
    approval_times = []
    dispatch_times = []
    within_sla_count = 0
    total_evaluated = len(plans)

    status_counts = {"DRAFT": 0, "APPROVED": 0, "DISPATCHED": 0, "DONE": 0, "VERIFIED": 0}

    for p in plans:
        status_counts[p.status] = status_counts.get(p.status, 0) + 1
        created = p.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        due = p.due_at
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)

        is_overdue = (as_of_dt > due) and (p.status in ("DRAFT", "APPROVED", "DISPATCHED"))
        if is_overdue:
            overdue_count += 1

        if p.status == "DRAFT":
            draft_count += 1

        # Check approval & dispatch durations from events
        app_evt = next((e for e in p.events if e.event == "APPROVED"), None)
        disp_evt = next((e for e in p.events if e.event == "DISPATCHED"), None)

        if app_evt:
            evt_ts = app_evt.ts if app_evt.ts.tzinfo else app_evt.ts.replace(tzinfo=timezone.utc)
            approval_times.append(max((evt_ts - created).total_seconds() / 3600.0, 0.0))

        if disp_evt:
            evt_ts = disp_evt.ts if disp_evt.ts.tzinfo else disp_evt.ts.replace(tzinfo=timezone.utc)
            dispatch_times.append(max((evt_ts - created).total_seconds() / 3600.0, 0.0))

        # Check within SLA
        if not is_overdue:
            within_sla_count += 1

    median_approval = round(statistics.median(approval_times), 1) if approval_times else 0.0
    median_dispatch = round(statistics.median(dispatch_times), 1) if dispatch_times else 0.0
    pct_within_sla = round((within_sla_count / total_evaluated * 100.0), 1) if total_evaluated > 0 else 100.0

    return {
        "overdue_actions": overdue_count,
        "draft_pending": draft_count,
        "median_approval_hours": median_approval,
        "median_dispatch_hours": median_dispatch,
        "pct_within_sla": pct_within_sla,
        "total_active_plans": total_evaluated,
        "status_distribution": status_counts,
        "as_of": as_of_dt.isoformat()
    }
