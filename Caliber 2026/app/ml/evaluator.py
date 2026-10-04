import os
import json
import numpy as np
from typing import Dict, Any, List, Optional

RCA_CAPA_DATABASE = {
    "KO-3201": {
        "failure_mode": "High Radial Vibration & Lube Oil Water Contamination",
        "immediate_action": "Batasi laju kompresor ke < 52 T/H; isolasi lube oil cooler dan lakukan pengujian kebocoran nitrogen.",
        "corrective_action": "Plug pipa cooler bocor; kuras 2.400L oli pelumas dan isi oli sintetis ISO VG 46 baru; inspeksi babbitt bearing.",
        "preventive_action": "Pasang online water-in-oil transmitter (AT-3201) terhubung ke alarm trip DCS; jadwalkan analisis oli mingguan.",
        "pic": "STA-02 (Stationary Lead) & ROT-01 (Rotating Lead)",
        "priority": "P1 - Critical Safety Action"
    },
    "BL-5702": {
        "failure_mode": "Coupling Misalignment & Impeller Casing Rub",
        "immediate_action": "Batasi throughput blower ke 37 T/H; pasang pemantau getaran portabel spektrum 1X & 2X.",
        "corrective_action": "Lakukan precision laser alignment poros motor-blower (offset < 0.05 mm); ganti flexible coupling disc pack.",
        "preventive_action": "Masukkan rute laser alignment berkala per 6 bulan; perketat inspeksi baut soft-foot pondasi.",
        "pic": "ROT-01 (Rotating Lead) & MEC-03 (Mechanical Specialist)",
        "priority": "P1 - Immediate Intervention"
    },
    "PM-4405B": {
        "failure_mode": "Motor Bearing Overheating & Grease Carbonization",
        "immediate_action": "Nyalakan pompa utilitas cadangan PM-4405C; turunkan beban bertahap dan hentikan PM-4405B untuk pendinginan.",
        "corrective_action": "Ganti bantalan drive-end (DE) dan non-drive-end (NDE); bersihkan sisa grease terbakar pada housing.",
        "preventive_action": "Ubah interval pelumasan ulang dari kalender 12 bulan menjadi berbasis kondisi per 4 bulan; gunakan metered grease gun.",
        "pic": "ELE-01 (Electrical Lead) & REL-02 (Reliability Engineer)",
        "priority": "P2 - Urgent Attention"
    },
    "HE-3301": {
        "failure_mode": "Heavy Tube-Side Fouling & Heat Duty Collapse",
        "immediate_action": "Potong laju umpan ZCU secara terkendali untuk menjaga batas suhu inlet reaktor hilir.",
        "corrective_action": "Buka tube bundle; eksekusi pembersihan high-pressure hydrojetting (20,000 psi) untuk melarutkan kokas/polimer.",
        "preventive_action": "Tetapkan ambang alarm otomatis pembersihan dP > 0.60 bar pada DCS; pasang transmitter dP pada filter umpan hulu.",
        "pic": "STA-02 (Stationary Lead) & OPR-01 (Operations Supervisor)",
        "priority": "P2 - Scheduled Intervention"
    },
    "PU-2101B": {
        "failure_mode": "Mechanical Seal Leakage & Suction Cavitation",
        "immediate_action": "Kurangi ramp rate umpan ke < 1.0 T/H per menit; pantau margin NPSH dan siapkan pompa cadangan.",
        "corrective_action": "Bongkar seal cartridge Plan 11; ganti silicon carbide face yang retak termal (heat checking).",
        "preventive_action": "Revisi SOP ramp rate start-up; pasang transmitter aliran flush otomatis Plan 11 dengan interlock DCS.",
        "pic": "ROT-01 (Rotating Lead) & MEC-01 (Mechanical Specialist)",
        "priority": "P1 - Critical Safety Action"
    }
}

