"""
generate_blank_templates.py

Generates pre-formatted Excel template workbooks for entering historical
calibrations for:
  1. DC Voltage Reference (Fluke 732A / 732C)
  2. AC Voltage Dividers (ET 10mV / ET 100mV)
  3. Waveform Generator (Keysight 33622A)

Run with:
    python generate_blank_templates.py
"""

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# Palette & Fonts
HEADER_FILL = PatternFill(start_color="1E3A5F", end_color="1E3A5F", fill_type="solid")
HEADER_FONT = Font(name="Arial", size=10, bold=True, color="FFFFFF")
LABEL_FONT = Font(name="Arial", size=10, bold=True, color="0F172A")
VALUE_FONT = Font(name="Arial", size=10, color="0F172A")
SAMPLE_FONT = Font(name="Arial", size=10, color="475569", italic=True)
NOTE_FONT = Font(name="Arial", size=9, italic=True, color="64748B")

THIN_SIDE = Side(border_style="thin", color="CBD5E1")
DATA_BORDER = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)


def _apply_meta_block(ws, category: str, model: str, serial: str, equip_id: str, set_id: str, note: str):
    """Writes the standardized metadata header in rows 1-5."""
    meta = [
        ("Category", category),
        ("Model", model),
        ("Serial Number", serial),
        ("Equipment ID", equip_id),
        ("Set ID", set_id),
    ]
    for r_idx, (label, val) in enumerate(meta, start=1):
        c_lbl = ws.cell(row=r_idx, column=1, value=label)
        c_lbl.font = LABEL_FONT
        c_val = ws.cell(row=r_idx, column=2, value=val)
        c_val.font = VALUE_FONT

    c_note = ws.cell(row=6, column=1, value=f"Note: {note}")
    c_note.font = NOTE_FONT


def _auto_fit_columns(ws, min_width=13):
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = 0
        for cell in col:
            val_str = str(cell.value or "")
            if cell.row < 7 and col[0].column == 1:
                continue  # don't base column A solely on metadata length
            max_len = max(max_len, len(val_str))
        ws.column_dimensions[col_letter].width = max(max_len + 4, min_width)


