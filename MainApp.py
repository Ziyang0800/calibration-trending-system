"""
MainApp.py - Calibration Trending & Metrology Management Dashboard.

Run with:
    python MainApp.py
Then open http://127.0.0.1:5000 in your browser.
"""

import argparse
import io
import os
import re
import shutil
import sys
import threading
import time
import uuid
import webbrowser
import zipfile
import secrets
from urllib.parse import urlparse
from pathlib import Path
from werkzeug.utils import secure_filename
from service import CalibrationService
from datetime import date, datetime
from flask import jsonify

from flask import Flask, render_template, send_file, abort, redirect, url_for, request, session

from db import (
    connect, update_asset, delete_asset, get_calibration, 
    update_calibration, delete_calibration, insert_calibration
)
from queries import list_assets_grouped_by_set, get_asset_detail
from export_excel import export_all_assets, export_single_asset
from report_pdf import generate_report
from htbasic_export import (
    SET_STATION_MAPPING, ZERO_POINT_ONE_OHM_OPTIONS, WFG_OPTIONS,
    validate_required_resistors, generate_all_files
)
from cal_cert_importer import extract_serial_and_date, extract_measurement, logger as cert_logger, _setup_logging


def resource_path(relative: str) -> str:
    """Locates bundled files (templates/, static/) in PyInstaller or development."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


def app_dir() -> str:
    """Persistent storage directory beside the executable or script."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


app = Flask(__name__, template_folder=resource_path("templates"), static_folder=resource_path("static"))
app.config["DB_PATH"] = os.path.join(app_dir(), "calibration.db")
app.secret_key = secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict", MAX_CONTENT_LENGTH=32 * 1024 * 1024)


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def protect_local_application():
    if request.remote_addr not in ("127.0.0.1", "::1"):
        abort(403, "This application accepts local connections only.")
    if urlparse("http://" + request.host).hostname not in ("127.0.0.1", "localhost", "::1"):
        abort(403, "Untrusted application host.")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        token = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
        expected = session.get("csrf_token")
        if not expected or not secrets.compare_digest(str(token), expected):
            abort(403, "The form expired. Reload the page and try again.")
        origin = request.headers.get("Origin")
        if origin and (urlparse(origin).scheme != "http" or urlparse(origin).hostname not in ("127.0.0.1", "localhost", "::1")):
            abort(403, "Cross-origin writes are not permitted.")


def desktop_service():
    # Share validation without starting desktop background backups in the web server.
    svc = CalibrationService.__new__(CalibrationService)
    svc.db_path = app.config["DB_PATH"]
    return svc


def pending_path(token):
    if not isinstance(token, str) or not re.fullmatch(r"[a-f0-9]{32}", token):
        raise ValueError("Invalid or expired upload token.")
    path = (Path(PENDING_DIR) / (token + ".pdf")).resolve()
    if path.parent != Path(PENDING_DIR).resolve():
        raise ValueError("Invalid upload path.")
    return path


EXPORTS_DIR = os.path.join(app_dir(), "exports")
REPORTS_DIR = os.path.join(app_dir(), "reports")
CERTS_DIR = os.path.join(app_dir(), "certs")
ATTACHMENTS_DIR = os.path.join(app_dir(), "attachments")
PENDING_DIR = os.path.join(app_dir(), "pending_imports")




def _decimals_for(nominal: float) -> int:
    integer_digits = len(str(abs(int(nominal)))) if abs(nominal) >= 1 else 1
    return max(0, 9 - integer_digits)


@app.template_filter("ohms")
def format_ohms(value):
    if value is None:
        return "—"
    if float(value) == int(value):
        return f"{int(value):,}"
    return f"{value:g}"


@app.template_filter("measured")
def format_measured(value, nominal=None):
    if value is None:
        return "—"
    decimals = _decimals_for(nominal) if nominal is not None else 8
    return f"{value:,.{decimals}f}"


@app.template_filter("basename")
def format_basename(path):
    if not path:
        return ""
    return os.path.basename(path)


def get_conn():
    return connect(app.config["DB_PATH"])

