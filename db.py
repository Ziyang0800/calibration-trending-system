"""
db.py - SQLite helper for calibration trending database.
Supports Standard Resistors, DC Voltage References, AC Voltage Dividers, and Waveform Generators.
"""

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    if SCHEMA_PATH.exists():
        try:
            conn.executescript(SCHEMA_PATH.read_text())
        except sqlite3.OperationalError:
            pass
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection):
    """Safely upgrades database schema with zero data loss."""
    existing_asset_cols = {row[1] for row in conn.execute("PRAGMA table_info(assets)")}
    if "set_id" not in existing_asset_cols:
        conn.execute("ALTER TABLE assets ADD COLUMN set_id TEXT")
    if "category" not in existing_asset_cols:
        conn.execute("ALTER TABLE assets ADD COLUMN category TEXT DEFAULT 'standard_resistor'")
    if "unit" not in existing_asset_cols:
        conn.execute("ALTER TABLE assets ADD COLUMN unit TEXT DEFAULT 'Ω'")

    existing_cal_cols = {row[1] for row in conn.execute("PRAGMA table_info(calibrations)")}
    if "reviewer_comment" not in existing_cal_cols:
        conn.execute("ALTER TABLE calibrations ADD COLUMN reviewer_comment TEXT")
    if "excluded_from_regression" not in existing_cal_cols:
        conn.execute("ALTER TABLE calibrations ADD COLUMN excluded_from_regression INTEGER NOT NULL DEFAULT 0")
    if "reviewer_attachment_path" not in existing_cal_cols:
        conn.execute("ALTER TABLE calibrations ADD COLUMN reviewer_attachment_path TEXT")
    if "reviewer_url" not in existing_cal_cols:
        conn.execute("ALTER TABLE calibrations ADD COLUMN reviewer_url TEXT")
    if "pressure_hpa" not in existing_cal_cols:
        conn.execute("ALTER TABLE calibrations ADD COLUMN pressure_hpa REAL")
    if "is_adjusted" not in existing_cal_cols:
        conn.execute("ALTER TABLE calibrations ADD COLUMN is_adjusted INTEGER NOT NULL DEFAULT 0")
    if "location" not in existing_cal_cols:
        conn.execute("ALTER TABLE calibrations ADD COLUMN location TEXT")

    conn.execute("""
    CREATE TABLE IF NOT EXISTS test_points (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
        point_name TEXT NOT NULL,
        group_name TEXT,
        nominal_value REAL,
        unit TEXT NOT NULL,
        display_order INTEGER DEFAULT 0,
        UNIQUE(asset_id, point_name)
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS calibration_readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        calibration_id INTEGER NOT NULL REFERENCES calibrations(id) ON DELETE CASCADE,
        test_point_id INTEGER NOT NULL REFERENCES test_points(id) ON DELETE CASCADE,
        measured_value REAL NOT NULL,
        secondary_value REAL,
        uncertainty REAL,
        excluded_from_regression INTEGER NOT NULL DEFAULT 0,
        UNIQUE(calibration_id, test_point_id)
    )
    """)

    conn.commit()


def upsert_asset(conn, serial: str, model: str, asset_number: str, nominal_ohms: float,
                 source_workbook: str = None, source_sheet: str = None,
                 category: str = "standard_resistor", unit: str = "Ω", set_id: str = None) -> int:
    row = conn.execute("SELECT id, model, asset_number, category, unit, set_id FROM assets WHERE serial = ?", (serial,)).fetchone()
    if row:
        asset_id, ex_model, ex_asset_no, ex_cat, ex_unit, ex_set = row
        updates, params = [], []
        if ex_model is None and model is not None:
            updates.append("model = ?"); params.append(model)
        if ex_asset_no is None and asset_number is not None:
            updates.append("asset_number = ?"); params.append(asset_number)
        if ex_cat is None and category is not None:
            updates.append("category = ?"); params.append(category)
        if ex_unit is None and unit is not None:
            updates.append("unit = ?"); params.append(unit)
        if ex_set is None and set_id is not None:
            updates.append("set_id = ?"); params.append(set_id)
        if updates:
            params.append(asset_id)
            conn.execute(f"UPDATE assets SET {', '.join(updates)} WHERE id = ?", params)
        return asset_id

    cur = conn.execute(
        "INSERT INTO assets (serial, model, asset_number, nominal_ohms, source_workbook, source_sheet, category, unit, set_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (serial, model, asset_number, nominal_ohms, source_workbook, source_sheet, category, unit, set_id),
    )
    return cur.lastrowid


def insert_calibration(conn, asset_id: int, cal_date: str, measured_value: float, mu_relative: float,
                       source: str, cert_number: str = None, cert_pdf_path: str = None,
                       pressure_hpa: float = None, is_adjusted: bool = False,
                       reviewer_comment: str = None, location: str = None) -> int:
    try:
        cur = conn.execute(
            "INSERT INTO calibrations (asset_id, cert_number, cal_date, measured_value, mu_relative, "
            "source, cert_pdf_path, pressure_hpa, is_adjusted, reviewer_comment, location) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (asset_id, cert_number, cal_date, measured_value, mu_relative, source, cert_pdf_path,
             pressure_hpa, int(is_adjusted), reviewer_comment, location),
        )
        return cur.lastrowid
    except sqlite3.IntegrityError:
        row = conn.execute("SELECT id FROM calibrations WHERE asset_id = ? AND cal_date = ?", (asset_id, cal_date)).fetchone()
        if row:
            cal_id = row[0]
            conn.execute(
                "UPDATE calibrations SET measured_value = ?, mu_relative = ?, pressure_hpa = COALESCE(?, pressure_hpa), "
                "is_adjusted = ?, reviewer_comment = COALESCE(?, reviewer_comment), location = COALESCE(?, location) WHERE id = ?",
                (measured_value, mu_relative, pressure_hpa, int(is_adjusted), reviewer_comment, location, cal_id)
            )
            return cal_id
        return None


