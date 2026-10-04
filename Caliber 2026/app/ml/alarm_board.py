"""
Alarm Board ML — klasifikasi aset 'Perlu Perbaikan' vs 'Watchlist'.

Memakai ulang fungsi murni evaluate() (app/ml/evaluator.py) PER PARAMETER sensor,
lalu menggabungkan hasilnya per aset. Tidak ada logika deteksi baru di sini; modul ini
hanya agregasi + aturan klasifikasi + atribusi sensor penyebab.

Prinsip:
- Lantai keselamatan: parameter dengan rule_status TRIP/ALERT SELALU membuat aset masuk
  'Perlu Perbaikan'; ML tidak pernah menurunkannya.
- Tanpa health % sintetis, tanpa klaim akurasi. Semua data DUMMY.
"""
import os
import json
import math
import sqlite3
from typing import Dict, Any, List, Optional

from app.ml.evaluator import evaluate

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "oneview.db")
CFG_PATH = os.path.join(PROJECT_ROOT, "sensor_thresholds.json")

RULE_RANK = {"TRIP": 3, "ALERT": 2, "NORMAL": 0}


def load_sensor_config() -> Dict[str, Any]:
    with open(CFG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _clean(v):
    """Pastikan JSON bebas NaN/inf."""
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_clean(x) for x in v]
    return v


def _param_rank(r: Dict[str, Any]) -> tuple:
    """Urutan 'seberapa dominan' sebuah parameter sebagai penyebab."""
    rule = RULE_RANK.get(r.get("rule_status", "NORMAL"), 0)
    ml = 1 if r.get("ml_anomaly_detected") else 0
    ttt = r.get("ttt_nominal_hours")
    ttt_score = -(ttt if ttt is not None else 1e9)
    flat = 1 if r.get("is_flatline") else 0
    return (rule, ml, ttt_score, abs(r.get("rolling_zscore") or 0.0), flat)


def _load_capa(conn: sqlite3.Connection) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    try:
        rows = conn.execute(
            "SELECT a.tag, c.tipe, c.teks, c.pic FROM alarm_capa c JOIN alarms a ON a.id = c.alarm_id"
        ).fetchall()
    except sqlite3.Error:
        return out
    for tag, tipe, teks, pic in rows:
        d = out.setdefault(tag, {})
        d[tipe] = teks
        d["pic"] = pic
    return out


def _priority(rule_top: str, ttt_min: Optional[float]) -> str:
    if rule_top == "TRIP":
        return "P1 — Intervensi segera (≤ 24 jam)"
    if rule_top == "ALERT" or (ttt_min is not None and ttt_min <= 72):
        return "P1 — Perbaikan ≤ 72 jam"
    return "P2 — Jadwalkan sebelum batas bawah estimasi TTT"


def _ttt_min_hours(r: Dict[str, Any]) -> Optional[float]:
    nom = r.get("ttt_nominal_hours")
    if nom is None:
        return None
    return max(0.5, round(nom * 0.75, 1))


def _downsample(seq: List, step: int) -> List:
    return seq[::step] if step > 1 else seq


