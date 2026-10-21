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
from cal_cert_importer import extract_serial_and_date, extract_measurement, extract_multi_point_measurements


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
        """Preview a certificate; scalar resistor import is parsed, multi-point assets are verified point-by-point."""
        pdf_path = winfile.open_file(
            "Select Calibration Certificate PDF",
            filt="PDF files (*.pdf)\0*.pdf\0All files\0*.*\0",
        )
        if not pdf_path:
            return to_json_safe({"ok": False, "cancelled": True})

        try:
            id_fields = extract_serial_and_date(pdf_path)
            serial = id_fields.get("serial")
            cal_date = id_fields.get("cal_date")
            if not serial:
                return to_json_safe({"ok": False, "error": "Could not identify the Serial Number on the first two PDF pages. Nothing was imported."})
            if not cal_date:
                return to_json_safe({"ok": False, "error": "Could not identify a valid Date of Calibration on the first two PDF pages. Nothing was imported."})

            conn = self.get_conn()
            try:
                row = conn.execute(
                    "SELECT id, serial, model, asset_number, nominal_ohms, category, unit "
                    "FROM assets WHERE serial = ?", (serial,)
                ).fetchone()
                if not row:
                    return to_json_safe({
                        "ok": False,
                        "error": f"Serial {serial} is not registered in the calibration database. Register/match the asset before importing.",
                    })
                asset = {
                    "id": row[0], "serial": row[1], "model": row[2],
                    "asset_number": row[3], "nominal_ohms": row[4],
                    "category": row[5] or "standard_resistor", "unit": row[6] or "Ω",
                }
                duplicate = conn.execute(
                    "SELECT id FROM calibrations WHERE asset_id = ? AND cal_date = ?",
                    (asset["id"], cal_date.date().isoformat()),
                ).fetchone()
                if duplicate:
                    return to_json_safe({
                        "ok": False,
                        "error": f"A calibration for serial {serial} already exists on {cal_date.date().isoformat()}. Existing data was not changed.",
                    })

                test_points = conn.execute(
                    "SELECT id, point_name, group_name, nominal_value, unit, display_order "
                    "FROM test_points WHERE asset_id = ? ORDER BY display_order, id",
                    (asset["id"],),
                ).fetchall()
                category = asset["category"]
                if category == "standard_resistor" and not test_points:
                    meas = extract_measurement(pdf_path, known_nominal=asset["nominal_ohms"])
                    if meas.get("measured_value") is None or meas.get("mu_relative") is None:
                        return to_json_safe({
                            "ok": False,
                            "error": "Could not safely extract the resistor MEASURED VALUE and MU. " + " ".join(meas.get("warnings", [])),
                        })
                    return to_json_safe({
                        "ok": True, "pdf_path": pdf_path, "serial": serial,
                        "cal_date": cal_date.date().isoformat(), "cert_number": id_fields.get("cert_number"), "measured_value": meas["measured_value"],
                        "mu_relative": meas["mu_relative"], "warnings": meas.get("warnings", []),
                        "asset": asset, "manual_readings_required": False,
                    })

                if category not in ("ac_divider", "waveform_generator", "dcv_reference"):
                    return to_json_safe({"ok": False, "error": f"Certificate import is not configured for asset category '{category}'. Nothing was imported."})
                if not test_points:
                    return to_json_safe({"ok": False, "error": f"Asset {serial} is categorized as {category} but has no configured test points. Set up its point matrix before importing."})

                uncertainty_unit = {"ac_divider": "ppm", "dcv_reference": "nV", "waveform_generator": None}[category]
                configured_points = [{
                    "id": tp[0], "point_name": tp[1], "group_name": tp[2],
                    "nominal_value": tp[3], "unit": tp[4], "display_order": tp[5],
                } for tp in test_points]

                extracted = extract_multi_point_measurements(pdf_path, category, configured_points)
                extracted_by_id = {
                    int(r["test_point_id"]): r for r in extracted.get("readings", [])
                }
                points = []
                for point in configured_points:
                    point_id = int(point["id"])
                    reading = extracted_by_id.get(point_id, {})
                    points.append({
                        **point,
                        "name": point["point_name"],
                        "uncertainty_unit": uncertainty_unit,
                        # UI can prefill these fields, but operator confirmation
                        # remains mandatory because OCR results are not authoritative.
                        "measured_value": reading.get("measured_value"),
                        "uncertainty": reading.get("uncertainty"),
                        "extraction_status": "extracted" if reading else "manual_required",
                    })

                warnings = list(extracted.get("warnings", []))
                if not extracted.get("ok"):
                    warnings.append(
                        "Some point readings could not be confidently extracted. "
                        "Enter/verify every configured point against the PDF before saving."
                    )
                return to_json_safe({
                    "ok": True, "pdf_path": pdf_path, "serial": serial,
                    "cal_date": cal_date.date().isoformat(),
                    "cert_number": id_fields.get("cert_number"),
                    "warnings": warnings,
                    "asset": asset, "manual_readings_required": True,
                    "auto_extraction_complete": bool(extracted.get("ok")),
                    "extracted_readings": extracted.get("readings", []),
                    "test_points": points, "uncertainty_unit": uncertainty_unit,
                })
            finally:
                conn.close()
        except Exception as e:
            return to_json_safe({"ok": False, "error": f"Certificate preview failed safely: {e}"})

    def commit_imported_certificate(self, data):
        """Validate and atomically commit a verified scalar or multi-point certificate."""
        import math
        import sqlite3

        conn = self.get_conn()
        try:
            asset_id = int(data["asset_id"])
            cal_date = date.fromisoformat(str(data["cal_date"])[:10]).isoformat()
            asset = conn.execute(
                "SELECT id, serial, category FROM assets WHERE id = ?", (asset_id,)
            ).fetchone()
            if not asset:
                return to_json_safe({"ok": False, "error": "The selected asset no longer exists."})
            category = asset[2] or "standard_resistor"
            cert_number = data.get("cert_number") or None
            cert_pdf_path = data.get("pdf_path") or None

            existing = conn.execute(
                "SELECT id FROM calibrations WHERE asset_id = ? AND cal_date = ?",
                (asset_id, cal_date),
            ).fetchone()
            if existing:
                return to_json_safe({"ok": False, "duplicate": True, "error": f"A calibration already exists for {asset[1]} on {cal_date}. Existing data was not changed."})

            point_rows = conn.execute(
                "SELECT id, point_name, unit FROM test_points WHERE asset_id = ? ORDER BY display_order, id",
                (asset_id,),
            ).fetchall()
            if category in ("ac_divider", "waveform_generator", "dcv_reference") and not point_rows:
                return to_json_safe({"ok": False, "error": "This multi-point category has no configured test points. Import is blocked to prevent a misleading scalar-only calibration."})
            if point_rows and category in ("ac_divider", "waveform_generator", "dcv_reference"):
                submitted = data.get("readings")
                if not isinstance(submitted, list) or not submitted:
                    return to_json_safe({"ok": False, "error": "Point readings are required for this multi-point asset."})
                expected = {int(r[0]): r for r in point_rows}
                by_id = {}
                for item in submitted:
                    try:
                        point_id = int(item["test_point_id"])
                        value = float(item["measured_value"])
                    except (KeyError, TypeError, ValueError):
                        return to_json_safe({"ok": False, "error": "Each point requires a valid numeric measured value."})
                    if point_id not in expected or point_id in by_id or not math.isfinite(value):
                        return to_json_safe({"ok": False, "error": "Point list contains an unknown/duplicate point or a non-finite reading."})
                    uncertainty = item.get("uncertainty")
                    if category in ("ac_divider", "dcv_reference"):
                        try:
                            uncertainty = float(uncertainty)
                        except (TypeError, ValueError):
                            return to_json_safe({"ok": False, "error": f"Uncertainty is required for every {category} test point."})
                        if not math.isfinite(uncertainty) or uncertainty < 0:
                            return to_json_safe({"ok": False, "error": "Uncertainty must be a finite non-negative number."})
                    else:
                        uncertainty = None
                    by_id[point_id] = {"measured_value": value, "uncertainty": uncertainty}
                if set(by_id) != set(expected):
                    missing = [expected[pid][1] for pid in expected.keys() - by_id.keys()]
                    return to_json_safe({"ok": False, "error": "Missing test-point reading(s): " + ", ".join(missing)})
                # Legacy summary columns remain required by the schema. For multi-point
                # assets they mirror the first configured point; per-point values and
                # uncertainty remain authoritative in calibration_readings.
                first_id = int(point_rows[0][0])
                measured_value = by_id[first_id]["measured_value"]
                mu_relative = 0.0  # no single global MU exists for these multi-point categories
            else:
                try:
                    measured_value = float(data["measured_value"])
                    mu_relative = float(data["mu_relative"])
                except (KeyError, TypeError, ValueError):
                    return to_json_safe({"ok": False, "error": "Measured value and relative uncertainty are required."})
                if not math.isfinite(measured_value) or not math.isfinite(mu_relative) or mu_relative <= 0:
                    return to_json_safe({"ok": False, "error": "Measured value must be finite and relative uncertainty must be greater than zero."})
                by_id = {}

            try:
                with conn:
                    cur = conn.execute(
                        "INSERT INTO calibrations (asset_id, cert_number, cal_date, measured_value, mu_relative, source, cert_pdf_path) "
                        "VALUES (?, ?, ?, ?, ?, 'pdf_import', ?)",
                        (asset_id, cert_number, cal_date, measured_value, mu_relative, cert_pdf_path),
                    )
                    cal_id = cur.lastrowid
                    for point_id, values in by_id.items():
                        conn.execute(
                            "INSERT INTO calibration_readings (calibration_id, test_point_id, measured_value, uncertainty) "
                            "VALUES (?, ?, ?, ?)",
                            (cal_id, point_id, values["measured_value"], values["uncertainty"]),
                        )
            except sqlite3.IntegrityError as exc:
                return to_json_safe({"ok": False, "duplicate": True, "error": f"Import was not committed because of a database constraint: {exc}"})
            return to_json_safe({"ok": True, "calibration_id": cal_id, "point_count": len(by_id)})
        except (KeyError, TypeError, ValueError) as exc:
            return to_json_safe({"ok": False, "error": f"Invalid import data: {exc}"})
        finally:
            conn.close()

    def save_pdf_report(self, asset_ids=None):
        """Automated report export with zero manual metadata fields required."""
        conn = self.get_conn()
        try:
            if asset_ids is None:
                asset_ids = [r[0] for r in conn.execute("SELECT id FROM assets ORDER BY category, source_sheet, serial")]
            elif not asset_ids:
                return to_json_safe({"ok": False, "error": "No assets were selected for the report."})

            default_name = f"calibration_report_{datetime.now():%Y%m%d_%H%M%S}.pdf"
            dest_folder = str(Path.home() / "Documents" / "Calibration Reports")
            Path(dest_folder).mkdir(parents=True, exist_ok=True)

            save_path = winfile.save_file("Save Calibration Audit Report", dest_folder, default_name, filt="PDF files (*.pdf)\0*.pdf\0", ext="pdf")
            if not save_path:
                return to_json_safe({"ok": False, "cancelled": True})
            report_pdf.generate_report(conn, asset_ids, save_path)
            return to_json_safe({"ok": True, "path": save_path})
        except Exception as exc:
            return to_json_safe({"ok": False, "error": f"Report generation failed: {exc}"})
        finally:
            conn.close()

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
