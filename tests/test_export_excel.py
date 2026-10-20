"""
tests/test_export_excel.py - Verifies exact file path preservation and
multi-point worksheet generation in Excel export operations.
"""

import sqlite3
import pytest
from pathlib import Path
import openpyxl

from db import connect, upsert_asset, insert_calibration, upsert_test_point, insert_calibration_reading
from export_excel import export_single_asset


@pytest.fixture
def populated_db(tmp_path):
    db_file = tmp_path / "test_export.db"
    conn = connect(str(db_file))

    # Add an AC Divider with 6 frequencies
    aid = upsert_asset(conn, "SN_DIV100", "ET 100mV", "PN030000", 10.0, category="ac_divider", unit="Ratio")
    tp1 = upsert_test_point(conn, aid, "1 kHz", "Ratio", 10.0, "Ratio", 1)
    tp2 = upsert_test_point(conn, aid, "20 kHz", "Ratio", 10.0, "Ratio", 2)
    tp3 = upsert_test_point(conn, aid, "100 kHz", "Ratio", 10.0, "Ratio", 3)

    cid1 = insert_calibration(conn, aid, "2024-01-01", 10.0003, 2.3e-5, "test")
    insert_calibration_reading(conn, cid1, tp1, 10.0003, uncertainty=23.0)
    insert_calibration_reading(conn, cid1, tp2, 10.0007, uncertainty=21.0)
    insert_calibration_reading(conn, cid1, tp3, 10.0003, uncertainty=21.0)

    cid2 = insert_calibration(conn, aid, "2025-01-01", 10.0004, 2.3e-5, "test")
    insert_calibration_reading(conn, cid2, tp1, 10.0004, uncertainty=23.0)
    insert_calibration_reading(conn, cid2, tp2, 10.0008, uncertainty=21.0)
    insert_calibration_reading(conn, cid2, tp3, 10.0004, uncertainty=21.0)

    return conn, aid


def test_export_single_asset_honors_exact_path(populated_db, tmp_path):
    """Ensures export_single_asset writes strictly to the chosen path without appending timestamp overrides."""
    conn, aid = populated_db
    custom_target = tmp_path / "Custom_Lab_Report_Named_By_Tech.xlsx"

    result_path = export_single_asset(conn, aid, out_path=str(custom_target))
    assert result_path == str(custom_target.resolve())
    assert custom_target.exists(), "Target file must exist with exact name chosen by user"

    # Verify openpyxl can load it and tabs correspond to characterized test points
    wb = openpyxl.load_workbook(str(custom_target))
    sheet_names = wb.sheetnames
    assert "1 kHz" in sheet_names
    assert "20 kHz" in sheet_names
    assert "100 kHz" in sheet_names

    # Verify data inside the first sheet
    ws = wb["1 kHz"]
    assert ws["B1"].value == "ET 100mV"  # Model
    assert ws["D1"].value == "PN030000"  # Equipment ID
    assert ws["F1"].value == "1 kHz"     # Test Point
    assert ws["F3"].value == 10.0003     # Reading 1
    assert ws["F4"].value == 10.0004     # Reading 2
    assert ws["G3"].value == 23.0        # Uncertainty in ppm