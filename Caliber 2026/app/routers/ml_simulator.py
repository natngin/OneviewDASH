import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel

from app.ml.excel_input import read_and_evaluate_excel
from app.ml.scenarios import SCENARIO_CATALOG, run_scenario, generate_scenario_data
from app.ml.evaluator import evaluate

router = APIRouter(prefix="/api/ml", tags=["ml-simulator"])

class ExportRequest(BaseModel):
    tag: Optional[str] = None
    custom_notes: Optional[str] = None
    scenario_key: Optional[str] = None
    simulation_override: Optional[Dict[str, Any]] = None

@router.get("/live-input")
def get_live_excel_input() -> Dict[str, Any]:
    """
    Membaca dan mengevaluasi berkas Excel live_sensor_input.xlsx secara dinamis (hot-reload).
    Mengembalikan status berkas, riwayat telemetri, hasil evaluasi, TTT, dan rekomendasi CAPA.
    """
    try:
        return read_and_evaluate_excel()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal membaca berkas Excel live-input: {str(e)}")

@router.get("/scenarios")
def get_scenario_catalog() -> Dict[str, Any]:
    """
    Mengembalikan katalog 7 skenario standar pengujian modul alarm dini.
    """
    scenarios = []
    for k, v in SCENARIO_CATALOG.items():
        scenarios.append({
            "key": k,
            "id": v["id"],
            "name": v["name"],
            "tag": v["tag"],
            "mode": v["mode"],
            "description": v["description"],
            "expected_summary": v["expected"]
        })
    return {
        "total": len(scenarios),
        "scenarios": scenarios
    }

@router.get("/scenario-eval")
def get_scenario_evaluation(key: str = Query(..., description="Kunci skenario")) -> Dict[str, Any]:
    """
    Mengevaluasi skenario standar langsung dari katalog untuk pengujian cepat interaktif tanpa membuka berkas Excel.
    """
    if key not in SCENARIO_CATALOG:
        raise HTTPException(
            status_code=404,
            detail=f"Skenario '{key}' tidak ditemukan. Pilihan valid: {list(SCENARIO_CATALOG.keys())}"
        )
    
    scen_data = generate_scenario_data(key)
    scen_info = scen_data["scenario_info"]
    eval_res = evaluate(
        riwayat=scen_data["parameter_value"],
        beban=scen_data["load_rate"],
        aset=scen_data["tag"],
        config=scen_data["config"],
        timestamps=scen_data["timestamps"],
        is_simulated=True
    )
    
    timeseries_data = [
        {
            "hour": i + 1,
            "timestamp": scen_data["timestamps"][i],
            "load_rate": round(scen_data["load_rate"][i], 2),
            "parameter_value": round(scen_data["parameter_value"][i], 3)
        }
        for i in range(len(scen_data["parameter_value"]))
    ]
    
    return {
        "file_status": {
            "file_name": f"KATALOG SKENARIO: #{scen_info['id']} {scen_info['name']}",
            "file_path": f"app/ml/scenarios.py [{key}]",
            "last_read_time": datetime.now(timezone.utc).isoformat(),
            "file_mtime": datetime.now(timezone.utc).isoformat(),
            "is_valid": True,
            "errors": [],
            "selected_tag": scen_data["tag"],
            "selected_source": "SCENARIO_PRESET",
            "selected_mode": scen_info["mode"],
            "scenario_description": scen_info["description"],
            "total_rows_read": 72
        },
        "simulation": eval_res,
        "timeseries": timeseries_data
    }

