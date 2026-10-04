import math
import numpy as np
from typing import Dict, Any, List
from app.ml.evaluator import evaluate
from app.ml.early_alarm import load_thresholds

SCENARIO_CATALOG = {
    "sehat": {
        "id": "1",
        "name": "Operasi Sehat Stabil (Normal Baseline)",
        "tag": "KO-3201",
        "mode": "datar",
        "description": "Kondisi operasi normal stabil dengan fluktuasi noise rendah tanpa tren degradasi.",
        "expected": {
            "combined_status": "NORMAL",
            "rule_status": "NORMAL",
            "ml_anomaly": False,
            "ttt_contains": "tidak ada tren menuju trip"
        }
    },
    "ramp_lambat": {
        "id": "2",
        "name": "Degradasi Bertahap Lambat (Slow Ramp)",
        "tag": "KO-3201",
        "mode": "ramp",
        "description": "Kenaikan bertahap parameter getaran melebihi baseline sehat, memicu ML early warning sebelum menyentuh alert aturan.",
        "expected": {
            "combined_status": "EARLY WARNING",
            "rule_status": "NORMAL",
            "ml_anomaly": True,
            "has_ttt_range": True
        }
    },
    "lonjakan_cepat": {
        "id": "3",
        "name": "Lonjakan Cepat (Rapid Degradation 2-5 Hari)",
        "tag": "PM-4405B",
        "mode": "lonjakan",
        "description": "Peningkatan suhu bearing secara agresif yang dengan cepat menembus batas alert aturan menuju trip.",
        "expected": {
            "combined_status": "WARNING ALERT",
            "rule_status": "ALERT",
            "has_ttt_range": True
        }
    },
    "naik_karena_beban": {
        "id": "4",
        "name": "Kenaikan Akibat Beban Operasi (Load-Driven Rise)",
        "tag": "KO-3201",
        "mode": "naik_karena_beban",
        "description": "Kenaikan parameter getaran yang proporsional dengan peningkatan laju beban proses. Normalisasi beban harus mengisolasinya sehingga TIDAK memicu alarm degradasi.",
        "expected": {
            "combined_status": "NORMAL",
            "ml_anomaly": False,
            "rule_status": "NORMAL"
        }
    },
    "spike_noise": {
        "id": "5",
        "name": "Spike Noise Impulsif Sesaat (Single-Hour Spike)",
        "tag": "BL-5702",
        "mode": "spike",
        "description": "Lonjakan tajam ekstrem 1 jam akibat interferensi sensor/listrik sesaat. Filter rolling harus meredamnya sehingga tidak memicu alarm palsu.",
        "expected": {
            "combined_status": "NORMAL",
            "ml_anomaly": False,
            "rule_status": "NORMAL"
        }
    },
    "sensor_flatline": {
        "id": "6",
        "name": "Sensor Macet / Beku (Sensor Flatline)",
        "tag": "HE-3301",
        "mode": "flatline",
        "description": "Nilai sensor sama sekali tidak bervariasi selama 24 jam terakhir, mengindikasikan transmitter freeze atau kabel putus.",
        "expected": {
            "combined_status": "SENSOR FLATLINE",
            "is_flatline": True
        }
    },
    "ml_normal_rule_trip": {
        "id": "7",
        "name": "Pelanggaran Batas Trip (Safety Floor Rule Supremacy)",
        "tag": "PU-2101B",
        "mode": "trip_breach",
        "description": "Nilai sensor anjlok menembus batas Trip aturan. Lantai keselamatan harus memaksa status CRITICAL TRIP tanpa peduli status ML.",
        "expected": {
            "combined_status": "CRITICAL TRIP",
            "rule_status": "TRIP"
        }
    }
}

