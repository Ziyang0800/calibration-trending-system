"""
service.py - Desktop service layer providing state, trend calculations,
file exports, settings management, and full mathematical traceability.
"""

import os
import math
import zipfile
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
from cal_cert_importer import extract_serial_and_date, extract_measurement


def to_json_safe(obj):
    """Recursively converts dates, NumPy scalars, and NaNs to standard JSON types."""
    if obj is None:
        return None
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()[:10]
    if isinstance(obj, dict):
        return {k: to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_json_safe(x) for x in obj]
    if hasattr(obj, "item"):
        val = obj.item()
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
        return val
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


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

    def get_settings(self):
        return to_json_safe({
            "local_db_path": self.db_path,
            "network_db_path": self.sync_mgr.get_network_path(),
            "theme": self.setup.get("theme", "dark"),
            "last_sync": self.sync_mgr.last_sync,
            "last_status": self.sync_mgr.last_status,
        })

    def save_settings(self, new_settings):
        if "network_db_path" in new_settings:
            self.setup["network_db_path"] = str(new_settings["network_db_path"]).strip()
        if "theme" in new_settings:
            self.setup["theme"] = new_settings["theme"]
            try:
                import winchrome
                winchrome.apply(self.setup["theme"], wait=False)
            except Exception:
                pass
        store.write_json(self.dir / "setup.json", self.setup)
        return to_json_safe({"ok": True})

    def get_sync_status(self):
        return to_json_safe({
            "last_sync": self.sync_mgr.last_sync,
            "status": self.sync_mgr.last_status,
            "target": self.sync_mgr.get_network_path(),
            "in_progress": self.sync_mgr.is_syncing,
        })

    def sync_database(self):
        return to_json_safe(self.sync_mgr.sync_now())

    def get_dashboard(self):
        conn = self.get_conn()
        sets = queries.list_assets_grouped_by_set(conn)
        conn.close()

        total = sum(s["total"] for s in sets)
        ok_count = sum(s["ok_count"] for s in sets)
        out_count = sum(s["out_count"] for s in sets)
        insufficient_count = sum(s["insufficient_count"] for s in sets)

        return to_json_safe({
            "sets": sets,
            "total": total,
            "ok_count": ok_count,
            "out_count": out_count,
            "insufficient_count": insufficient_count,
            "sync": self.get_sync_status(),
            "theme": self.setup.get("theme", "dark"),
        })

    def get_asset_detail(self, asset_id, tp_id=None):
        conn = self.get_conn()
        try:
            detail = queries.get_asset_detail(conn, int(asset_id), selected_point_id=int(tp_id) if tp_id else None)
            if not detail:
                return None

            trend = detail.get("trend")
            cals = detail.get("calibrations", [])
            asset = detail.get("asset", {})
            active_tp = detail.get("active_test_point") or {}
            stability = detail.get("stability")

            traceability = None
            if trend and len(cals) >= 4:
                n = trend["n"]
                df = trend["df"]
                t_crit = trend["t_crit"]
                Syx = trend["Syx"]
                xbar = trend["xbar"]
                SSx = trend["SSx"]
                slope = trend["slope"]
                intercept = trend["intercept"]

                latest_cal = cals[-1]
                x0 = latest_cal["accumulated_days"]
                leverage = ((x0 - xbar) ** 2) / SSx if SSx != 0 else 0.0
                margin = t_crit * Syx * math.sqrt(1.0 + (1.0 / n) + leverage) if SSx != 0 else 0.0

                unit = asset.get("unit", "Ω")
                drift_rate_year = slope * 365.25
                if unit == "dB":
                    rate_str = f"{drift_rate_year:+.5f} dB/year"
                elif unit == "Ratio":
                    nom = active_tp.get("nominal_value") or asset.get("nominal_ohms") or 1.0
                    rate_str = f"{(drift_rate_year / nom * 1e6):+.2f} ppm/year"
                else:
                    nom = asset.get("nominal_ohms") or 1.0
                    rate_str = f"{(drift_rate_year / nom * 1e6):+.2f} ppm/year"

                stability_calc = None
                if stability and stability.get("allowance_ppm") is not None:
                    observed = stability["observed_drift_ppm"]
                    allowance = stability["allowance_ppm"]
                    consumed_pct = (abs(observed) / allowance * 100.0) if allowance != 0 else 0.0
                    stability_calc = {
                        "spec_description": stability.get("spec_description"),
                        "previous_date": stability.get("previous_date"),
                        "latest_date": stability.get("latest_date"),
                        "elapsed_days": stability.get("elapsed_days"),
                        "observed_drift_ppm": observed,
                        "allowance_ppm": allowance,
                        "consumed_percent": consumed_pct,
                        "exceeds": stability.get("exceeds", False)
                    }

                traceability = {
                    "method_statement": "Hold-out anomaly evaluation (two-sided 95% prediction interval with Student's t expansion)",
                    "equation": f"y = {intercept:.9f} + ({slope:.5e}) × Days",
                    "slope": slope,
                    "intercept": intercept,
                    "annual_drift_rate": rate_str,
                    "n": n,
                    "df": df,
                    "t_crit": t_crit,
                    "Syx": Syx,
                    "xbar": xbar,
                    "SSx": SSx,
                    "x0_latest_days": x0,
                    "leverage": leverage,
                    "prediction_margin": margin,
                    "hold_out_date": latest_cal["date"],
                    "is_out_of_trend": latest_cal.get("out_of_trend", False),
                    "lower_bound": latest_cal.get("lower"),
                    "upper_bound": latest_cal.get("upper"),
                    "actual_reading": latest_cal["measured_value"],
                    "stability_calc": stability_calc
                }

            detail["traceability"] = traceability
            return to_json_safe(detail)
        finally:
            conn.close()

    def get_calibration_for_edit(self, calibration_id):
        conn = self.get_conn()
        cal = db.get_calibration(conn, int(calibration_id))
        if not cal:
            conn.close()
            return None

        tp_rows = conn.execute(
            "SELECT cr.test_point_id, tp.point_name, cr.measured_value, cr.uncertainty "
            "FROM calibration_readings cr JOIN test_points tp ON tp.id = cr.test_point_id "
            "WHERE cr.calibration_id = ? ORDER BY tp.display_order, tp.id",
            (calibration_id,)
        ).fetchall()
        conn.close()

        readings = [{"tp_id": r[0], "point_name": r[1], "measured_value": r[2], "uncertainty": r[3]} for r in tp_rows]
        return to_json_safe({**cal, "test_point_readings": readings})

    def save_calibration_edit(self, data):
        conn = self.get_conn()
        cal_id = int(data["id"])
        new_meas = float(data["measured_value"])
        new_mu = float(data.get("mu_relative", 0.0))
        comment = data.get("reviewer_comment", "").strip() or None
        excluded = bool(data.get("excluded_from_regression"))
        is_adj = bool(data.get("is_adjusted"))
        loc = data.get("location", "").strip() or None
        pressure = float(data["pressure_hpa"]) if data.get("pressure_hpa") else None

        ok, error = db.update_calibration(
            conn, cal_id,
            cal_date=data["cal_date"],
            measured_value=new_meas,
            mu_relative=new_mu,
            reviewer_comment=comment,
            excluded_from_regression=excluded,
            keep_existing_attachment=True,
            pressure_hpa=pressure,
            is_adjusted=is_adj,
            location=loc,
        )

        tp_readings = data.get("test_point_readings", [])
        if ok and tp_readings:
            for tpr in tp_readings:
                val = float(tpr["measured_value"])
                conn.execute(
                    "UPDATE calibration_readings SET measured_value = ? WHERE calibration_id = ? AND test_point_id = ?",
                    (val, cal_id, int(tpr["tp_id"]))
                )

        conn.commit()
        conn.close()
        return to_json_safe({"ok": ok, "error": error})

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
                "SELECT a.serial, c.cal_date, c.measured_value FROM assets a "
                "LEFT JOIN calibrations c ON c.asset_id = a.id WHERE a.asset_number = ? ORDER BY c.cal_date DESC LIMIT 1",
                (item["pn"],)
            ).fetchone()
            all_resistor_audit.append({
                **item,
                "serial": row[0] if row else "—",
                "cal_date": row[1] if row else "Missing",
                "measured_value": row[2] if row else None,
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

        div_pns = [
            ("PN030002", "10mV Block", "100:1", "Set 1"),
            ("PN030000", "100mV Block", "10:1", "Set 1"),
            ("PN030001", "10mV Block", "100:1", "Set 2"),
            ("PN030003", "100mV Block", "10:1", "Set 2"),
        ]
        divider_test_points = []
        for dpn, blk, ratio_nom, s_name in div_pns:
            d_asset = conn.execute("SELECT id, serial FROM assets WHERE asset_number = ?", (dpn,)).fetchone()
            if d_asset:
                d_id, d_sn = d_asset
                c_row = conn.execute("SELECT id, cal_date FROM calibrations WHERE asset_id = ? ORDER BY cal_date DESC LIMIT 1", (d_id,)).fetchone()
                cal_id = c_row[0] if c_row else None
                cal_date = c_row[1] if c_row else "Missing"

                for freq in ["1 kHz", "20 kHz", "100 kHz", "300 kHz", "500 kHz", "1 MHz"]:
                    r_val = None
                    if cal_id:
                        rd = conn.execute(
                            "SELECT cr.measured_value FROM calibration_readings cr "
                            "JOIN test_points tp ON tp.id = cr.test_point_id "
                            "WHERE cr.calibration_id = ? AND tp.point_name = ?", (cal_id, freq)
                        ).fetchone()
                        if rd:
                            r_val = rd[0]

                    divider_test_points.append({
                        "file": "DIVMEANS.TXT",
                        "rx_tag": f"{blk} · {freq}",
                        "nominal": f"{ratio_nom} ({freq})",
                        "pn": dpn,
                        "serial": d_sn,
                        "set": s_name,
                        "cal_date": cal_date,
                        "measured_value": r_val
                    })

        cf_points_def = [
            ("cf 10mV @ 4MHz (dB)", "10mV @ 4MHz"),
            ("cf 100mV @ 4MHz (dB)", "100mV @ 4MHz"),
            ("cf 100mV @ 8MHz (dB)", "100mV @ 8MHz"),
            ("cf 100mV @ 10MHz (dB)", "100mV @ 10MHz"),
            ("cf 1V @ 4MHz (dB)", "1V @ 4MHz"),
            ("cf 1V @ 8MHz (dB)", "1V @ 8MHz"),
            ("cf 1V @ 10MHz (dB)", "1V @ 10MHz"),
            ("cf 3V @ 2MHz (dB)", "3V @ 2MHz"),
            ("cf 3V @ 4MHz (dB)", "3V @ 4MHz"),
            ("cf 3V @ 8MHz (dB)", "3V @ 8MHz"),
            ("cf 3V @ 10MHz (dB)", "3V @ 10MHz"),
        ]

        wfg_all_points = {}
        wfg_details = {}
        for sn, item in WFG_OPTIONS.items():
            w_asset = conn.execute("SELECT id, asset_number, set_id FROM assets WHERE serial = ?", (sn,)).fetchone()
            asset_id = w_asset[0] if w_asset else None
            trace_id = w_asset[1] if (w_asset and w_asset[1]) else item["pn"]
            assigned_set = w_asset[2] if (w_asset and w_asset[2]) else item["default_set"]

            c_row = conn.execute("SELECT id, cal_date FROM calibrations WHERE asset_id = ? ORDER BY cal_date DESC LIMIT 1", (asset_id,)).fetchone() if asset_id else None
            cal_id = c_row[0] if c_row else None
            cal_date = c_row[1] if c_row else "No history"

            wfg_details[sn] = {
                **item,
                "trace_id": trace_id,
                "set_id": assigned_set,
                "last_date": cal_date,
            }

            pts_list = []
            for pt_col, pt_label in cf_points_def:
                val = None
                if cal_id:
                    rd = conn.execute(
                        "SELECT cr.measured_value FROM calibration_readings cr "
                        "JOIN test_points tp ON tp.id = cr.test_point_id "
                        "WHERE cr.calibration_id = ? AND tp.point_name = ?", (cal_id, pt_col)
                    ).fetchone()
                    if rd:
                        val = rd[0]
                pts_list.append({
                    "file": f"{item['file_id']}_Extended.txt",
                    "rx_tag": pt_label,
                    "nominal": "cf Data (dB)",
                    "pn": trace_id,
                    "serial": sn,
                    "cal_date": cal_date,
                    "measured_value": val
                })
            wfg_all_points[sn] = pts_list

        conn.close()
        return to_json_safe({
            "set_options": list(SET_STATION_MAPPING.keys()),
            "zero_pt_one_options": ZERO_POINT_ONE_OHM_OPTIONS,
            "zero_pt_one_details": zero_pt_one_details,
            "wfg_options": WFG_OPTIONS,
            "wfg_details": wfg_details,
            "wfg_all_points": wfg_all_points,
            "divider_test_points": divider_test_points,
            "all_resistors": all_resistor_audit,
            "set_name": set_name,
            "zero_pt_one_pn": zero_pt_one_pn,
            "wfg_serial": wfg_serial,
        })

    def generate_htbasic_zip(self, set_name, zero_pt_one_pn, wfg_serial):
        conn = self.get_conn()
        problems = htbasic_export.validate_required_resistors(conn, set_name, zero_pt_one_pn, wfg_serial)
        if problems:
            conn.close()
            return to_json_safe({"ok": False, "problems": problems})

        files = htbasic_export.generate_all_files(conn, set_name, zero_pt_one_pn, wfg_serial)
        conn.close()

        station = htbasic_export.SET_STATION_MAPPING[set_name]["station"].replace(" ", "")
        default_name = f"htbasic_{set_name.replace(' ', '')}_{station}_{datetime.now():%Y%m%d_%H%M%S}.zip"
        dest_folder = str(Path.home() / "Documents" / "Calibration Files")
        Path(dest_folder).mkdir(parents=True, exist_ok=True)

        save_path = winfile.save_file("Save HTBasic Cal Factor Package", dest_folder, default_name, filt="ZIP files (*.zip)\0*.zip\0", ext="zip")
        if not save_path:
            return to_json_safe({"ok": False, "cancelled": True})

        with zipfile.ZipFile(save_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for filename, content in files.items():
                if content:
                    zf.writestr(filename, content.encode("ascii"))

        return to_json_safe({"ok": True, "path": save_path})

    def import_certificate_file(self):
        """Native Windows Open dialog to select and parse a PDF certificate."""
        pdf_path = winfile.open_file("Select Calibration Certificate PDF", filt="PDF files (*.pdf)\0*.pdf\0All files\0*.*\0")
        if not pdf_path:
            return to_json_safe({"ok": False, "cancelled": True})

        try:
            id_fields = extract_serial_and_date(pdf_path)
            conn = self.get_conn()
            serial = id_fields.get("serial")
            asset = None
            if serial:
                row = conn.execute("SELECT id, serial, model, asset_number, nominal_ohms, category, unit FROM assets WHERE serial = ?", (serial,)).fetchone()
                if row:
                    asset = {"id": row[0], "serial": row[1], "model": row[2], "asset_number": row[3], "nominal_ohms": row[4], "category": row[5], "unit": row[6]}

            known_nom = asset["nominal_ohms"] if asset else None
            meas = extract_measurement(pdf_path, known_nominal=known_nom)
            conn.close()

            return to_json_safe({
                "ok": True,
                "pdf_path": pdf_path,
                "serial": serial or "",
                "cal_date": id_fields["cal_date"].date().isoformat() if id_fields.get("cal_date") else "",
                "measured_value": meas.get("measured_value"),
                "mu_relative": meas.get("mu_relative"),
                "warnings": meas.get("warnings", []),
                "asset": asset,
            })
        except Exception as e:
            return to_json_safe({"ok": False, "error": str(e)})

    def commit_imported_certificate(self, data):
        """Commits verified certificate reading directly to database."""
        conn = self.get_conn()
        asset_id = int(data["asset_id"])
        cal_date = data["cal_date"]
        measured_value = float(data["measured_value"])
        mu_relative = float(data.get("mu_relative", 0.0))
        cert_number = data.get("cert_number") or None
        cert_pdf_path = data.get("pdf_path") or None

        cal_id = db.insert_calibration(
            conn, asset_id, cal_date=cal_date, measured_value=measured_value,
            mu_relative=mu_relative, source="pdf_import", cert_number=cert_number,
            cert_pdf_path=cert_pdf_path
        )
        conn.commit()
        conn.close()
        return to_json_safe({"ok": True, "calibration_id": cal_id})

    def save_pdf_report(self, asset_ids=None):
        """Automated report export with zero manual metadata fields required."""
        conn = self.get_conn()
        if not asset_ids:
            asset_ids = [r[0] for r in conn.execute("SELECT id FROM assets ORDER BY category, source_sheet, serial")]

        default_name = f"calibration_report_{datetime.now():%Y%m%d_%H%M%S}.pdf"
        dest_folder = str(Path.home() / "Documents" / "Calibration Reports")
        Path(dest_folder).mkdir(parents=True, exist_ok=True)

        save_path = winfile.save_file("Save Calibration Audit Report", dest_folder, default_name, filt="PDF files (*.pdf)\0*.pdf\0", ext="pdf")
        if not save_path:
            conn.close()
            return to_json_safe({"ok": False, "cancelled": True})

        report_pdf.generate_report(conn, asset_ids, save_path)
        conn.close()
        return to_json_safe({"ok": True, "path": save_path})

    def export_excel(self, asset_id: int):
        conn = self.get_conn()
        try:
            row = conn.execute("SELECT serial FROM assets WHERE id = ?", (int(asset_id),)).fetchone()
            serial = row[0] if row else "asset"
            default_name = f"asset_{serial}_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
            dest_folder = str(Path.home() / "Documents" / "Calibration Exports")
            Path(dest_folder).mkdir(parents=True, exist_ok=True)

            save_path = winfile.save_file(
                "Export Asset to Excel", dest_folder, default_name,
                filt="Excel files (*.xlsx)\0*.xlsx\0", ext="xlsx"
            )
            if not save_path:
                return to_json_safe({"ok": False, "cancelled": True})

            # Strictly honor the exact user-selected path
            actual_path = export_excel.export_single_asset(conn, int(asset_id), out_path=save_path)
            return to_json_safe({"ok": True, "path": actual_path})
        finally:
            conn.close()