@router.post("/export")
def export_simulation_summary(req: Optional[ExportRequest] = None) -> Dict[str, Any]:
    """
    Menghasilkan ringkasan satu halaman (1-page summary) hasil simulasi sensor.
    """
    sim = None
    f_stat = {}
    
    if req and req.simulation_override:
        sim = req.simulation_override
        f_stat = {
            "file_name": req.custom_notes or "Simulasi Interaktif",
            "selected_source": "MANUAL_UI"
        }
    elif req and req.scenario_key and req.scenario_key in SCENARIO_CATALOG:
        eval_resp = get_scenario_evaluation(req.scenario_key)
        sim = eval_resp["simulation"]
        f_stat = eval_resp["file_status"]
    else:
        live_res = read_and_evaluate_excel()
        sim = live_res.get("simulation")
        f_stat = live_res.get("file_status", {})

    if not sim:
        raise HTTPException(
            status_code=400,
            detail=f"Tidak ada data simulasi valid yang dapat diekspor. Error: {', '.join(f_stat.get('errors', []))}"
        )

    ts_now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    tag = sim["tag"]
    asset_name = sim["asset_name"]
    plant = sim["plant"]
    param = sim["parameter"]
    unit = sim["unit"]
    curr_val = sim["current_value"]
    exp_val = sim["expected_value"]
    status = sim["combined_status"]
    badge = sim["combined_badge"]
    ttt = sim["ttt_range"]
    reasons = sim.get("structured_reasons", [])
    recom = sim.get("recommendations", {})

    md_report = f"""# ONEVIEW PREDICTIVE MAINTENANCE — SIMULATION SUMMARY REPORT
**Tanggal/Waktu Ekspor**: {ts_now}  
**Sumber Berkas**: `{f_stat.get('file_name', 'live_sensor_input.xlsx')}`  
**Label Integritas**: `DUMMY DATA — SIMULASI ML ALARM DINI`  
**Prinsip**: `LANTAI KESELAMATAN AKTIF (SAFETY FLOOR 100%)`

---

## 1. IDENTIFIKASI PERALATAN & TELEMETRI TERKINI
- **Tag Peralatan**: `{tag}`
- **Nama Peralatan**: {asset_name} ({plant})
- **Parameter Terpantau**: {param} ({unit})
- **Nilai Sensor Terkini**: **{curr_val:.2f} {unit}**
- **Ekspektasi Beban Model**: {exp_val:.2f} {unit} (Deviasi Residu: {sim['residual']:+.2f}, Z-score: {sim['residual_zscore']:+.2f}σ)
- **Model Regresi Beban**: `{sim['regression_model']['formula']}` (R² = {sim['regression_model']['r2_score']})
- **Ambang Batas Aturan**: Alert = {sim['rule_alert_threshold']} {unit} | Trip = {sim['rule_trip_threshold']} {unit}

---

## 2. STATUS EVALUASI KESELAMATAN & ESTIMASI WAKTU
- **Tingkat Status**: **{status}** (`{badge}`)
- **Estimasi Waktu Menuju Trip (TTT)**: **{ttt}**
- **Lantai Keselamatan (Safety Floor)**: {'TERPICU (Aturan Melampaui Model ML)' if sim.get('safety_floor_triggered') else 'Aktif (Kondisi Sensor di Bawah Ambang Aturan)'}
- **Justifikasi Alasan Terstruktur**:
"""
    for r in reasons:
        md_report += f"  - {r}\n"

    md_report += f"""
---

## 3. REKOMENDASI TINDAKAN PRESKRIPTIF (SUMBER: RCA & CAPA)
- **Moda Kegagalan Dominan**: {recom.get('failure_mode', '-')}
- **Tindakan Mitigasi Segera (Operator / DCS)**:
  > {recom.get('immediate_action', '-')}
- **Tindakan Perbaikan (Maintenance Tim)**:
  > {recom.get('corrective_action', '-')}
- **Tindakan Pencegahan Sistemik (Reliability CAPA)**:
  > {recom.get('preventive_action', '-')}
- **Penanggung Jawab (PIC)**: {recom.get('pic', '-')}
- **Tingkat Prioritas**: {recom.get('priority', '-')}
- **Sumber Data Acuan**: {recom.get('source', '-')}

---
*Laporan ini dihasilkan secara otomatis oleh sistem ONEVIEW Simulator Addendum 2B. Data simulasi tidak memengaruhi catatan historis atau KPI eksekutif pabrik.*
"""

    return {
        "export_metadata": {
            "title": "ONEVIEW Simulation Summary Report",
            "exported_at": ts_now,
            "is_simulated": True,
            "dummy_badge": "DUMMY DATA — SIMULASI ML ALARM DINI",
            "safety_floor_enforced": True
        },
        "summary": {
            "tag": tag,
            "asset_name": asset_name,
            "plant": plant,
            "parameter": param,
            "unit": unit,
            "current_value": curr_val,
            "expected_value": exp_val,
            "residual_zscore": sim["residual_zscore"],
            "combined_status": status,
            "combined_badge": badge,
            "time_to_trip_range": ttt,
            "structured_reasons": reasons,
            "recommendations": recom
        },
        "report_markdown": md_report
    }
