import os
import sys
import json
import unittest
import openpyxl

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi.testclient import TestClient
from app.main import app
from app.ml.scenarios import run_all_scenarios, run_scenario
from app.ml.excel_input import read_and_evaluate_excel

class TestScenariosAndSimulator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_01_seven_standard_scenarios(self):
        """Memverifikasi seluruh 7 skenario standar memenuhi hasil yang diharapkan."""
        summary = run_all_scenarios()
        self.assertEqual(summary["total_scenarios"], 7)
        self.assertTrue(summary["all_passed"], f"Gagal pada skenario: {[r['scenario_key'] for r in summary['results'] if not r['passed']]}")
        print(f"PASSED: 7 skenario standar terverifikasi 100% lulus.")

    def test_02_corrupted_file_handling(self):
        """Memverifikasi penanganan berkas rusak secara graceful dengan pesan error informatif."""
        corrupted_path = os.path.join(PROJECT_ROOT, "scratch", "corrupted_test.xlsx")
        os.makedirs(os.path.dirname(corrupted_path), exist_ok=True)
        with open(corrupted_path, "wb") as f:
            f.write(b"NOT_A_VALID_ZIP_OR_XLSX_STREAM_1234567890")

        res = read_and_evaluate_excel(corrupted_path)
        self.assertFalse(res["file_status"]["is_valid"])
        self.assertTrue(len(res["file_status"]["errors"]) > 0)
        self.assertTrue(any("rusak" in err.lower() or "zip" in err.lower() for err in res["file_status"]["errors"]))
        if os.path.exists(corrupted_path):
            os.remove(corrupted_path)
        print("PASSED: Berkas korup/rusak ditangani dengan aman tanpa crash.")

    def test_03_temporary_lock_file_ignored(self):
        """Memverifikasi berkas sementara ~$* diabaikan oleh sistem."""
        res = read_and_evaluate_excel("~$live_sensor_input.xlsx")
        self.assertFalse(res["file_status"]["is_valid"])
        self.assertTrue(any("sementara" in err.lower() for err in res["file_status"]["errors"]))
        print("PASSED: Berkas kunci sementara Excel (~$*) diabaikan dengan benar.")

    def test_04_uncalculated_formula_detection(self):
        """Memverifikasi deteksi sel formula tanpa cached value (None pada data_only=True)."""
        uncalc_path = os.path.join(PROJECT_ROOT, "scratch", "uncalc_test.xlsx")
        wb = openpyxl.Workbook()
        ws_p = wb.active
        ws_p.title = "PARAMETER"
        ws_p["B4"] = "KO-3201"
        ws_p["B5"] = "GENERATOR"
        ws_p["B6"] = "ramp"

        ws_g = wb.create_sheet("GENERATOR")
        # Row 4 with formula but no cached value
        ws_g["B4"] = "2026-10-01 00:00:00"
        ws_g["C4"] = "=50+5"
        ws_g["D4"] = "=28+1"
        wb.save(uncalc_path)

        res = read_and_evaluate_excel(uncalc_path)
        self.assertFalse(res["file_status"]["is_valid"])
        self.assertTrue(any("Buka dan simpan file di Excel agar rumus terhitung" in err for err in res["file_status"]["errors"]))
        if os.path.exists(uncalc_path):
            os.remove(uncalc_path)
        print("PASSED: Deteksi sel rumus kosong berhasil mengarahkan pengguna untuk menyimpan di Excel.")

    def test_05_idempotency_and_state_preservation(self):
        """Memverifikasi evaluasi bersifat idempoten dan mempertahankan state valid terakhir saat terjadi error."""
        res1 = read_and_evaluate_excel()
        res2 = read_and_evaluate_excel()
        self.assertEqual(res1["file_status"]["is_valid"], res2["file_status"]["is_valid"])

        # Uji membaca file rusak: harus mempertahankan data simulasi terakhir
        corrupted_path = os.path.join(PROJECT_ROOT, "scratch", "corrupted_temp.xlsx")
        with open(corrupted_path, "wb") as f:
            f.write(b"JUNK")
        res_err = read_and_evaluate_excel(corrupted_path)
        self.assertFalse(res_err["file_status"]["is_valid"])
        # State simulasi valid sebelumnya tetap dipertahankan
        self.assertIsNotNone(res_err.get("simulation"))
        if os.path.exists(corrupted_path):
            os.remove(corrupted_path)
        print("PASSED: Idempotensi dan pelestarian state valid terakhir terverifikasi.")

    def test_06_no_nan_in_api(self):
        """Memverifikasi payload API bebas dari NaN, Infinity, dan tipe data tidak valid."""
        resp = self.client.get("/api/ml/live-input")
        self.assertEqual(resp.status_code, 200)
        raw_text = resp.text
        self.assertNotIn("NaN", raw_text)
        self.assertNotIn("Infinity", raw_text)
        data = resp.json()
        self.assertIn("file_status", data)
        print("PASSED: Serialisasi JSON endpoint /api/ml/live-input bebas dari NaN.")

    def test_07_simulation_data_does_not_leak_to_kpi(self):
        """Memverifikasi isolasi mutlak: data simulasi Excel tidak pernah bocor ke KPI atau tabel historis."""
        # 1. Rekam metrik historis sebelum pembacaan simulasi
        kpi_before = self.client.get("/api/kpi/executive").json()
        alarms_before = self.client.get("/api/alarms").json()
        perf_before = self.client.get("/api/performance/restored").json()

        # 2. Jalankan simulasi live-input berkali-kali
        for _ in range(3):
            sim_res = self.client.get("/api/ml/live-input").json()
            if sim_res.get("simulation"):
                self.assertTrue(sim_res["simulation"]["is_simulated"])
                self.assertTrue(sim_res["simulation"]["is_dummy"])

        # 3. Verifikasi metrik historis tidak berubah sama sekali
        kpi_after = self.client.get("/api/kpi/executive").json()
        alarms_after = self.client.get("/api/alarms").json()
        perf_after = self.client.get("/api/performance/restored").json()

        self.assertEqual(kpi_before["totalMonitored"], kpi_after["totalMonitored"])
        self.assertEqual(kpi_before["criticalCount"], kpi_after["criticalCount"])
        self.assertEqual(kpi_before["activeAlarmCount"], kpi_after["activeAlarmCount"])
        self.assertEqual(len(alarms_before), len(alarms_after))
        self.assertEqual(len(perf_before), len(perf_after))
        print("PASSED: Data simulasi terisolasi 100% dan tidak pernah memengaruhi KPI / status armada historis.")

if __name__ == "__main__":
    unittest.main()
