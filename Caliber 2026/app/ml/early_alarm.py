import os
import json
import sqlite3
from typing import Dict, Any, List
from app.ml.evaluator import evaluate

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "oneview.db")
CONFIG_PATH = os.path.join(PROJECT_ROOT, "thresholds.json")

def load_thresholds() -> Dict[str, Any]:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def run_early_alarm_analysis() -> Dict[str, Any]:
    """
    Jalur data historis database.
    Membaca data condition_hourly dari SQLite dan mengevaluasinya menggunakan
    fungsi murni evaluate(...) yang sama persis dengan simulator Excel dan test.
    """
    thresholds = load_thresholds()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    asset_results = []
    total_lead_time_hours = 0
    anomalies_detected_count = 0

    for tag, cfg in thresholds.items():
        cursor.execute("""
            SELECT timestamp, parameter_value, load_rate_ton_hr, is_interpolated, source_resolution
            FROM condition_hourly
            WHERE tag = ?
            ORDER BY timestamp ASC
        """, (tag,))
        rows = cursor.fetchall()

        if not rows:
            eval_res = evaluate(
                riwayat=[],
                beban=[],
                aset=tag,
                config=cfg,
                timestamps=[],
                is_simulated=False
            )
            asset_results.append(eval_res)
            continue

        timestamps = [r[0] for r in rows]
        y = [float(r[1]) for r in rows]
        x = [float(r[2]) for r in rows]
        is_interp = bool(rows[0][3])
        source_res = str(rows[0][4])

        eval_res = evaluate(
            riwayat=y,
            beban=x,
            aset=tag,
            config=cfg,
            timestamps=timestamps,
            is_simulated=False
        )

        # Tambahkan informasi resolusi database jika tersedia
        eval_res["source_info"]["is_interpolated"] = is_interp
        eval_res["source_info"]["source_resolution"] = source_res

        if eval_res.get("ml_anomaly_detected"):
            anomalies_detected_count += 1
        total_lead_time_hours += eval_res.get("lead_time_hours", 0)

        asset_results.append(eval_res)

    conn.close()

    return {
        "metadata": {
            "title": "ONEVIEW Early Alarm ML Module (Unsupervised Load-Normalized Residual Anomaly Detection)",
            "definition": "Model normalisasi beban regresi linier pada periode baseline sehat untuk mengisolasi kenaikan degradasi murni dari fluktuasi laju produksi.",
            "source": "Tabel condition_hourly (oneview.db) & thresholds.json",
            "period": "30 Hari telemetri per jam (720 Jam per aset)",
            "benchmark": "Baseline 168 jam pertama (Minggu ke-1) periode sehat",
            "is_dummy": True,
            "dummy_badge": "DUMMY DATA — SIMULASI ML ALARM DINI",
            "safety_floor_rule": "Aturan ambang adalah LANTAI KESELAMATAN: alarm berbasis aturan selalu aktif dan tidak pernah ditekan oleh ML. ML hanya menambah peringatan lebih awal."
        },
        "summary": {
            "total_monitored_assets": len(thresholds),
            "early_anomalies_detected": anomalies_detected_count,
            "total_lead_time_gained_hours": total_lead_time_hours,
            "average_lead_time_hours": round(total_lead_time_hours / len(thresholds), 1) if thresholds else 0
        },
        "assets": asset_results
    }
