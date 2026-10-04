import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_performance_kpi_endpoint():
    resp = client.get("/api/performance/kpi")
    assert resp.status_code == 200
    data = resp.json()

    assert data.get("badge") == "Dummy Data"
    assert data.get("is_dummy") is True

    # 5 Aset alarm aktif dieksklusi dari KPI kasus selesai
    filter_info = data.get("filter_info", {})
    assert filter_info.get("excluded_alarm_count") == 5
    assert set(filter_info.get("excluded_alarm_assets", [])) == {"BL-5702", "HE-3301", "KO-3201", "PM-4405B", "PU-2101B"}

    # Kasus selesai: 375 (380 - 5)
    assert data.get("kpi_incidents", {}).get("nilai") == 375

    # Cek rekonsiliasi total kasus selesai
    loss_usd = data.get("kpi_loss", {}).get("nilai_total_usd")
    assert abs(loss_usd - 63834140.0) < 1.0  # US$ 63,834,140.00 (~63.83M)

    downtime_h = data.get("kpi_downtime", {}).get("nilai_total_jam")
    assert abs(downtime_h - 2176.6) < 0.1  # 2,176.6 Jam

    # Proksi MTTR kasus selesai
    avg_dt = data.get("kpi_downtime", {}).get("rata_rata_jam")
    assert abs(avg_dt - 5.80) < 0.05

    # RCA Timeliness (89 dari 91 benchmark tetap utuh)
    rca_data = data.get("kpi_rca", {})
    assert rca_data.get("total_rca_berjalan") == 91
    assert rca_data.get("overdue_benchmark_count") == 89
    assert rca_data.get("overdue_today_count") == 91

    # Kelengkapan Data (226 AR kosong, 24 needs_review karena 2 bearing alarm tereksklusi)
    comp_data = data.get("kpi_data_completeness", {})
    assert comp_data.get("ar_kosong_count") == 226
    assert abs(comp_data.get("ar_kosong_pct") - 60.3) < 0.1
    assert comp_data.get("needs_review_count") == 24

    # Pareto
    top_6_comp = data.get("pareto_components", {}).get("top_6", [])
    assert len(top_6_comp) == 6
    assert top_6_comp[0]["komponen"] == "Shaft"
    assert top_6_comp[1]["komponen"] == "Bearing"

    top_7_plant = data.get("pareto_plants", {}).get("top_7", [])
    assert len(top_7_plant) == 7
    assert top_7_plant[0]["plant"] == "ZCU"
    assert top_7_plant[1]["plant"] == "ARP"

    # Limitations
    limitations = data.get("limitations", {})
    assert limitations.get("mtbf_per_asset") == "insufficient data"
    assert limitations.get("recurrence_per_asset") == "insufficient data"

    # KPI Prevented Last Month (Proactive Interventions & Avoided Downtime)
    prev = data.get("kpi_prevented_last_month", {})
    assert prev.get("total_prevented_trips") == 3
    assert prev.get("avoided_downtime_hours") == 42.0
    assert prev.get("avoided_loss_k_usd") == 558.0
    assert prev.get("recurrence_rate_pct") == 0.0
    items = prev.get("items", [])
    assert len(items) == 3
    tags = {it["tag"] for it in items}
    assert tags == {"PM-4405B", "FV-2208", "HE-3301"}

