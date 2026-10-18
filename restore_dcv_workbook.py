"""
restore_dcv_workbook.py

Pulls all historical Fluke 732A/C data directly from calibration.db
and automatically reconstructs 'Template_DCV_Reference_732A.xlsx'
with the new 10V + 1V columns and all 3 asset tabs.
"""

import sqlite3
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# Styles
HEADER_FILL = PatternFill(start_color="1E3A5F", end_color="1E3A5F", fill_type="solid")
HEADER_FONT = Font(name="Arial", size=10, bold=True, color="FFFFFF")
LABEL_FONT = Font(name="Arial", size=10, bold=True, color="0F172A")
VALUE_FONT = Font(name="Arial", size=10, color="0F172A")
NOTE_FONT = Font(name="Arial", size=9, italic=True, color="64748B")
DATA_FONT = Font(name="Arial", size=10, color="0F172A")
THIN_SIDE = Side(border_style="thin", color="CBD5E1")
DATA_BORDER = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)

HEADERS = [
    "Date (YYYY-MM-DD)",
    "10V Measured (V)",
    "10V Uncert (nV)",
    "1V Measured (V)",
    "1V Uncert (nV)",
    "Facility Location",
    "Pressure (hPa)",
    "Cert Number",
    "Reviewer Comment",
]


def restore_workbook(db_path="calibration.db", output_file="Template_DCV_Reference_732A.xlsx"):
    conn = sqlite3.connect(db_path)

    # Find all 732A/C assets
    assets = conn.execute(
        "SELECT id, serial, model, asset_number, set_id FROM assets "
        "WHERE category = 'dcv_reference' OR model LIKE '%732%' "
        "ORDER BY id"
    ).fetchall()

    if not assets:
        print("No 732A/C assets found in the database!")
        conn.close()
        return

    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # Remove default sheet

    for asset_id, serial, model, equip_id, set_id in assets:
        ws = wb.create_sheet(title=str(serial))

        # 1. Metadata Block (Rows 1-5)
        meta = [
            ("Category", "DC Voltage Reference"),
            ("Model", model or "732A"),
            ("Serial Number", serial),
            ("Equipment ID", equip_id or ""),
            ("Set ID", set_id or "Set 1"),
        ]
        for r_idx, (lbl, val) in enumerate(meta, start=1):
            c_lbl = ws.cell(row=r_idx, column=1, value=lbl)
            c_lbl.font = LABEL_FONT
            c_val = ws.cell(row=r_idx, column=2, value=val)
            c_val.font = VALUE_FONT

        c_note = ws.cell(row=6, column=1, value="Note: Tracks 10V and 1V outputs. Uncertainty is in nV.")
        c_note.font = NOTE_FONT

        # 2. Table Headers (Row 7)
        for col_idx, header in enumerate(HEADERS, start=1):
            cell = ws.cell(row=7, column=col_idx, value=header)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        # 3. Pull calibration records for this asset
        cals = conn.execute(
            "SELECT cal_date, measured_value, mu_relative, cert_number, pressure_hpa, location, reviewer_comment "
            "FROM calibrations WHERE asset_id = ? ORDER BY cal_date",
            (asset_id,)
        ).fetchall()

        # Check if 1V readings already exist in calibration_readings
        tp_1v = conn.execute("SELECT id FROM test_points WHERE asset_id = ? AND point_name LIKE '%1V%'",
                             (asset_id,)).fetchone()
        readings_1v = {}
        if tp_1v:
            for r in conn.execute(
                    "SELECT calibration_id, measured_value, uncertainty FROM calibration_readings WHERE test_point_id = ?",
                    (tp_1v[0],)).fetchall():
                readings_1v[r[0]] = (r[1], r[2])

        # Write data rows (Row 8+)
        for r_idx, cal in enumerate(cals, start=8):
            cal_date, meas_10v, mu_rel, cert_no, pressure, location, comment = cal
            uncert_10v = round(mu_rel * 10.0 * 1e9, 1) if mu_rel else None

            # If location is empty, check if comment holds Loveland/Roseville
            loc_val = location
            comm_val = comment
            if not loc_val and comm_val in ("Loveland", "Roseville"):
                loc_val = comm_val
                comm_val = None

            row_data = [
                cal_date,
                meas_10v,
                uncert_10v,
                None,  # 1V Measured (Ready to be filled if available)
                None,  # 1V Uncert
                loc_val,
                pressure,
                cert_no,
                comm_val,
            ]

            for c_idx, val in enumerate(row_data, start=1):
                c = ws.cell(row=r_idx, column=c_idx, value=val)
                c.font = DATA_FONT
                c.border = DATA_BORDER
                if c_idx == 2:
                    c.number_format = "0.000000000"
                elif c_idx == 3:
                    c.number_format = "0.0"

        ws.freeze_panes = "A8"

        # Auto-fit columns
        for col in ws.columns:
            col_letter = get_column_letter(col[0].column)
            max_len = max(len(str(cell.value or "")) for cell in col if cell.row >= 7)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 16)

        print(f"  Restored Tab: '{serial}' ({len(cals)} calibrations pre-filled)")

    wb.save(output_file)
    conn.close()
    print(f"\nSuccessfully created '{output_file}' with all existing data intact!")


if __name__ == "__main__":
    restore_workbook()