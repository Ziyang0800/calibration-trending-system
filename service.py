"""
service.py - Desktop service layer providing state, trend calculations, 
and file exports to pywebview without web server overhead.
"""

import os
from datetime import datetime, date
from pathlib import Path

import db
import queries
import trending
import htbasic_export
import report_pdf
import export_excel
import store
import winfile


class CalibrationService:
    def __init__(self):
        self.dir = store.data_dir()
        self.setup = store.read_json(self.dir / "setup.json", {
            "network_db_path": store.DEFAULT_NETWORK_DB_PATH,
            "theme": "dark",
        })
        self.db_path = store.get_local_db_path()
        self.sync_mgr = store.DatabaseSyncManager(self.setup)

    def get_conn(self):
        return db.connect(self.db_path)

    def get_sync_status(self):
        return {
            "last_sync": self.sync_mgr.last_sync,
            "status": self.sync_mgr.last_status,
            "target": self.sync_mgr.get_network_path(),
            "in_progress": self.sync_mgr.is_syncing,
        }

    def sync_database(self):
        return self.sync_mgr.sync_now()

    def get_dashboard(self):
        conn = self.get_conn()
        sets = queries.list_assets_grouped_by_set(conn)
        conn.close()

        total = sum(s["total"] for s in sets)
        ok_count = sum(s["ok_count"] for s in sets)
        out_count = sum(s["out_count"] for s in sets)
        insufficient_count = sum(s["insufficient_count"] for s in sets)

        return {
            "sets": sets,
            "total": total,
            "ok_count": ok_count,
            "out_count": out_count,
            "insufficient_count": insufficient_count,
            "sync": self.get_sync_status(),
        }

    def get_asset_detail(self, asset_id, tp_id=None):
        conn = self.get_conn()
        detail = queries.get_asset_detail(conn, int(asset_id), selected_point_id=int(tp_id) if tp_id else None)
        conn.close()
        return detail

    def get_htbasic_context(self, set_name="Set 1", zero_pt_one_pn="PN010034", wfg_serial="SG53800187"):
        conn = self.get_conn()
        from htbasic_export import SET_STATION_MAPPING, ZERO_POINT_ONE_OHM_OPTIONS, WFG_OPTIONS

        HTBASIC_RESISTORS = [
            {"file": "RESNOM.txt", "rx_tag": "1 Ω Std", "nominal": "1 Ω", "pn": "PN010022", "set": "Set 1"},
            {"file": "RESNOM.txt", "rx_tag": "1 Ω Std", "nominal": "1 Ω", "pn": "PN010001", "set": "Set 2"},
            {"file": "RESVALUE.TXT", "rx_tag": "Rx 10001", "nominal": "10 Ω", "pn": "PN010002", "set": "Set 1"},
            {"file": "RESVALUE.TXT", "rx_tag": "Rx 10010", "nominal": "10 Ω", "pn": "PN010003", "set": "Set 2"},
            {"file": "RESVALUE.TXT", "rx_tag": "Rx 20050", "nominal": "100 Ω", "pn": "PN010004", "set": "Set 1"},
            {"file": "RESVALUE.TXT", "rx_tag": "Rx 20014", "nominal": "100 Ω", "pn": "PN010005", "set": "Set 2"},
            {"file": "RESVALUE.TXT", "rx_tag": "Rx 30267", "nominal": "1 kΩ", "pn": "PN010006", "set": "Set 1"},
            {"file": "RESVALUE.TXT", "rx_tag": "Rx 30162", "nominal": "1 kΩ", "pn": "PN010007", "set": "Set 2"},
            {"file": "RESVALUE.TXT", "rx_tag": "Rx 40233", "nominal": "10 kΩ", "pn": "PN010008", "set": "Set 1"},
            {"file": "RESVALUE.TXT", "rx_tag": "Rx 40059", "nominal": "10 kΩ", "pn": "PN010009", "set": "Set 2"},
            {"file": "HIGHRES.txt", "rx_tag": "S/N 50031", "nominal": "100 kΩ", "pn": "PN010010", "set": "Set 1"},
            {"file": "HIGHRES.txt", "rx_tag": "S/N 366", "nominal": "100 kΩ", "pn": "PN010011", "set": "Set 2"},
            {"file": "ONEMEG.txt", "rx_tag": "S/N 132", "nominal": "1 MΩ", "pn": "PN010012", "set": "Set 1"},
            {"file": "ONEMEG.txt", "rx_tag": "S/N 133", "nominal": "1 MΩ", "pn": "PN010013", "set": "Set 2"},
            {"file": "RESNOM.txt", "rx_tag": "10M #1", "nominal": "10 MΩ", "pn": "PN010014", "set": "Set 1"},
            {"file": "RESNOM.txt", "rx_tag": "10M #2", "nominal": "10 MΩ", "pn": "PN010015", "set": "Set 2"},
            {"file": "RESNOM.txt", "rx_tag": "100M Std", "nominal": "100 MΩ", "pn": "PN010017", "set": "Set 1"},
            {"file": "RESNOM.txt", "rx_tag": "100M Std", "nominal": "100 MΩ", "pn": "PN010016", "set": "Set 2"},
            {"file": "RESNOM.txt", "rx_tag": "1G Std", "nominal": "1 GΩ", "pn": "PN010050", "set": "Set 1"},
            {"file": "RESNOM.txt", "rx_tag": "1G Std", "nominal": "1 GΩ", "pn": "PN010048", "set": "Set 2"},
        ]

        all_resistor_audit = []
        for item in HTBASIC_RESISTORS:
            row = conn.execute(
                "SELECT a.serial, a.model, c.cal_date, c.measured_value FROM assets a "
                "LEFT JOIN calibrations c ON c.asset_id = a.id WHERE a.asset_number = ? ORDER BY c.cal_date DESC LIMIT 1",
                (item["pn"],)
            ).fetchone()
            all_resistor_audit.append({
                **item,
                "serial": row[0] if row else "—",
                "cal_date": row[2] if row else "Missing",
                "measured_value": row[3] if row else None,
            })

        zero_pt_one_details = {}
        for pn, label in ZERO_POINT_ONE_OHM_OPTIONS.items():
            row = conn.execute(
                "SELECT a.serial, a.set_id, c.cal_date, c.measured_value FROM assets a "
                "LEFT JOIN calibrations c ON c.asset_id = a.id WHERE a.asset_number = ? ORDER BY c.cal_date DESC LIMIT 1",
                (pn,)
            ).fetchone()
            zero_pt_one_details[pn] = {
                "asset_number": pn, "serial": row[0] if row else "—", "set_id": row[1] if row else "—",
                "last_date": row[2] if row else "Missing", "last_measured": row[3] if row else None
            }

        wfg_details = {}
        for sn, item in WFG_OPTIONS.items():
            row = conn.execute(
                "SELECT a.asset_number, a.set_id, c.cal_date FROM assets a "
                "LEFT JOIN calibrations c ON c.asset_id = a.id WHERE a.serial = ? ORDER BY c.cal_date DESC LIMIT 1",
                (sn,)
            ).fetchone()
            wfg_details[sn] = {
                **item,
                "trace_id": row[0] if row and row[0] else item["pn"],
                "set_id": row[1] if row and row[1] else item["default_set"],
                "last_date": row[2] if row and row[2] else "No history",
            }

        conn.close()
        return {
            "set_options": list(SET_STATION_MAPPING.keys()),
            "zero_pt_one_options": ZERO_POINT_ONE_OHM_OPTIONS,
            "zero_pt_one_details": zero_pt_one_details,
            "wfg_options": WFG_OPTIONS,
            "wfg_details": wfg_details,
            "all_resistors": all_resistor_audit,
            "set_name": set_name,
            "zero_pt_one_pn": zero_pt_one_pn,
            "wfg_serial": wfg_serial,
        }

    def generate_htbasic_zip(self, set_name, zero_pt_one_pn, wfg_serial):
        """Asks user where to save the .zip file using native Windows dialog, then compiles it."""
        import io, zipfile
        conn = self.get_conn()
        problems = htbasic_export.validate_required_resistors(conn, set_name, zero_pt_one_pn, wfg_serial)
        if problems:
            conn.close()
            return {"ok": False, "problems": problems}

        files = htbasic_export.generate_all_files(conn, set_name, zero_pt_one_pn, wfg_serial)
        conn.close()

        station = htbasic_export.SET_STATION_MAPPING[set_name]["station"].replace(" ", "")
        default_name = f"htbasic_{set_name.replace(' ', '')}_{station}_{datetime.now():%Y%m%d_%H%M%S}.zip"
        dest_folder = str(Path.home() / "Documents" / "Calibration Files")
        Path(dest_folder).mkdir(parents=True, exist_ok=True)

        save_path = winfile.save_file("Save HTBasic Cal Factor Package", dest_folder, default_name, filt="ZIP files (*.zip)\0*.zip\0", ext="zip")
        if not save_path:
            return {"ok": False, "cancelled": True}

        with zipfile.ZipFile(save_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for filename, content in files.items():
                if content:
                    zf.writestr(filename, content.encode("ascii"))

        return {"ok": True, "path": save_path}

    def save_pdf_report(self, asset_ids=None):
        """Generates a PDF report using native Windows Save dialog."""
        conn = self.get_conn()
        if not asset_ids:
            asset_ids = [r[0] for r in conn.execute("SELECT id FROM assets ORDER BY category, source_sheet, serial")]

        default_name = f"calibration_report_{datetime.now():%Y%m%d_%H%M%S}.pdf"
        dest_folder = str(Path.home() / "Documents" / "Calibration Reports")
        Path(dest_folder).mkdir(parents=True, exist_ok=True)

        save_path = winfile.save_file("Save Calibration Audit Report", dest_folder, default_name, filt="PDF files (*.pdf)\0*.pdf\0", ext="pdf")
        if not save_path:
            conn.close()
            return {"ok": False, "cancelled": True}

        report_pdf.generate_report(conn, asset_ids, save_path)
        conn.close()
        return {"ok": True, "path": save_path}

    def export_excel(self, asset_id):
        conn = self.get_conn()
        row = conn.execute("SELECT serial FROM assets WHERE id = ?", (int(asset_id),)).fetchone()
        serial = row[0] if row else "asset"
        default_name = f"asset_{serial}_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
        dest_folder = str(Path.home() / "Documents" / "Calibration Exports")
        Path(dest_folder).mkdir(parents=True, exist_ok=True)

        save_path = winfile.save_file("Export Asset to Excel", dest_folder, default_name, filt="Excel files (*.xlsx)\0*.xlsx\0", ext="xlsx")
        if not save_path:
            conn.close()
            return {"ok": False, "cancelled": True}

        export_excel.export_single_asset(conn, int(asset_id), out_dir=str(Path(save_path).parent))
        conn.close()
        return {"ok": True, "path": save_path}