# -----------------------------------------------------------------------------
# REST API Endpoints for Next.js / shadcn/ui Frontend
# -----------------------------------------------------------------------------
@app.route("/api/csrf", methods=["GET"])
def api_csrf():
    response = jsonify({"csrf_token": csrf_token()})
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/api/dashboard", methods=["GET"])
def api_dashboard():
    conn = get_conn()
    sets = list_assets_grouped_by_set(conn)
    conn.close()

    total = sum(s["total"] for s in sets)
    ok_count = sum(s["ok_count"] for s in sets)
    out_count = sum(s["out_count"] for s in sets)
    insufficient_count = sum(s["insufficient_count"] for s in sets)

    return jsonify({
        "sets": sets,
        "total": total,
        "ok_count": ok_count,
        "out_count": out_count,
        "insufficient_count": insufficient_count,
    })


@app.route("/api/assets/<int:asset_id>", methods=["GET"])
def api_asset_detail(asset_id):
    conn = get_conn()
    tp = request.args.get("tp", type=int)
    detail = get_asset_detail(conn, asset_id, selected_point_id=tp)
    conn.close()
    if detail is None:
        return jsonify({"error": "Asset not found"}), 404
    return jsonify(detail)

@app.route("/api/htbasic/context", methods=["GET"])
def api_htbasic_context():
    conn = get_conn()
    set_name = request.args.get("set", "Set 1")
    zero_pt_one_pn = request.args.get("resistor", "PN010034")
    wfg_serial = request.args.get("wfg", "SG53800187")
    ctx = _get_htbasic_context(conn, set_name=set_name, zero_pt_one_pn=zero_pt_one_pn, wfg_serial=wfg_serial)
    conn.close()
    return jsonify(ctx)

# -----------------------------------------------------------------------------
# Dashboard & Core Asset Routes
# -----------------------------------------------------------------------------
@app.route("/")
def dashboard():
    conn = get_conn()
    sets = list_assets_grouped_by_set(conn)
    conn.close()

    total = sum(s["total"] for s in sets)
    ok_count = sum(s["ok_count"] for s in sets)
    out_count = sum(s["out_count"] for s in sets)
    insufficient_count = sum(s["insufficient_count"] for s in sets)

    return render_template(
        "dashboard.html", sets=sets, total=total,
        ok_count=ok_count, out_count=out_count, insufficient_count=insufficient_count,
    )


@app.route("/assets/<int:asset_id>")
def asset_detail(asset_id):
    conn = get_conn()
    tp = request.args.get("tp", type=int)
    detail = get_asset_detail(conn, asset_id, selected_point_id=tp)
    conn.close()
    if detail is None:
        abort(404)
    return render_template("asset_detail.html", **detail)


@app.route("/certs/<int:calibration_id>")
def view_certificate(calibration_id):
    conn = get_conn()
    row = conn.execute("SELECT cert_pdf_path FROM calibrations WHERE id = ?", (calibration_id,)).fetchone()
    conn.close()
    if row is None or row[0] is None or not os.path.exists(row[0]):
        abort(404, "No certificate PDF on file for this calibration.")
    return send_file(row[0], mimetype="application/pdf")


@app.route("/calibrations/<int:calibration_id>/comment")
def calibration_comment(calibration_id):
    conn = get_conn()
    cal = get_calibration(conn, calibration_id)
    asset = None
    if cal is not None:
        asset_row = conn.execute("SELECT serial, model FROM assets WHERE id = ?", (cal["asset_id"],)).fetchone()
        asset = {"serial": asset_row[0], "model": asset_row[1]} if asset_row else None
    conn.close()
    if cal is None:
        abort(404)
    return render_template("calibration_comment.html", cal=cal, asset=asset)


@app.route("/calibrations/<int:calibration_id>/attachment")
def view_attachment(calibration_id):
    conn = get_conn()
    cal = get_calibration(conn, calibration_id)
    conn.close()
    path = cal["reviewer_attachment_path"] if cal else None
    if not path or not os.path.exists(path):
        abort(404, "No attachment on file for this calibration.")
    return send_file(path, as_attachment=False)


