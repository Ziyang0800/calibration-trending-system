"""
export_excel.py - Phase 5.

Generates a fresh Excel workbook from the database on demand - this is a
snapshot/report, not something meant to be hand-edited and fed back in
(the database is the source of truth now, not the exported file).

Layout mirrors the original template for familiarity: one sheet per
decade, asset blocks of 10 columns side by side (Date, Since Last Cal,
Accumulated, Error, Drifted, Measured, MU, Prediction, Lower, Upper),
plus a scatter chart per asset - written with VISIBLE line colors from
the start (see the chart-color bug we found and fixed in Phase 1/2 on
the original workbook - not repeating that here).

Usage (also called from MainApp.py's /export routes):
    from export_excel import export_all_assets, export_single_asset
    path = export_all_assets(conn, out_dir="exports")
    path = export_single_asset(conn, asset_id, out_dir="exports")
"""

from datetime import date, datetime
from pathlib import Path

import openpyxl
from openpyxl.chart import ScatterChart, Series, Reference
from openpyxl.chart.marker import Marker
from openpyxl.utils import get_column_letter

from queries import get_asset_detail

BLOCK_WIDTH = 10
BLOCK_GAP = 1  # blank column between asset blocks
HEADER_ROW2 = ["Date", "Since Last Cal [Days]", "Accumulated [Days]", "Error [PPM]",
               "Drifted [PPM]", "Measured Value", "MU (K =2)", "Prediction", "Lower", "Upper"]

LINE_COLORS = {"predicted": "404040", "lower": "0F9ED5", "upper": "E97132"}
MARKER_COLOR = "156082"


def _write_asset_block(ws, start_col: int, detail: dict):
    asset = detail["asset"]
    cals = detail["calibrations"]

    c = start_col
    ws.cell(row=1, column=c + 1, value=asset["model"])
    ws.cell(row=1, column=c + 2, value=asset["asset_number"])
    ws.cell(row=1, column=c + 3, value=asset["serial"])
    for i, header in enumerate(HEADER_ROW2):
        ws.cell(row=2, column=c + i, value=header)

    prev_date = None
    accumulated = 0.0
    for r, cal in enumerate(cals):
        row = 3 + r
        d = date.fromisoformat(cal["date"])
        since = 0 if prev_date is None else (d - prev_date).days
        accumulated += since
        prev_date = d

        ws.cell(row=row, column=c + 0, value=d)
        ws.cell(row=row, column=c + 1, value=since)
        ws.cell(row=row, column=c + 2, value=accumulated)
        ws.cell(row=row, column=c + 3, value=cal.get("error_ppm"))
        ws.cell(row=row, column=c + 4, value=cal.get("drift_ppm"))
        ws.cell(row=row, column=c + 5, value=cal["measured_value"])
        ws.cell(row=row, column=c + 6, value=cal["mu_relative"] * asset["nominal_ohms"])
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

    chart = ScatterChart()
    chart.title = f"{asset['asset_number'] or asset['serial']} Historical vs Prediction"
    chart.height, chart.width = 8, 16

    x_ref = Reference(ws, min_col=x_col, min_row=3, max_row=last_row)

    def add_line_series(col, name, color, dashed=False):
        y_ref = Reference(ws, min_col=col, min_row=3, max_row=last_row)
        s = Series(y_ref, x_ref, title=name)
        s.marker = Marker(symbol="none")
        s.graphicalProperties.line.solidFill = color
        s.graphicalProperties.line.width = 15000
        if dashed:
            s.graphicalProperties.line.dashStyle = "dash"
        s.smooth = False
        chart.series.append(s)

    # measured points (markers only, no line)
    y_ref = Reference(ws, min_col=meas_col, min_row=3, max_row=last_row)
    measured_series = Series(y_ref, x_ref, title="Measured Value")
    measured_series.marker = Marker(symbol="circle", size=6)
    measured_series.marker.graphicalProperties.solidFill = MARKER_COLOR
    measured_series.marker.graphicalProperties.line.noFill = True
    measured_series.graphicalProperties.line.noFill = True
    chart.series.append(measured_series)

    add_line_series(pred_col, "Prediction", LINE_COLORS["predicted"], dashed=True)
    add_line_series(lower_col, "Lower Bound", LINE_COLORS["lower"])
    add_line_series(upper_col, "Upper Bound", LINE_COLORS["upper"])

    chart.x_axis.title = "Accumulated Days"
    chart.y_axis.title = "Ohms"
    ws.add_chart(chart, f"{get_column_letter(c)}{last_row + 3}")


def _build_workbook(conn, asset_ids: list) -> openpyxl.Workbook:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    by_sheet = {}
    for asset_id in asset_ids:
        detail = get_asset_detail(conn, asset_id)
        if detail is None:
            continue
        sheet_name = detail["asset"]["source_sheet"] or "Assets"
        by_sheet.setdefault(sheet_name, []).append(detail)

    for sheet_name, details in by_sheet.items():
        ws = wb.create_sheet(title=sheet_name[:31])
        col = 1
        for detail in details:
            _write_asset_block(ws, col, detail)
            col += BLOCK_WIDTH + BLOCK_GAP

    return wb


def export_all_assets(conn, out_dir: str = "exports") -> str:
    asset_ids = [r[0] for r in conn.execute("SELECT id FROM assets ORDER BY source_sheet, serial")]
    wb = _build_workbook(conn, asset_ids)
    Path(out_dir).mkdir(exist_ok=True)
    path = str(Path(out_dir) / f"calibration_export_{datetime.now():%Y%m%d_%H%M%S}.xlsx")
    wb.save(path)
    return path


def export_single_asset(conn, asset_id: int, out_dir: str = "exports") -> str:
    row = conn.execute("SELECT serial FROM assets WHERE id = ?", (asset_id,)).fetchone()
    if row is None:
        return None
    wb = _build_workbook(conn, [asset_id])
    Path(out_dir).mkdir(exist_ok=True)
    path = str(Path(out_dir) / f"asset_{row[0]}_{datetime.now():%Y%m%d_%H%M%S}.xlsx")
    wb.save(path)
    return path
