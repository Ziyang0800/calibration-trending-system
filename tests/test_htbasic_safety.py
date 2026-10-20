"""
tests/test_htbasic_safety.py - Verifies that HTBasic generation strictly blocks
missing data and never injects hardcoded fallback values into production files.
"""

import sqlite3
import pytest
from htbasic_export import (
    validate_required_resistors,
    generate_all_files,
    generate_divmeans,
    generate_33622a_extended,
)


@pytest.fixture
def empty_db(tmp_path):
    db_file = tmp_path / "test_safety.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("""
        CREATE TABLE assets (
            id INTEGER PRIMARY KEY, serial TEXT, model TEXT,
            asset_number TEXT, nominal_ohms REAL, source_workbook TEXT,
            source_sheet TEXT, set_id TEXT, category TEXT, unit TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE calibrations (
            id INTEGER PRIMARY KEY, asset_id INTEGER, cert_number TEXT,
            cal_date TEXT, measured_value REAL, mu_relative REAL,
            source TEXT, cert_pdf_path TEXT, reviewer_comment TEXT,
            excluded_from_regression INTEGER DEFAULT 0, is_adjusted INTEGER DEFAULT 0,
            location TEXT, pressure_hpa REAL
        )
    """)
    conn.execute("""
        CREATE TABLE test_points (
            id INTEGER PRIMARY KEY, asset_id INTEGER, point_name TEXT,
            group_name TEXT, nominal_value REAL, unit TEXT, display_order INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE calibration_readings (
            id INTEGER PRIMARY KEY, calibration_id INTEGER, test_point_id INTEGER,
            measured_value REAL, secondary_value REAL, uncertainty REAL
        )
    """)
    conn.commit()
    return conn


def test_missing_divider_strictly_raises_error(empty_db):
    """Ensures generate_divmeans raises ValueError instead of using 100.9039 fallback."""
    with pytest.raises(ValueError) as excinfo:
        generate_divmeans(empty_db, "Set 1")
    assert "missing live calibration ratios" in str(excinfo.value)


def test_missing_wfg_strictly_raises_error(empty_db):
    """Ensures generate_33622a_extended raises ValueError instead of writing 0.0 dB."""
    with pytest.raises(ValueError) as excinfo:
        generate_33622a_extended(empty_db, "SG53800187")
    assert "not registered in the database" in str(excinfo.value) or "no recorded calibration history" in str(excinfo.value)


def test_preflight_validator_blocks_package(empty_db):
    """Ensures generate_all_files refuses to compile when standards are missing."""
    with pytest.raises(ValueError) as excinfo:
        generate_all_files(empty_db, "Set 1", "PN010034", "SG53800187")
    assert "Pre-flight verification failed" in str(excinfo.value)