# -----------------------------------------------------------------------------
# Reporting & Excel Export
# -----------------------------------------------------------------------------
@app.route("/export/asset/<int:asset_id>")
def export_asset(asset_id):
    conn = get_conn()
    path = export_single_asset(conn, asset_id, out_dir=EXPORTS_DIR)
    conn.close()
    if path is None:
        abort(404)
    return send_file(path, as_attachment=True)


@app.route("/export/all")
def export_all():
    conn = get_conn()
    path = export_all_assets(conn, out_dir=EXPORTS_DIR)
    conn.close()
    return send_file(path, as_attachment=True)


@app.route("/report/generate", methods=["POST"])
def report_generate():
    asset_ids = [int(i) for i in request.form.getlist("asset_ids")]
    conn = get_conn()
    if not asset_ids:
        asset_ids = [r[0] for r in conn.execute("SELECT id FROM assets ORDER BY category, source_sheet, serial")]
    path = os.path.join(REPORTS_DIR, f"calibration_report_{datetime.now():%Y%m%d_%H%M%S}.pdf")
    generate_report(conn, asset_ids, path)
    conn.close()
    return send_file(path, as_attachment=True)


# -----------------------------------------------------------------------------
# HTBasic Legacy Factor Generator
# -----------------------------------------------------------------------------
def _get_htbasic_context(conn, set_name="Set 1", zero_pt_one_pn="PN010034", wfg_serial="SG53800187", problems=None):
    from htbasic_export import WFG_OPTIONS

    # All standard resistors sorted ascending: 1 Ohm to 1 GOhm
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
            """
            SELECT a.serial, a.model, c.cal_date, c.measured_value 
            FROM assets a 
            LEFT JOIN calibrations c ON c.asset_id = a.id 
            WHERE a.asset_number = ? 
            ORDER BY c.cal_date DESC LIMIT 1
            """,
            (item["pn"],)
        ).fetchone()

        all_resistor_audit.append({
            **item,
            "serial": row[0] if row else "—",
            "model": row[1] if row else "—",
            "cal_date": row[2] if row else "Missing",
            "measured_value": row[3] if row else None,
        })

    # 0.1 Ohm Transfer Resistors
    zero_pt_one_details = {}
    for pn, label in ZERO_POINT_ONE_OHM_OPTIONS.items():
        row = conn.execute(
            """
            SELECT a.serial, a.model, a.set_id, c.cal_date, c.measured_value 
            FROM assets a 
            LEFT JOIN calibrations c ON c.asset_id = a.id 
            WHERE a.asset_number = ? 
            ORDER BY c.cal_date DESC LIMIT 1
            """,
            (pn,)
        ).fetchone()
        zero_pt_one_details[pn] = {
            "asset_number": pn, "serial": row[0] if row else "—", "model": row[1] if row else "—",
            "set_id": row[2] if row else "—", "last_date": row[3] if row else "Missing",
            "last_measured": row[4] if row else None
        }

    # Query all 6 frequencies for each Divider
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

    # Query all 11 cf points for all three 33622A units
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

    return {
        "set_options": list(SET_STATION_MAPPING.keys()),
        "zero_pt_one_options": ZERO_POINT_ONE_OHM_OPTIONS,
        "zero_pt_one_details": zero_pt_one_details,
        "wfg_options": WFG_OPTIONS,
        "wfg_details": wfg_details,
        "wfg_all_points": wfg_all_points,
        "divider_test_points": divider_test_points,
        "all_resistors": all_resistor_audit,
        "problems": problems,
        "set_name": set_name,
        "zero_pt_one_pn": zero_pt_one_pn,
        "wfg_serial": wfg_serial,
    }


@app.route("/htbasic")
def htbasic_form():
    conn = get_conn()
    ctx = _get_htbasic_context(conn)
    conn.close()
    return render_template("htbasic_form.html", **ctx)