def run_alarm_board(include_series: bool = True, series_step: int = 3) -> Dict[str, Any]:
    cfg = load_sensor_config()
    meta_cfg = cfg.get("_meta", {})
    repair_ttt = float(meta_cfg.get("repair_ttt_hours", 168))
    mild_z = float(meta_cfg.get("mild_drift_z", 1.5))
    support_z = float(meta_cfg.get("supporting_z", 2.0))

    conn = sqlite3.connect(DB_PATH)
    capa_db = _load_capa(conn)

    repair, watchlist, normal_tags = [], [], []
    window_start, window_end = None, None

    for tag, acfg in cfg["assets"].items():
        param_results = []
        series_by_param = {}
        for pkey, pcfg in acfg["parameters"].items():
            rows = conn.execute(
                "SELECT timestamp, value, load_rate FROM sensor_readings WHERE tag=? AND parameter=? ORDER BY timestamp ASC",
                (tag, pkey),
            ).fetchall()
            ts = [r[0] for r in rows]
            y = [float(r[1]) for r in rows]
            x = [float(r[2]) if r[2] is not None else 0.0 for r in rows]
            if ts:
                window_start = ts[0] if window_start is None or ts[0] < window_start else window_start
                window_end = ts[-1] if window_end is None or ts[-1] > window_end else window_end

            eval_cfg = {
                "asset_name": acfg["asset_name"], "plant": acfg["plant"],
                "parameter": pcfg["label"], "unit": pcfg["unit"],
                "baseline_min": pcfg["baseline_min"], "baseline_max": pcfg["baseline_max"],
                "alert": pcfg["alert"], "trip": pcfg["trip"],
                "source": "sensor_thresholds.json",
            }
            res = evaluate(riwayat=y, beban=x, aset=tag, config=eval_cfg, timestamps=ts, is_simulated=False)
            res["param_key"] = pkey
            res["param_label"] = pcfg["label"]
            res["failure_mode"] = pcfg.get("failure_mode", "-")
            param_results.append(res)

            if include_series and ts and "regression_model" in res:
                b0 = res["regression_model"]["intercept"]
                b1 = res["regression_model"]["slope"]
                series_by_param[pkey] = [
                    {"t": ts[i][5:16], "actual": round(y[i], 3), "expected": round(b0 + b1 * x[i], 3)}
                    for i in range(0, len(ts), series_step)
                ]

        valid = [r for r in param_results if r.get("combined_status") != "DATA TIDAK CUKUP"]
        if not valid:
            watchlist.append({
                "tag": tag, "asset_name": acfg["asset_name"], "plant": acfg["plant"], "cls": acfg.get("cls"),
                "reason": "Data sensor tidak cukup (< 24 titik) — perlu verifikasi akuisisi data",
                "status": "DATA TIDAK CUKUP", "status_color": "#94A3B8",
                "priority": "P3 — Verifikasi data", "dominant": None, "parameters": param_results,
            })
            continue

        ranked = sorted(valid, key=_param_rank, reverse=True)
        dom = ranked[0]
        rule_top = max((r["rule_status"] for r in valid), key=lambda s: RULE_RANK.get(s, 0))
        ttt_noms = [r["ttt_nominal_hours"] for r in valid if r.get("ttt_nominal_hours") is not None]
        ttt_min_nom = min(ttt_noms) if ttt_noms else None

        repair_reasons = []
        for r in valid:
            if r["rule_status"] in ("TRIP", "ALERT"):
                repair_reasons.append(f"{r['param_label']}: {r['rule_status']} (lantai keselamatan) — {r['current_value']} {r['unit']} vs ambang {r['rule_alert_threshold'] if r['rule_status']=='ALERT' else r['rule_trip_threshold']} {r['unit']}")
            elif r.get("ttt_nominal_hours") is not None and r["ttt_nominal_hours"] <= repair_ttt:
                tag_ml = "anomali ML + " if r.get("ml_anomaly_detected") else ""
                repair_reasons.append(f"{r['param_label']}: {tag_ml}tren menuju trip ≤ 7 hari ({r['ttt_range']})")

        supporting = [
            {
                "param_label": r["param_label"], "unit": r["unit"], "current_value": r["current_value"],
                "expected_value": r["expected_value"], "rolling_zscore": r["rolling_zscore"],
                "rule_status": r["rule_status"], "failure_mode": r["failure_mode"],
            }
            for r in ranked[1:]
            if abs(r.get("rolling_zscore") or 0) >= support_z or r["rule_status"] != "NORMAL"
        ]

        dominant = {
            "param_key": dom["param_key"], "param_label": dom["param_label"], "unit": dom["unit"],
            "current_value": dom["current_value"], "expected_value": dom["expected_value"],
            "residual": dom["residual"], "rolling_zscore": dom["rolling_zscore"],
            "alert": dom["rule_alert_threshold"], "trip": dom["rule_trip_threshold"],
            "rule_status": dom["rule_status"], "combined_status": dom["combined_status"],
            "ml_anomaly_detected": dom["ml_anomaly_detected"], "is_flatline": dom["is_flatline"],
            "ttt_range": dom["ttt_range"], "ttt_nominal_hours": dom["ttt_nominal_hours"],
            "drift_slope_per_h": dom["recent_drift_slope"],
            "ml_detection_timestamp": dom["ml_detection_timestamp"],
            "rule_alert_timestamp": dom["rule_alert_timestamp"],
            "failure_mode": dom["failure_mode"],
            "regression_formula": dom["regression_model"]["formula"],
            "r2": dom["regression_model"]["r2_score"],
            "series": series_by_param.get(dom["param_key"], []),
        }

        capa = capa_db.get(tag, {})
        base = {
            "tag": tag, "asset_name": acfg["asset_name"], "plant": acfg["plant"], "cls": acfg.get("cls"),
            "load_label": acfg.get("load_label"), "load_unit": acfg.get("load_unit"),
            "dominant": dominant, "supporting": supporting,
            "parameters": [
                {k: r.get(k) for k in ("param_label", "unit", "current_value", "expected_value", "rolling_zscore",
                                       "rule_status", "combined_status", "ttt_range", "failure_mode")}
                for r in param_results
            ],
            "actions": {
                "immediate": capa.get("immediate", "belum ada rekomendasi terdokumentasi"),
                "preventive": capa.get("preventive", "belum ada rekomendasi terdokumentasi"),
                "pic": capa.get("pic", "-"),
            },
        }

        if repair_reasons:
            if rule_top == "TRIP":
                status, color = "CRITICAL TRIP", "#E11D48"
            elif rule_top == "ALERT":
                status, color = "ALERT", "#D97706"
            else:
                status, color = "EARLY WARNING", "#2563EB"
            ttt_min_h = _ttt_min_hours({"ttt_nominal_hours": ttt_min_nom})
            base.update({
                "status": status, "status_color": color, "reasons": repair_reasons,
                "priority": _priority(rule_top, ttt_min_h),
                "_sort": (RULE_RANK.get(rule_top, 0), -(ttt_min_nom if ttt_min_nom is not None else 1e9),
                          max(abs(r.get("rolling_zscore") or 0) for r in valid)),
            })
            repair.append(base)
            continue

        # Kandidat watchlist
        flat = [r for r in valid if r.get("is_flatline")]
        ml_warn = [r for r in valid if r.get("ml_anomaly_detected")]
        drift = [r for r in valid if abs(r.get("rolling_zscore") or 0) >= mild_z]

        if flat:
            reason = f"Sensor {flat[0]['param_label']} flatline ≥ 24 jam — kemungkinan transmitter macet; cek instrumen"
            status, color, prio = "SENSOR FLATLINE", "#8B5CF6", "P3 — Cek instrumen"
        elif ml_warn:
            r = sorted(ml_warn, key=_param_rank, reverse=True)[0]
            reason = f"Anomali ML pada {r['param_label']} ({r['rolling_zscore']:+.2f}σ), {r['ttt_range']}"
            status, color, prio = "EARLY WARNING", "#2563EB", "P3 — Pantau ketat & rencanakan inspeksi"
        elif drift:
            r = sorted(drift, key=lambda q: abs(q.get("rolling_zscore") or 0), reverse=True)[0]
            reason = f"Drift ringan pada {r['param_label']} ({r['rolling_zscore']:+.2f}σ, di bawah ambang anomali 2.5σ)"
            status, color, prio = "DRIFT RINGAN", "#0891B2", "P3 — Pantau"
        else:
            normal_tags.append(tag)
            continue

        base.update({"status": status, "status_color": color, "reason": reason, "priority": prio,
                     "_sort": (abs(dom.get("rolling_zscore") or 0),)})
        watchlist.append(base)

    conn.close()

    repair.sort(key=lambda a: a["_sort"], reverse=True)
    watchlist.sort(key=lambda a: a.get("_sort", (0,)), reverse=True)
    for a in repair + watchlist:
        a.pop("_sort", None)

    return _clean({
        "metadata": {
            "title": "Alarm Board ML — Perlu Perbaikan & Watchlist",
            "engine": "evaluate() — normalisasi beban + residual Z-score + lantai keselamatan (dipanggil per parameter)",
            "source": "Tabel sensor_readings (DUMMY) & sensor_thresholds.json",
            "window_start": window_start, "window_end": window_end,
            "repair_rule": "Ada parameter TRIP/ALERT (lantai keselamatan) ATAU tren menuju trip ≤ 7 hari",
            "watchlist_rule": "Anomali ML tanpa tren ≤ 7 hari, sensor flatline, atau drift ringan |Z| ≥ 1.5σ",
            "is_dummy": True,
            "dummy_badge": "DUMMY DATA",
            "disclaimer": "Pola degradasi dibuat untuk demo pipeline; bukan validasi akurasi model.",
        },
        "summary": {
            "total_assets": len(cfg["assets"]),
            "repair_count": len(repair),
            "watchlist_count": len(watchlist),
            "normal_hidden_count": len(normal_tags),
            "normal_hidden_tags": normal_tags,
        },
        "repair": repair,
        "watchlist": watchlist,
    })
