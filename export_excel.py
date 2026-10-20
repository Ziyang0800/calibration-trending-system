"""
export_excel.py - Generates standalone Excel workbook snapshots from calibration.db.
Supports Standard Resistors, DC Voltage Standards (10V & 1V), AC Dividers (6 frequencies),
and Waveform Generators (15 points) with exact user-selected path preservation.
"""

from datetime import date, datetime
from pathlib import Path
from typing import Optional, List

import openpyxl
from openpyxl.chart import ScatterChart, Series, Reference
from openpyxl.chart.marker import Marker
from openpyxl.utils import get_column_letter

from queries import get_asset_detail

BLOCK_WIDTH = 10
HEADER_ROW2 = [
    "Date", "Since Last Cal [Days]", "Accumulated [Days]", "Error / Dev",
    "Drift", "Measured Value", "Uncertainty", "Prediction", "95% Lower", "95% Upper"
]

LINE_COLORS = {"predicted": "404040", "lower": "0F9ED5", "upper": "E97132"}
MARKER_COLOR = "156082"


def _write_channel_block(ws, start_col: int, asset: dict, test_point_name: str, cals: list):
    """Writes a 10-column telemetry block with a scatter plot for a specific test point."""
    c = start_col
    ws.cell(row=1, column=c + 0, value="Model:")
    ws.cell(row=1, column=c + 1, value=asset["model"] or asset["serial"])
    ws.cell(row=1, column=c + 2, value="Equipment ID:")
    ws.cell(row=1, column=c + 3, value=asset["asset_number"] or "—")
    ws.cell(row=1, column=c + 4, value="Test Point:")
    ws.cell(row=1, column=c + 5, value=test_point_name)

    for i, header in enumerate(HEADER_ROW2):
        ws.cell(row=2, column=c + i, value=header)

    prev_date = None
    accumulated = 0
    cat = asset.get("category", "standard_resistor")

    for r, cal in enumerate(cals):
        row = 3 + r
        d = date.fromisoformat(cal["date"][:10])
        since = 0 if prev_date is None else (d - prev_date).days
        accumulated += since
        prev_date = d

        # Resolve correct uncertainty display
        uncert_val = None
        if cat == "dcv_reference":
            uncert_val = cal.get("uncertainty")  # Nanovolts
        elif cat == "ac_divider":
            uncert_val = cal.get("uncertainty")  # ppm
        elif cat == "waveform_generator":
            uncert_val = None  # WFG cf points do not report expanded uncertainty
        else:
            # Resistors: convert relative ratio to absolute ohms if available
            nom = asset.get("nominal_ohms") or 1.0
            uncert_val = round(cal.get("mu_relative", 0.0) * nom, 12) if cal.get("mu_relative") else None

        ws.cell(row=row, column=c + 0, value=d)
        ws.cell(row=row, column=c + 1, value=since)
        ws.cell(row=row, column=c + 2, value=accumulated)
        ws.cell(row=row, column=c + 3, value=cal.get("error_ppm"))
        ws.cell(row=row, column=c + 4, value=cal.get("drift_ppm"))
        ws.cell(row=row, column=c + 5, value=cal.get("measured_value"))
        ws.cell(row=row, column=c + 6, value=uncert_val)
        ws.cell(row=row, column=c + 7, value=cal.get("predicted"))
        ws.cell(row=row, column=c + 8, value=cal.get("lower"))
        ws.cell(row=row, column=c + 9, value=cal.get("upper"))

    n_rows = len(cals)
    if n_rows == 0:
        return

    last_row = 2 + n_rows
    x_col = c + 2       # Accumulated [Days]
    meas_col = c + 5
    pred_col = c + 7
    lower_col = c + 8
    upper_col = c + 9

    # Build Native Excel Scatter Chart
    chart = ScatterChart()
    chart.title = f"{asset['asset_number'] or asset['serial']} — {test_point_name}"
    chart.height, chart.width = 10, 18
    chart.x_axis.title = "Accumulated Days in Service"
    chart.y_axis.title = f"Reading ({asset.get('unit', '')})"

    x_ref = Reference(ws, min_col=x_col, min_row=3, max_row=last_row)

    # 1. Measured Data Points
    y_meas = Reference(ws, min_col=meas_col, min_row=3, max_row=last_row)
    s_meas = Series(y_meas, x_ref, title="Measured Reading")
    s_meas.marker = Marker(symbol="circle", size=6)
    s_meas.marker.graphicalProperties.solidFill = MARKER_COLOR
    s_meas.marker.graphicalProperties.line.noFill = True
    s_meas.graphicalProperties.line.noFill = True
    chart.series.append(s_meas)

    # 2. Linear Prediction & 95% Interval Lines (if present)
    has_prediction = any(c.get("predicted") is not None for c in cals)
    if has_prediction:
        def add_line(col_idx, name, color, dashed=False):
            y_ref = Reference(ws, min_col=col_idx, min_row=3, max_row=last_row)
            s = Series(y_ref, x_ref, title=name)
            s.marker = Marker(symbol="none")
            s.graphicalProperties.line.solidFill = color
            s.graphicalProperties.line.width = 15000
            if dashed:
                s.graphicalProperties.line.dashStyle = "dash"
            chart.series.append(s)

        add_line(pred_col, "Linear Prediction", LINE_COLORS["predicted"], dashed=True)
        add_line(lower_col, "95% Lower Limit", LINE_COLORS["lower"])
        add_line(upper_col, "95% Upper Limit", LINE_COLORS["upper"])

    ws.add_chart(chart, f"{get_column_letter(c)}{last_row + 3}")