@app.route("/htbasic/generate", methods=["POST"])
def htbasic_generate():
    set_name = request.form["set_name"]
    zero_pt_one_pn = request.form["zero_pt_one_pn"]
    wfg_serial = request.form.get("wfg_serial", "SG53800187")

    conn = get_conn()
    problems = validate_required_resistors(conn, set_name, zero_pt_one_pn, wfg_serial)
    if problems:
        ctx = _get_htbasic_context(conn, set_name=set_name, zero_pt_one_pn=zero_pt_one_pn, wfg_serial=wfg_serial, problems=problems)
        conn.close()
        return render_template("htbasic_form.html", **ctx)

    files = generate_all_files(conn, set_name, zero_pt_one_pn, wfg_serial)
    conn.close()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, content in files.items():
            if content:
                zf.writestr(filename, content.encode("ascii"))
    buf.seek(0)

    station = SET_STATION_MAPPING[set_name]["station"].replace(" ", "")
    zip_name = f"htbasic_{set_name.replace(' ', '')}_{station}_{datetime.now():%Y%m%d_%H%M%S}.zip"
    return send_file(buf, as_attachment=True, download_name=zip_name, mimetype="application/zip")


# -----------------------------------------------------------------------------
# Asset & Calibration Editing Routes
# -----------------------------------------------------------------------------
@app.route("/assets/<int:asset_id>/edit", methods=["GET", "POST"])
def asset_edit(asset_id):
    conn = get_conn()
    if request.method == "POST":
        ok, error = update_asset(
            conn, asset_id,
            serial=request.form["serial"].strip(),
            model=request.form.get("model", "").strip() or None,
            asset_number=request.form.get("asset_number", "").strip() or None,
            nominal_ohms=float(request.form["nominal_ohms"]),
            set_id=request.form.get("set_id", "").strip() or None,
            category=request.form.get("category", "").strip() or None,
            unit=request.form.get("unit", "").strip() or None,
        )
        if ok:
            conn.commit()
            conn.close()
            return redirect(url_for("asset_detail", asset_id=asset_id))
        detail = get_asset_detail(conn, asset_id)
        conn.close()
        return render_template("asset_edit.html", asset=detail["asset"], error=error)

    detail = get_asset_detail(conn, asset_id)
    conn.close()
    if detail is None:
        abort(404)
    return render_template("asset_edit.html", asset=detail["asset"], error=None)


@app.route("/assets/<int:asset_id>/delete", methods=["POST"])
def asset_delete(asset_id):
    conn = get_conn()
    delete_asset(conn, asset_id)
    conn.commit()
    conn.close()
    return redirect(url_for("dashboard"))


@app.route("/calibrations/<int:calibration_id>/edit", methods=["GET", "POST"])
def calibration_edit(calibration_id):
    conn = get_conn()

    # Load test point readings if this calibration has multiple test points
    tp_rows = conn.execute(
        "SELECT cr.test_point_id, tp.point_name, cr.measured_value, cr.uncertainty "
        "FROM calibration_readings cr "
        "JOIN test_points tp ON tp.id = cr.test_point_id "
        "WHERE cr.calibration_id = ? "
        "ORDER BY tp.display_order, tp.id",
        (calibration_id,)
    ).fetchall()
    
    test_point_readings = [{
        "tp_id": r[0], "point_name": r[1], "measured_value": r[2], "uncertainty": r[3]
    } for r in tp_rows]

    if request.method == "POST":
        conn.close()
        data = {"id": calibration_id}
        for key in ("cal_date", "cert_number", "measured_value", "mu_relative", "reviewer_comment", "pressure_hpa", "location"):
            if key in request.form:
                data[key] = request.form[key]
        data["is_adjusted"] = request.form.get("is_adjusted") == "on"
        data["excluded_from_regression"] = request.form.get("excluded_from_regression") == "on"
        data["test_point_readings"] = [
            {"tp_id": point["tp_id"], "measured_value": request.form[f"tp_meas_{point['tp_id']}"]}
            for point in test_point_readings if f"tp_meas_{point['tp_id']}" in request.form
        ]
        uploaded = request.files.get("reviewer_attachment")
        data["reviewer_url"] = request.form.get("reviewer_url", "").strip() or None
        new_attachment = None
        if uploaded and uploaded.filename:
            safe_name = secure_filename(uploaded.filename)
            if not safe_name:
                abort(400, "Invalid attachment filename.")
            Path(ATTACHMENTS_DIR).mkdir(parents=True, exist_ok=True)
            new_attachment = Path(ATTACHMENTS_DIR) / f"{calibration_id}_{uuid.uuid4().hex}_{safe_name}"
            uploaded.save(new_attachment)
            data["reviewer_attachment_path"] = str(new_attachment.resolve())
        elif request.form.get("remove_attachment") == "on":
            # Unlink from the record; retain the original file for recovery.
            data["reviewer_attachment_path"] = None
        result = desktop_service().save_calibration_edit(data)
        if not result["ok"] and new_attachment is not None:
            new_attachment.unlink(missing_ok=True)
        cal = desktop_service().get_calibration_for_edit(calibration_id)
        if result["ok"]:
            return redirect(url_for("asset_detail", asset_id=cal["asset_id"]))
        return render_template("calibration_edit.html", cal=cal, error=result.get("error"), test_point_readings=test_point_readings), 400

    cal = get_calibration(conn, calibration_id)
    conn.close()
    if cal is None:
        abort(404)
    return render_template("calibration_edit.html", cal=cal, error=None, test_point_readings=test_point_readings)