def generate_scenario_data(scenario_key: str) -> Dict[str, Any]:
    """
    Menghasilkan data sintetis 72-jam untuk skenario pengujian tertentu.
    """
    thresholds = load_thresholds()
    scen = SCENARIO_CATALOG.get(scenario_key)
    if not scen:
        raise ValueError(f"Skenario '{scenario_key}' tidak ditemukan.")

    tag = scen["tag"]
    cfg = thresholds[tag]
    timestamps = [f"2026-10-{(h-1)//24+1:02d} {(h-1)%24:02d}:00:00" for h in range(1, 73)]

    n = 72
    y = np.zeros(n, dtype=float)
    x = np.zeros(n, dtype=float)

    if scenario_key == "sehat":
        # KO-3201: Normal baseline ~28.5 µm, load ~55 T/H
        for i in range(n):
            x[i] = 55.0 + math.sin(i * 0.5) * 0.5
            y[i] = 28.5 + math.sin(i * 0.89) * 0.25 + math.cos(i * 0.53) * 0.15

    elif scenario_key == "ramp_lambat":
        # KO-3201: Ramp perlahan dari 28.5 hingga ~38.0 µm (di atas baseline 30, tapi di bawah alert 45)
        # ML anomali terdeteksi saat Z >= 2.5
        for i in range(n):
            x[i] = 55.0 + math.sin(i * 0.5) * 0.5
            ramp = (i - 24) * 0.22 if i >= 24 else 0.0
            noise = math.sin(i * 0.89) * 0.15
            y[i] = 28.5 + ramp + noise

    elif scenario_key == "lonjakan_cepat":
        # PM-4405B: Suhu bearing normal 64°C, mulai jam 48 melonjak cepat hingga ~80°C (alert 75°C, trip 95°C)
        for i in range(n):
            x[i] = 135.0 + math.cos(i * 0.4) * 1.5
            surge = (i - 48) * 0.7 if i >= 48 else 0.0
            noise = math.sin(i * 0.7) * 0.2
            y[i] = 64.0 + surge + noise

    elif scenario_key == "naik_karena_beban":
        # KO-3201: Laju umpan naik dari 45 T/H ke 60 T/H (+15 T/H) pada jam 36
        # Sensor vibrasi naik proporsional dengan beban
        slope_beban = 0.12  # Korelasi fisik: vibrasi naik 0.12 um per T/H
        for i in range(n):
            load_step = 15.0 if i >= 36 else 0.0
            x[i] = 45.0 + load_step + math.sin(i * 0.5) * 0.3
            noise = math.sin(i * 0.89) * 0.15
            y[i] = 28.5 + (x[i] - 45.0) * slope_beban + noise

    elif scenario_key == "spike_noise":
        # BL-5702: Vibrasi normal ~3.8 mm/s, tepat di jam 35 ada 1 spike ke 18.0 mm/s
        for i in range(n):
            x[i] = 38.0 + math.sin(i * 0.3) * 0.4
            spike = 15.0 if i == 35 else 0.0
            noise = math.sin(i * 0.9) * 0.15
            y[i] = 3.8 + spike + noise

    elif scenario_key == "sensor_flatline":
        # HE-3301: Nilai persis konstan 9.400 bar tanpa variansi
        for i in range(n):
            x[i] = 30.0
            y[i] = 9.400

    elif scenario_key == "ml_normal_rule_trip":
        # PU-2101B: Tekanan discharge normal ~9.4 bar, di jam 60 anjlok ke 3.2 barg (trip th = 3.8)
        for i in range(n):
            x[i] = 13.5
            if i >= 60:
                y[i] = 3.2
            else:
                y[i] = 9.4 + math.sin(i * 0.6) * 0.1

    return {
        "scenario_key": scenario_key,
        "scenario_info": scen,
        "tag": tag,
        "config": cfg,
        "timestamps": timestamps,
        "load_rate": x.tolist(),
        "parameter_value": y.tolist()
    }

def run_scenario(scenario_key: str) -> Dict[str, Any]:
    """
    Menjalankan skenario tertentu melalui evaluate() dan memeriksa kesesuaian hasil vs ekspektasi.
    """
    data = generate_scenario_data(scenario_key)
    eval_res = evaluate(
        riwayat=data["parameter_value"],
        beban=data["load_rate"],
        aset=data["tag"],
        config=data["config"],
        timestamps=data["timestamps"],
        is_simulated=True
    )

    expected = data["scenario_info"]["expected"]
    passed = True
    reasons = []

    # Verifikasi ekspektasi
    if "combined_status" in expected:
        if eval_res["combined_status"] != expected["combined_status"]:
            passed = False
            reasons.append(f"Status aktual '{eval_res['combined_status']}' != ekspektasi '{expected['combined_status']}'")

    if "rule_status" in expected:
        if eval_res["rule_status"] != expected["rule_status"]:
            passed = False
            reasons.append(f"Rule status aktual '{eval_res['rule_status']}' != ekspektasi '{expected['rule_status']}'")

    if "ml_anomaly" in expected:
        if eval_res["ml_anomaly_detected"] != expected["ml_anomaly"]:
            passed = False
            reasons.append(f"ML Anomaly aktual '{eval_res['ml_anomaly_detected']}' != ekspektasi '{expected['ml_anomaly']}'")

    if "is_flatline" in expected:
        if eval_res["is_flatline"] != expected["is_flatline"]:
            passed = False
            reasons.append(f"Flatline flag '{eval_res['is_flatline']}' != ekspektasi '{expected['is_flatline']}'")

    if "ttt_contains" in expected:
        if expected["ttt_contains"] not in str(eval_res["ttt_range"]):
            passed = False
            reasons.append(f"TTT range '{eval_res['ttt_range']}' tidak memuat '{expected['ttt_contains']}'")

    if "has_ttt_range" in expected and expected["has_ttt_range"]:
        if eval_res["ttt_nominal_hours"] is None:
            passed = False
            reasons.append("Diharapkan ada estimasi TTT nominal tapi bernilai None")

    return {
        "scenario_key": scenario_key,
        "name": data["scenario_info"]["name"],
        "tag": data["tag"],
        "passed": passed,
        "discrepancies": reasons,
        "expected": expected,
        "evaluation": eval_res
    }

def run_all_scenarios() -> Dict[str, Any]:
    """
    Menjalankan seluruh 7 skenario dan mengembalikan rangkuman lulus/gagal.
    """
    results = []
    total_passed = 0
    for key in SCENARIO_CATALOG.keys():
        res = run_scenario(key)
        if res["passed"]:
            total_passed += 1
        results.append(res)

    return {
        "total_scenarios": len(results),
        "total_passed": total_passed,
        "all_passed": total_passed == len(results),
        "results": results
    }