# -----------------------------------------------------------------------------
# 1. DC Voltage Reference (Fluke 732A / 732C)
# -----------------------------------------------------------------------------
def create_dcv_template(filename="Template_DCV_Reference_732A.xlsx"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "732A Reference"

    _apply_meta_block(
        ws,
        category="DC Voltage Reference",
        model="732A",
        serial="3615000",
        equip_id="PN010064",
        set_id="Set 2",
        note="Tracks 10V and 1V outputs. Uncertainty is in nV.",
    )

    headers = [
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

    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=7, column=col_idx, value=header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # Sample row (from Keysight WO-01394837 Page 3)
    sample_row = [
        "2026-05-19",
        10.000083883, 35.0,
        0.999982438, 24.4,
        "Roseville", 1008,
        "WO-01394837",
        "Sample calibration baseline",
    ]
    for col_idx, val in enumerate(sample_row, start=1):
        cell = ws.cell(row=8, column=col_idx, value=val)
        cell.font = SAMPLE_FONT
        cell.border = DATA_BORDER
        if col_idx in [2, 4]:
            cell.number_format = "0.000000000"
        elif col_idx in [3, 5]:
            cell.number_format = "0.0"

    ws.freeze_panes = "A8"
    _auto_fit_columns(ws, min_width=16)
    wb.save(filename)
    print(f"Created: {filename}")


# -----------------------------------------------------------------------------
# 2. AC Voltage Divider (ET 10mV / ET 100mV)
# -----------------------------------------------------------------------------
def create_ac_divider_template(filename="Template_AC_Voltage_Divider_100mV.xlsx", model="ET 100mV", serial="PN030003", equip_id="960007"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "AC Divider Characterization"

    _apply_meta_block(
        ws,
        category="AC Voltage Divider",
        model=model,
        serial=serial,
        equip_id=equip_id,
        set_id="Set 1",
        note="6 frequency test points. Ratio is input/output. Uncertainty is in ppm.",
    )

    headers = [
        "Date (YYYY-MM-DD)",
        "Ratio (1 kHz)",
        "Uncert 1k (ppm)",
        "Ratio (20 kHz)",
        "Uncert 20k (ppm)",
        "Ratio (100 kHz)",
        "Uncert 100k (ppm)",
        "Ratio (300 kHz)",
        "Uncert 300k (ppm)",
        "Ratio (500 kHz)",
        "Uncert 500k (ppm)",
        "Ratio (1 MHz)",
        "Uncert 1M (ppm)",
        "Cert Number",
        "Reviewer Comment",
    ]

    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=7, column=col_idx, value=header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # Sample row (from Keysight WO-01257032 for ET 100mV)
    sample_row = [
        "2026-03-06",
        10.00037, 23.0,
        10.00078, 21.0,
        10.00033, 21.0,
        9.99952, 22.0,
        9.99817, 26.0,
        9.99308, 47.0,
        "WO-01257032",
        "Sample baseline with HP 3458A load",
    ]
    for col_idx, val in enumerate(sample_row, start=1):
        cell = ws.cell(row=8, column=col_idx, value=val)
        cell.font = SAMPLE_FONT
        cell.border = DATA_BORDER
        if col_idx in [2, 4, 6, 8, 10, 12]:
            cell.number_format = "0.00000"
        elif col_idx in [3, 5, 7, 9, 11, 13]:
            cell.number_format = "0.0"

    ws.freeze_panes = "A8"
    _auto_fit_columns(ws, min_width=16)
    wb.save(filename)
    print(f"Created: {filename}")


# -----------------------------------------------------------------------------
# 3. Waveform Generator (Keysight 33622A)
# -----------------------------------------------------------------------------
def create_waveform_gen_template(filename="Template_Waveform_Generator_33622A.xlsx"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "33622A Characterization"

    _apply_meta_block(
        ws,
        category="Waveform Generator",
        model="33622A",
        serial="MY53802790",
        equip_id="SL906099",
        set_id="Station B-1",
        note="All values in dB. 11 calibration factors (cf Data) and 4 characterized flatness errors.",
    )

    headers = [
        "Date (YYYY-MM-DD)",
        # 11 Calibration Factors (cf Data)
        "cf 10mV @ 4MHz (dB)",
        "cf 100mV @ 4MHz (dB)",
        "cf 100mV @ 8MHz (dB)",
        "cf 100mV @ 10MHz (dB)",
        "cf 1V @ 4MHz (dB)",
        "cf 1V @ 8MHz (dB)",
        "cf 1V @ 10MHz (dB)",
        "cf 3V @ 2MHz (dB)",
        "cf 3V @ 4MHz (dB)",
        "cf 3V @ 8MHz (dB)",
        "cf 3V @ 10MHz (dB)",
        # 4 Flatness Errors in dB
        "Flatness Error 2MHz (dB)",
        "Flatness Error 4MHz (dB)",
        "Flatness Error 8MHz (dB)",
        "Flatness Error 10MHz (dB)",
        # Cert & Comment
        "Cert Number",
        "Reviewer Comment",
    ]

    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=7, column=col_idx, value=header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # Sample row (from Keysight WO-01468931 Page 9)
    sample_row = [
        "2026-07-15",
        # 11 cf Data points
        -0.04378,
        -0.02783,
        -0.04926,
        -0.05720,
        -0.02972,
        -0.05126,
        -0.05900,
        -0.02996,
        -0.03175,
        -0.05397,
        -0.06295,
        # 4 Flatness error points
        -0.030,
        -0.033,
        -0.051,
        -0.060,
        # Metadata
        "WO-01468931",
        "Sample characterization with matched cable",
    ]

    for col_idx, val in enumerate(sample_row, start=1):
        cell = ws.cell(row=8, column=col_idx, value=val)
        cell.font = SAMPLE_FONT
        cell.border = DATA_BORDER
        if 2 <= col_idx <= 12:
            cell.number_format = "0.00000"
        elif 13 <= col_idx <= 16:
            cell.number_format = "0.000"

    ws.freeze_panes = "A8"
    _auto_fit_columns(ws, min_width=18)
    wb.save(filename)
    print(f"Created: {filename}")


if __name__ == "__main__":
    create_dcv_template()
    create_ac_divider_template()
    create_waveform_gen_template()
    print("\nAll 3 blank templates have been generated successfully.")