@app.route("/calibrations/<int:calibration_id>/delete", methods=["POST"])
def calibration_delete(calibration_id):
    conn = get_conn()
    cal = get_calibration(conn, calibration_id)
    if cal is None:
        conn.close()
        abort(404)
    asset_id = cal["asset_id"]
    delete_calibration(conn, calibration_id)
    conn.commit()
    conn.close()
    return redirect(url_for("asset_detail", asset_id=asset_id))


# -----------------------------------------------------------------------------
# Certificate Ingestion Routes
# -----------------------------------------------------------------------------
@app.route("/import", methods=["GET"])
def import_form():
    return render_template("import.html", error=None)


def _parse_one_cert(uploaded, conn) -> dict:
    original_filename = uploaded.filename
    token = uuid.uuid4().hex
    temp_path = os.path.join(PENDING_DIR, f"{token}.pdf")
    Path(PENDING_DIR).mkdir(parents=True, exist_ok=True)
    uploaded.save(temp_path)

    try:
        id_fields = extract_serial_and_date(temp_path)
    except Exception as e:
        os.remove(temp_path)
        cert_logger.error("Web import exception: %s", e)
        return {"ok": False, "filename": original_filename, "error": f"Failed to open PDF ({e})."}

    serial = id_fields.get("serial")
    cal_date = id_fields["cal_date"].date().isoformat() if id_fields.get("cal_date") else None

    asset = None
    if serial:
        asset_row = conn.execute(
            "SELECT id, serial, model, asset_number, nominal_ohms, source_sheet, category, unit FROM assets WHERE serial = ?",
            (serial,),
        ).fetchone()
        if asset_row:
            asset = {
                "id": asset_row[0], "serial": asset_row[1], "model": asset_row[2],
                "asset_number": asset_row[3], "nominal_ohms": asset_row[4], "source_sheet": asset_row[5],
                "category": asset_row[6], "unit": asset_row[7]
            }

    known_nominal = asset["nominal_ohms"] if asset else None
    try:
        measurement = extract_measurement(temp_path, known_nominal=known_nominal)
    except Exception as e:
        measurement = {"measured_value": None, "mu_relative": None, "warnings": []}

    cert_number_m = re.search(r"(WO-\d+)", original_filename)

    needs_manual = []
    if not serial or asset is None:
        needs_manual.append("serial")
    if not cal_date:
        needs_manual.append("cal_date")
    if measurement.get("measured_value") is None:
        needs_manual.append("measured_value")
    if measurement.get("mu_relative") is None:
        needs_manual.append("mu_relative")

    return {
        "ok": True, "filename": original_filename, "token": token, "asset": asset,
        "serial": serial or "", "cal_date": cal_date or "",
        "measured_value": measurement.get("measured_value"), "mu_relative": measurement.get("mu_relative"),
        "warnings": measurement.get("warnings", []),
        "needs_manual": needs_manual,
        "cert_number": cert_number_m.group(1) if cert_number_m else "",
    }