def export_single_asset(conn, asset_id: int, out_path: Optional[str] = None, out_dir: str = "exports") -> str:
    """
    Exports a single asset with tabs for every characterized test point.
    Writes strictly to out_path when provided by the user.
    """
    row = conn.execute("SELECT serial, model, category FROM assets WHERE id = ?", (asset_id,)).fetchone()
    if row is None:
        raise ValueError(f"Asset ID {asset_id} does not exist.")
    serial, model, category = row

    if out_path:
        dest = Path(out_path).resolve()
        if not dest.name.lower().endswith(".xlsx"):
            dest = dest.with_suffix(".xlsx")
    else:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        dest = (Path(out_dir) / f"asset_{serial}_{datetime.now():%Y%m%d_%H%M%S}.xlsx").resolve()

    dest.parent.mkdir(parents=True, exist_ok=True)

    # Query all test points for this asset
    tp_rows = conn.execute(
        "SELECT id, point_name FROM test_points WHERE asset_id = ? ORDER BY display_order, id",
        (asset_id,)
    ).fetchall()

    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # Remove default blank sheet

    if tp_rows and len(tp_rows) > 1:
        # Multi-Point Standard (732A, AC Divider, 33622A): Create a tab per test point
        for tp_id, tp_name in tp_rows:
            detail = get_asset_detail(conn, asset_id, selected_point_id=tp_id)
            safe_title = tp_name.replace("/", "-").replace(":", "-")[:31]
            ws = wb.create_sheet(title=safe_title)
            _write_channel_block(ws, start_col=1, asset=detail["asset"],
                                 test_point_name=tp_name, cals=detail["calibrations"])
    else:
        # Single-Point Standard (Standard Resistors)
        detail = get_asset_detail(conn, asset_id)
        ws = wb.create_sheet(title=f"{serial}"[:31])
        _write_channel_block(ws, start_col=1, asset=detail["asset"],
                             test_point_name=detail["asset"]["source_sheet"] or "Nominal",
                             cals=detail["calibrations"])

    wb.save(str(dest))
    return str(dest)


def export_all_assets(conn, out_path: Optional[str] = None, out_dir: str = "exports") -> str:
    """Exports all laboratory assets grouped by category and sheet name."""
    if out_path:
        dest = Path(out_path).resolve()
        if not dest.name.lower().endswith(".xlsx"):
            dest = dest.with_suffix(".xlsx")
    else:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        dest = (Path(out_dir) / f"calibration_export_{datetime.now():%Y%m%d_%H%M%S}.xlsx").resolve()

    dest.parent.mkdir(parents=True, exist_ok=True)

    asset_ids = [r[0] for r in conn.execute("SELECT id FROM assets ORDER BY category, source_sheet, serial").fetchall()]
    
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    by_sheet = {}
    for aid in asset_ids:
        detail = get_asset_detail(conn, aid)
        if not detail:
            continue
        sheet_name = detail["asset"]["source_sheet"] or detail["asset"]["category"] or "Standards"
        by_sheet.setdefault(sheet_name[:31], []).append(detail)

    for sheet_name, details in by_sheet.items():
        ws = wb.create_sheet(title=sheet_name)
        col = 1
        for d in details:
            tp_name = d["active_test_point"]["point_name"] if d.get("active_test_point") else (d["asset"]["source_sheet"] or "Nominal")
            _write_channel_block(ws, col, d["asset"], tp_name, d["calibrations"])
            col += BLOCK_WIDTH + 1  # 1 blank column gap between asset blocks

    wb.save(str(dest))
    return str(dest)