def evaluate(
    riwayat: List[float],
    beban: List[float],
    aset: str,
    config: Dict[str, Any],
    timestamps: Optional[List[str]] = None,
    is_simulated: bool = False
) -> Dict[str, Any]:
    """
    Fungsi murni untuk mengevaluasi status kondisi peralatan.
    Digunakan secara identik oleh:
    1. Jalur data historis database (condition_hourly)
    2. Jalur simulator Excel (live_sensor_input.xlsx)
    3. Unit test perpustakaan skenario otomatis
    """
    unit = config.get("unit", "")
    alert_th = float(config["alert"])
    trip_th = float(config["trip"])
    baseline_min = float(config.get("baseline_min", 0.0))
    baseline_max = float(config.get("baseline_max", alert_th))
    is_decreasing = (alert_th < baseline_min)

    # 1. Pengecekan kecukupan titik data
    if riwayat is None or len(riwayat) < 24:
        return {
            "tag": aset,
            "asset_name": config.get("asset_name", aset),
            "plant": config.get("plant", "-"),
            "parameter": config.get("parameter", "-"),
            "unit": unit,
            "status": "DATA TIDAK CUKUP",
            "combined_status": "DATA TIDAK CUKUP",
            "combined_badge": "DATA TIDAK CUKUP",
            "status_color": "#94A3B8",
            "message": "Data tidak cukup (minimal 24 titik per jam diperlukan untuk regresi normalisasi beban).",
            "ttt_status": "data tidak cukup",
            "ttt_nominal_hours": None,
            "ttt_range": "data tidak cukup",
            "is_simulated": is_simulated,
            "is_dummy": True
        }

    y = np.array(riwayat, dtype=float)
    x = np.array(beban, dtype=float)
    n = len(y)

    if timestamps is None or len(timestamps) != n:
        timestamps = [f"T+{i:02d}h" for i in range(n)]

    # 2. Pemodelan Normalisasi Beban pada Baseline Sehat
    # Untuk data 30 hari (>= 168 jam): gunakan 168 jam pertama (Minggu ke-1).
    # Untuk simulasi 72 jam (< 168 jam): gunakan 24 jam pertama (Hari ke-1) sebagai baseline sehat.
    if n >= 168:
        baseline_len = 168
    else:
        baseline_len = min(24, n)

    x_base = x[:baseline_len]
    y_base = y[:baseline_len]

    # Regresi linier sederhana: y = beta_0 + beta_1 * x
    if np.all(x_base == x_base[0]):
        beta_0 = float(np.mean(y_base))
        beta_1 = 0.0
    else:
        A = np.vstack([np.ones_like(x_base), x_base]).T
        beta_0, beta_1 = np.linalg.lstsq(A, y_base, rcond=None)[0]
        beta_0, beta_1 = float(beta_0), float(beta_1)

    y_pred_base = beta_0 + beta_1 * x_base
    ss_tot = float(np.sum((y_base - np.mean(y_base))**2))
    ss_res = float(np.sum((y_base - y_pred_base)**2))
    r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 1e-9 else 0.0

    residuals_base = y_base - y_pred_base
    mu_res = float(np.mean(residuals_base))
    sigma_res = float(np.std(residuals_base))
    if sigma_res < 1e-6:
        sigma_res = 1e-6

    # 3. Perhitungan Residu Berkelanjutan & Rolling Z-Score (Window 6)
    y_expected = beta_0 + beta_1 * x
    residuals = y - y_expected
    z_scores = (residuals - mu_res) / sigma_res

    kernel_size = min(6, n)
    rolling_z = np.convolve(z_scores, np.ones(kernel_size)/kernel_size, mode='valid')
    rolling_z_padded = np.pad(rolling_z, (len(z_scores) - len(rolling_z), 0), mode='edge')

    # 4. Deteksi Sensor Flatline (24 jam terakhir tidak ada variansi)
    recent_len = min(24, n)
    is_flatline = bool(np.std(y[-recent_len:]) < 1e-5)

    # 5. Riwayat Pemicu & Waktu Deteksi
    ml_warn_idx = None
    rule_alert_idx = None
    rule_trip_idx = None

    for i in range(n):
        val = y[i]
        z = rolling_z_padded[i]

        if is_decreasing:
            if z <= -2.5 and ml_warn_idx is None:
                ml_warn_idx = i
            if val <= alert_th and rule_alert_idx is None:
                rule_alert_idx = i
            if val <= trip_th and rule_trip_idx is None:
                rule_trip_idx = i
        else:
            if z >= 2.5 and ml_warn_idx is None:
                ml_warn_idx = i
            if val >= alert_th and rule_alert_idx is None:
                rule_alert_idx = i
            if val >= trip_th and rule_trip_idx is None:
                rule_trip_idx = i

    current_val = float(y[-1])
    current_exp = float(y_expected[-1])
    current_res = float(residuals[-1])
    current_z = float(z_scores[-1])
    current_roll_z = float(rolling_z_padded[-1])

    # 6. Status Aturan Konvensional (Rule Status)
    if is_decreasing:
        if current_val <= trip_th:
            rule_status = "TRIP"
        elif current_val <= alert_th:
            rule_status = "ALERT"
        else:
            rule_status = "NORMAL"
    else:
        if current_val >= trip_th:
            rule_status = "TRIP"
        elif current_val >= alert_th:
            rule_status = "ALERT"
        else:
            rule_status = "NORMAL"

    # Status Anomali ML
    is_ml_anomaly = bool(current_roll_z <= -2.5) if is_decreasing else bool(current_roll_z >= 2.5)

    # 7. Penegakan Prinsip Lantai Keselamatan (Safety Floor Enforcement)
    structured_reasons = []
    if rule_status == "TRIP":
        combined_status = "CRITICAL TRIP"
        combined_badge = "TRIP (Rule Floor)"
        status_color = "#E11D48"
        structured_reasons.append(f"Nilai telemetri ({current_val:.2f} {unit}) telah melampaui batas kritis trip DCS ({trip_th:.2f} {unit}). Lantai keselamatan aktif mutlak.")
    elif rule_status == "ALERT":
        combined_status = "WARNING ALERT"
        combined_badge = "ALERT (Rule Floor)"
        status_color = "#D97706"
        structured_reasons.append(f"Nilai telemetri ({current_val:.2f} {unit}) melampaui batas peringatan alert DCS ({alert_th:.2f} {unit}). Ambang aturan ditegakkan.")
    elif is_flatline:
        combined_status = "SENSOR FLATLINE"
        combined_badge = "SENSOR MACET (FLATLINE)"
        status_color = "#8B5CF6"
        structured_reasons.append(f"Sensor tidak menunjukkan variansi sama sekali (flatline) selama {recent_len} jam terakhir. Terindikasi sensor macet atau koneksi transmitter freeze.")
    elif is_ml_anomaly:
        combined_status = "EARLY WARNING"
        combined_badge = "EARLY ANOMALY (ML)"
        status_color = "#2563EB"
        structured_reasons.append(f"Residu normalisasi beban menyimpang secara signifikan ({current_roll_z:+.2f}σ) melampaui ambang anomali 2.50σ sebelum batas aturan konvensional berbunyi.")
    else:
        combined_status = "NORMAL"
        combined_badge = "NORMAL"
        status_color = "#059669"
        structured_reasons.append("Parameter beroperasi dalam batas normal dan konsisten dengan beban operasi.")

    # 8. Perhitungan Time to Trip (TTT) Tanpa Presisi Palsu
    # Menghitung drift rate regresi tren 12–24 jam terakhir
    n_trend = min(24, n)
    y_recent = y[-n_trend:]
    t_recent = np.arange(n_trend, dtype=float)
    slope, intercept = np.polyfit(t_recent, y_recent, 1)
    slope = float(slope)

    # Evaluasi signifikansi kemiringan tren menuju trip
    is_trending_to_trip = (slope < -0.005) if is_decreasing else (slope > 0.005)
    
    if rule_status == "TRIP":
        ttt_status = "Telah mencapai batas trip"
        ttt_nominal_hours = 0.0
        ttt_range = "Telah mencapai batas trip"
    elif is_trending_to_trip:
        dist_to_trip = abs(trip_th - current_val)
        abs_slope = abs(slope)
        t_nom = dist_to_trip / abs_slope if abs_slope > 1e-6 else 9999.0

        if t_nom > 720.0:  # Lebih dari 30 hari
            ttt_status = "tidak ada tren menuju trip"
            ttt_nominal_hours = None
            ttt_range = "tidak ada tren menuju trip"
        else:
            t_min = max(0.5, round(t_nom * 0.75, 1))
            t_max = round(t_nom * 1.35, 1)
            t_nom_round = round(t_nom, 1)
            ttt_status = f"Tren perburukan terdeteksi ({abs_slope:.3f} {unit}/jam)"
            ttt_nominal_hours = t_nom_round
            if t_nom_round >= 48:
                d_min = round(t_min / 24, 1)
                d_max = round(t_max / 24, 1)
                ttt_range = f"{t_min} – {t_max} Jam (~{d_min} – {d_max} Hari)"
            else:
                ttt_range = f"{t_min} – {t_max} Jam (Estimasi ~{t_nom_round} Jam)"
    else:
        ttt_status = "tidak ada tren menuju trip"
        ttt_nominal_hours = None
        ttt_range = "tidak ada tren menuju trip"

    # 9. Perhitungan Lead Time
    lead_hours = 0
    if rule_alert_idx is not None and ml_warn_idx is not None:
        if rule_alert_idx > ml_warn_idx:
            lead_hours = int(rule_alert_idx - ml_warn_idx)

    # 10. Rekomendasi Tindakan Preskriptif Bersumber Tabel RCA/CAPA
    capa_info = RCA_CAPA_DATABASE.get(aset)
    if capa_info:
        recommendations = {
            "has_documented_capa": True,
            "failure_mode": capa_info["failure_mode"],
            "immediate_action": capa_info["immediate_action"],
            "corrective_action": capa_info["corrective_action"],
            "preventive_action": capa_info["preventive_action"],
            "pic": capa_info["pic"],
            "priority": capa_info["priority"],
            "source": f"RCA Database & CAPA Table for {aset}"
        }
    else:
        recommendations = {
            "has_documented_capa": False,
            "failure_mode": "belum ada rekomendasi terdokumentasi",
            "immediate_action": "belum ada rekomendasi terdokumentasi",
            "corrective_action": "belum ada rekomendasi terdokumentasi",
            "preventive_action": "belum ada rekomendasi terdokumentasi",
            "pic": "-",
            "priority": "-",
            "source": "None"
        }

    return {
        "tag": aset,
        "asset_name": config.get("asset_name", aset),
        "plant": config.get("plant", "-"),
        "parameter": config.get("parameter", "-"),
        "unit": unit,
        "baseline_range": f"{baseline_min} - {baseline_max} {unit}",
        "current_value": round(current_val, 2),
        "expected_value": round(current_exp, 2),
        "residual": round(current_res, 2),
        "residual_zscore": round(current_z, 2),
        "rolling_zscore": round(current_roll_z, 2),
        "rule_alert_threshold": alert_th,
        "rule_trip_threshold": trip_th,
        "rule_status": rule_status,
        "ml_anomaly_detected": is_ml_anomaly,
        "is_flatline": is_flatline,
        "combined_status": combined_status,
        "combined_badge": combined_badge,
        "status_color": status_color,
        "structured_reasons": structured_reasons,
        "lead_time_hours": lead_hours,
        "lead_time_days": round(lead_hours / 24.0, 1),
        "ml_detection_timestamp": timestamps[ml_warn_idx] if ml_warn_idx is not None else None,
        "rule_alert_timestamp": timestamps[rule_alert_idx] if rule_alert_idx is not None else None,
        "rule_trip_timestamp": timestamps[rule_trip_idx] if rule_trip_idx is not None else None,
        "ttt_status": ttt_status,
        "ttt_nominal_hours": ttt_nominal_hours,
        "ttt_range": ttt_range,
        "recent_drift_slope": round(slope, 4),
        "regression_model": {
            "formula": f"y = {beta_0:.3f} + {beta_1:.4f} * rate",
            "intercept": round(beta_0, 4),
            "slope": round(beta_1, 4),
            "r2_score": round(r2, 4),
            "residual_std": round(sigma_res, 4)
        },
        "recommendations": recommendations,
        "source_info": {
            "source": config.get("source", "thresholds.json"),
            "note": config.get("note", "-"),
            "needs_confirmation": bool(config.get("needs_confirmation", False)),
            "is_simulated": is_simulated,
            "is_dummy": True
        },
        "is_simulated": is_simulated,
        "is_dummy": True
    }