@app.route("/import/parse", methods=["POST"])
def import_parse():
    uploaded_files = [f for f in request.files.getlist("pdfs") if f and f.filename]
    if not uploaded_files:
        return render_template("import.html", error="Select at least one PDF certificate.")

    conn = get_conn()
    results = [_parse_one_cert(f, conn) for f in uploaded_files]
    conn.close()

    return render_template("import_review.html", results=results)


@app.route("/import/confirm", methods=["POST"])
def import_confirm():
    try:
        row_count = int(request.form["row_count"])
        if not 0 <= row_count <= 100:
            raise ValueError("Invalid upload count.")
    except (KeyError, ValueError):
        abort(400, "Invalid upload count.")
    summary = []
    last_asset_id = None
    svc = desktop_service()
    for i in range(row_count):
        filename = request.form.get(f"filename_{i}", f"Row {i+1}")
        try:
            temporary = pending_path(request.form.get(f"token_{i}"))
            if request.form.get(f"include_{i}") != "on":
                temporary.unlink(missing_ok=True)
                continue
            if not temporary.is_file():
                raise ValueError("Upload expired.")
            conn = get_conn()
            try:
                asset = conn.execute("SELECT id FROM assets WHERE serial = ?",
                    (request.form.get(f"serial_{i}", "").strip(),)).fetchone()
            finally:
                conn.close()
            if not asset:
                raise ValueError("The serial number is not registered.")
            result = svc.commit_imported_certificate({
                "asset_id": asset[0], "cal_date": request.form.get(f"cal_date_{i}", ""),
                "measured_value": request.form.get(f"measured_value_{i}"),
                "mu_relative": request.form.get(f"mu_relative_{i}"),
                "cert_number": request.form.get(f"cert_number_{i}"), "pdf_path": str(temporary),
            })
            if result["ok"]:
                temporary.unlink(missing_ok=True)
                last_asset_id = asset[0]
                summary.append({"filename": filename, "status": "imported", "detail": "Verified scalar calibration archived and imported."})
            else:
                summary.append({"filename": filename, "status": "error", "detail": result.get("error")})
        except (ValueError, OSError) as exc:
            summary.append({"filename": filename, "status": "error", "detail": str(exc)})
    return render_template("import_result.html", summary=summary, last_asset_id=last_asset_id)


@app.route("/import/cancel", methods=["POST"])
def import_cancel():
    try:
        row_count = int(request.form.get("row_count", 1))
        if not 0 <= row_count <= 100:
            raise ValueError("Invalid upload count.")
        for i in range(row_count):
            pending_path(request.form.get(f"token_{i}")).unlink(missing_ok=True)
    except (ValueError, OSError):
        abort(400, "Invalid upload token or count.")
    return redirect(url_for("import_form"))


# -----------------------------------------------------------------------------
# Application Server Startup
# -----------------------------------------------------------------------------
def _open_browser_soon(url: str):
    def _open():
        time.sleep(1.2)
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()


def main():
    for folder in (CERTS_DIR, ATTACHMENTS_DIR, PENDING_DIR, REPORTS_DIR, EXPORTS_DIR):
        os.makedirs(folder, exist_ok=True)
    _setup_logging()
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--network", action="store_true")
    args = ap.parse_args()

    if args.db:
        app.config["DB_PATH"] = str(Path(args.db).resolve())

    if args.network:
        ap.error("Network serving is disabled. Run this application locally.")
    host = "127.0.0.1"
    browser_url = f"http://127.0.0.1:{args.port}"

    print(f"Calibration Trending running at {browser_url}")
    print(f"Database: {app.config['DB_PATH']}")
    print("Press Ctrl+C to stop.")

    if not args.no_browser:
        _open_browser_soon(browser_url)

    if args.debug:
        app.run(debug=True, host=host, port=args.port, use_reloader=False)
        return

    try:
        from waitress import serve
        serve(app, host=host, port=args.port)
    except ImportError:
        app.run(host=host, port=args.port, use_reloader=False)


if __name__ == "__main__":
    main()