def upsert_test_point(conn, asset_id: int, point_name: str, group_name: str, nominal_value: float, unit: str, display_order: int = 0) -> int:
    row = conn.execute("SELECT id FROM test_points WHERE asset_id = ? AND point_name = ?", (asset_id, point_name)).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO test_points (asset_id, point_name, group_name, nominal_value, unit, display_order) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (asset_id, point_name, group_name, nominal_value, unit, display_order)
    )
    return cur.lastrowid


def insert_calibration_reading(conn, calibration_id: int, test_point_id: int, measured_value: float, secondary_value: float = None, uncertainty: float = None) -> bool:
    try:
        conn.execute(
            "INSERT INTO calibration_readings (calibration_id, test_point_id, measured_value, secondary_value, uncertainty) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(calibration_id, test_point_id) DO UPDATE SET "
            "measured_value=excluded.measured_value, secondary_value=excluded.secondary_value, uncertainty=excluded.uncertainty",
            (calibration_id, test_point_id, measured_value, secondary_value, uncertainty)
        )
        return True
    except sqlite3.IntegrityError:
        return False


def get_calibration(conn, calibration_id: int):
    row = conn.execute(
        "SELECT id, asset_id, cal_date, measured_value, mu_relative, cert_number, cert_pdf_path, "
        "reviewer_comment, excluded_from_regression, reviewer_attachment_path, reviewer_url, "
        "pressure_hpa, is_adjusted "
        "FROM calibrations WHERE id = ?", (calibration_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0], "asset_id": row[1], "cal_date": row[2], "measured_value": row[3],
        "mu_relative": row[4], "cert_number": row[5], "cert_pdf_path": row[6],
        "reviewer_comment": row[7], "excluded_from_regression": bool(row[8]),
        "reviewer_attachment_path": row[9], "reviewer_url": row[10],
        "pressure_hpa": row[11], "is_adjusted": bool(row[12]),
    }


def update_calibration(conn, calibration_id: int, cal_date: str, measured_value: float, mu_relative: float,
                       reviewer_comment: str = None, excluded_from_regression: bool = False,
                       reviewer_attachment_path: str = None, keep_existing_attachment: bool = False,
                       reviewer_url: str = None, pressure_hpa: float = None, is_adjusted: bool = False,
                       location: str = None) -> tuple:
    row = conn.execute("SELECT asset_id FROM calibrations WHERE id = ?", (calibration_id,)).fetchone()
    if row is None:
        return False, "Calibration not found."
    asset_id = row[0]
    clash = conn.execute(
        "SELECT id FROM calibrations WHERE asset_id = ? AND cal_date = ? AND id != ?",
        (asset_id, cal_date, calibration_id),
    ).fetchone()
    if clash:
        return False, f"This asset already has a calibration dated {cal_date}."

    if keep_existing_attachment:
        conn.execute(
            "UPDATE calibrations SET cal_date = ?, measured_value = ?, mu_relative = ?, "
            "reviewer_comment = ?, excluded_from_regression = ?, reviewer_url = ?, "
            "pressure_hpa = ?, is_adjusted = ?, location = ? WHERE id = ?",
            (cal_date, measured_value, mu_relative, reviewer_comment, int(excluded_from_regression),
             reviewer_url, pressure_hpa, int(is_adjusted), location, calibration_id),
        )
    else:
        conn.execute(
            "UPDATE calibrations SET cal_date = ?, measured_value = ?, mu_relative = ?, "
            "reviewer_comment = ?, excluded_from_regression = ?, reviewer_attachment_path = ?, "
            "reviewer_url = ?, pressure_hpa = ?, is_adjusted = ?, location = ? WHERE id = ?",
            (cal_date, measured_value, mu_relative, reviewer_comment, int(excluded_from_regression),
             reviewer_attachment_path, reviewer_url, pressure_hpa, int(is_adjusted), location, calibration_id),
        )
    return True, None

def update_asset(conn, asset_id: int, serial: str, model: str, asset_number: str, nominal_ohms: float,
                 set_id: str = None, category: str = None, unit: str = None) -> tuple:
    clash = conn.execute("SELECT id FROM assets WHERE serial = ? AND id != ?", (serial, asset_id)).fetchone()
    if clash:
        return False, f"Serial {serial} is already used by another asset (id {clash[0]})."
    conn.execute(
        "UPDATE assets SET serial = ?, model = ?, asset_number = ?, nominal_ohms = ?, set_id = ?, "
        "category = COALESCE(?, category), unit = COALESCE(?, unit) WHERE id = ?",
        (serial, model, asset_number, nominal_ohms, set_id, category, unit, asset_id),
    )
    return True, None


def bulk_assign_sets(conn, serial_to_set: dict) -> dict:
    updated, not_found = [], []
    for serial, set_id in serial_to_set.items():
        cur = conn.execute("UPDATE assets SET set_id = ? WHERE serial = ?", (set_id, str(serial)))
        (updated if cur.rowcount > 0 else not_found).append(serial)
    conn.commit()
    return {"updated": updated, "not_found": not_found}


def delete_asset(conn, asset_id: int):
    conn.execute("DELETE FROM calibrations WHERE asset_id = ?", (asset_id,))
    conn.execute("DELETE FROM test_points WHERE asset_id = ?", (asset_id,))
    conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))


def delete_calibration(conn, calibration_id: int):
    conn.execute("DELETE FROM calibrations WHERE id = ?", (calibration_id,))