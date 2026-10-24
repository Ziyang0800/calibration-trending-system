"""
db.py - Hardened SQLite storage engine for metrology calibration trending.
Supports Standard Resistors, DC Voltage References, AC Voltage Dividers, and Waveform Generators.
"""

import sqlite3
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

SCHEMA_PATH = Path(__file__).parent / "schema.sql"
CURRENT_SCHEMA_VERSION = 2


def connect(db_path: str) -> sqlite3.Connection:
    """Connects to SQLite with WAL mode, foreign keys, and safe transactional migrations."""
    conn = sqlite3.connect(db_path, timeout=30.0)
    try:
        if _get_schema_version(conn) > CURRENT_SCHEMA_VERSION:
            raise ValueError("This database requires a newer application version.")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        with conn:
            _init_and_migrate(conn)
        return conn
    except Exception:
        conn.close()
        raise


def _get_schema_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(f"PRAGMA user_version = {int(version)}")


def _init_and_migrate(conn: sqlite3.Connection) -> None:
    """Explicit, transactional migrations from baseline to v2."""
    version = _get_schema_version(conn)

    # Initial base schema creation if fresh DB
    table_count = conn.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name IN ('assets', 'calibrations')"
    ).fetchone()[0]

    if table_count < 2 and SCHEMA_PATH.exists():
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    # Migration Step: Baseline -> Version 1 (Add modern metadata columns)
    if version < 1:
        asset_cols = {row[1] for row in conn.execute("PRAGMA table_info(assets)")}
        if "set_id" not in asset_cols:
            conn.execute("ALTER TABLE assets ADD COLUMN set_id TEXT")
        if "category" not in asset_cols:
            conn.execute("ALTER TABLE assets ADD COLUMN category TEXT DEFAULT 'standard_resistor'")
        if "unit" not in asset_cols:
            conn.execute("ALTER TABLE assets ADD COLUMN unit TEXT DEFAULT 'Ω'")

        cal_cols = {row[1] for row in conn.execute("PRAGMA table_info(calibrations)")}
        if "reviewer_comment" not in cal_cols:
            conn.execute("ALTER TABLE calibrations ADD COLUMN reviewer_comment TEXT")
        if "excluded_from_regression" not in cal_cols:
            conn.execute("ALTER TABLE calibrations ADD COLUMN excluded_from_regression INTEGER NOT NULL DEFAULT 0")
        if "reviewer_attachment_path" not in cal_cols:
            conn.execute("ALTER TABLE calibrations ADD COLUMN reviewer_attachment_path TEXT")
        if "reviewer_url" not in cal_cols:
            conn.execute("ALTER TABLE calibrations ADD COLUMN reviewer_url TEXT")
        if "pressure_hpa" not in cal_cols:
            conn.execute("ALTER TABLE calibrations ADD COLUMN pressure_hpa REAL")
        if "is_adjusted" not in cal_cols:
            conn.execute("ALTER TABLE calibrations ADD COLUMN is_adjusted INTEGER NOT NULL DEFAULT 0")
        if "location" not in cal_cols:
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
        _set_schema_version(conn, 1)
        version = 1

    # Migration Step: Version 1 -> Version 2 (Performance indexes)
    if version < 2:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_calibrations_asset_date ON calibrations(asset_id, cal_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_readings_cal_tp ON calibration_readings(calibration_id, test_point_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_test_points_asset ON test_points(asset_id)")
        _set_schema_version(conn, 2)


def upsert_asset(conn: sqlite3.Connection, serial: str, model: str, asset_number: str, nominal_ohms: float,
                 source_workbook: str = None, source_sheet: str = None,
                 category: str = "standard_resistor", unit: str = "Ω", set_id: str = None) -> int:
    with conn:
        row = conn.execute(
            "SELECT id, model, asset_number, category, unit, set_id FROM assets WHERE serial = ?",
            (serial,)
        ).fetchone()

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


def insert_calibration(conn: sqlite3.Connection, asset_id: int, cal_date: str, measured_value: float, mu_relative: float,
                       source: str, cert_number: str = None, cert_pdf_path: str = None,
                       pressure_hpa: float = None, is_adjusted: bool = False,
                       reviewer_comment: str = None, location: str = None,
                       allow_overwrite: bool = False) -> Optional[int]:
    """
    Inserts a calibration event.
    If a record with matching (asset_id, cal_date) already exists:
      - If allow_overwrite is False: returns None (clean duplicate, zero data destruction).
      - If allow_overwrite is True: explicitly updates the record and returns the existing ID.
    """
    with conn:
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
            # Only classify a real (asset_id, cal_date) collision as a duplicate.
            # Foreign-key / NOT NULL / other integrity failures must remain visible.
            row = conn.execute(
                "SELECT id FROM calibrations WHERE asset_id = ? AND cal_date = ?",
                (asset_id, cal_date)
            ).fetchone()
            if row is None:
                raise
            if not allow_overwrite:
                return None  # Duplicate date: preserve existing data.
            cal_id = row[0]
            conn.execute(
                "UPDATE calibrations SET measured_value = ?, mu_relative = ?, pressure_hpa = COALESCE(?, pressure_hpa), "
                "is_adjusted = ?, reviewer_comment = COALESCE(?, reviewer_comment), location = COALESCE(?, location), "
                "cert_number = COALESCE(?, cert_number), cert_pdf_path = COALESCE(?, cert_pdf_path) WHERE id = ?",
                (measured_value, mu_relative, pressure_hpa, int(is_adjusted), reviewer_comment, location,
                 cert_number, cert_pdf_path, cal_id)
            )
            return cal_id


def upsert_test_point(conn: sqlite3.Connection, asset_id: int, point_name: str, group_name: str,
                      nominal_value: float, unit: str, display_order: int = 0) -> int:
    with conn:
        row = conn.execute(
            "SELECT id FROM test_points WHERE asset_id = ? AND point_name = ?",
            (asset_id, point_name)
        ).fetchone()
        if row:
            return row[0]
        cur = conn.execute(
            "INSERT INTO test_points (asset_id, point_name, group_name, nominal_value, unit, display_order) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (asset_id, point_name, group_name, nominal_value, unit, display_order)
        )
        return cur.lastrowid


def insert_calibration_reading(conn: sqlite3.Connection, calibration_id: int, test_point_id: int,
                               measured_value: float, secondary_value: float = None, uncertainty: float = None) -> bool:
    with conn:
        conn.execute(
            "INSERT INTO calibration_readings (calibration_id, test_point_id, measured_value, secondary_value, uncertainty) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(calibration_id, test_point_id) DO UPDATE SET "
            "measured_value=excluded.measured_value, secondary_value=excluded.secondary_value, uncertainty=excluded.uncertainty",
            (calibration_id, test_point_id, measured_value, secondary_value, uncertainty)
        )
        return True


def get_calibration(conn: sqlite3.Connection, calibration_id: int) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        "SELECT id, asset_id, cal_date, measured_value, mu_relative, cert_number, cert_pdf_path, "
        "reviewer_comment, excluded_from_regression, reviewer_attachment_path, reviewer_url, "
        "pressure_hpa, is_adjusted, location "
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
        "location": row[13],
    }


def update_calibration(conn: sqlite3.Connection, calibration_id: int, cal_date: str, measured_value: float, mu_relative: float,
                       reviewer_comment: str = None, excluded_from_regression: bool = False,
                       reviewer_attachment_path: str = None, keep_existing_attachment: bool = False,
                       reviewer_url: str = None, pressure_hpa: float = None, is_adjusted: bool = False,
                       location: str = None) -> Tuple[bool, Optional[str]]:
    with conn:
        row = conn.execute("SELECT asset_id FROM calibrations WHERE id = ?", (calibration_id,)).fetchone()
        if row is None:
            return False, "Calibration record not found."
        asset_id = row[0]

        clash = conn.execute(
            "SELECT id FROM calibrations WHERE asset_id = ? AND cal_date = ? AND id != ?",
            (asset_id, cal_date, calibration_id),
        ).fetchone()
        if clash:
            return False, f"This standard already has another calibration dated {cal_date}."

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


def update_asset(conn: sqlite3.Connection, asset_id: int, serial: str, model: str, asset_number: str, nominal_ohms: float,
                 set_id: str = None, category: str = None, unit: str = None) -> Tuple[bool, Optional[str]]:
    with conn:
        clash = conn.execute("SELECT id FROM assets WHERE serial = ? AND id != ?", (serial, asset_id)).fetchone()
        if clash:
            return False, f"Serial '{serial}' is already used by another asset (ID {clash[0]})."
        conn.execute(
            "UPDATE assets SET serial = ?, model = ?, asset_number = ?, nominal_ohms = ?, set_id = ?, "
            "category = COALESCE(?, category), unit = COALESCE(?, unit) WHERE id = ?",
            (serial, model, asset_number, nominal_ohms, set_id, category, unit, asset_id),
        )
        return True, None


def bulk_assign_sets(conn: sqlite3.Connection, serial_to_set: dict) -> dict:
    updated, not_found = [], []
    with conn:
        for serial, set_id in serial_to_set.items():
            cur = conn.execute("UPDATE assets SET set_id = ? WHERE serial = ?", (set_id, str(serial)))
            (updated if cur.rowcount > 0 else not_found).append(serial)
    return {"updated": updated, "not_found": not_found}


def delete_asset(conn: sqlite3.Connection, asset_id: int) -> None:
    """Transactionally deletes an asset and all cascading child records."""
    with conn:
        cal_ids = [r[0] for r in conn.execute("SELECT id FROM calibrations WHERE asset_id = ?", (asset_id,)).fetchall()]
        if cal_ids:
            placeholders = ",".join("?" * len(cal_ids))
            conn.execute(f"DELETE FROM calibration_readings WHERE calibration_id IN ({placeholders})", cal_ids)
            conn.execute(f"DELETE FROM calibrations WHERE id IN ({placeholders})", cal_ids)
        conn.execute("DELETE FROM test_points WHERE asset_id = ?", (asset_id,))
        conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))


def delete_calibration(conn: sqlite3.Connection, calibration_id: int) -> None:
    """Transactionally deletes a calibration event and its reading records."""
    with conn:
        conn.execute("DELETE FROM calibration_readings WHERE calibration_id = ?", (calibration_id,))
        conn.execute("DELETE FROM calibrations WHERE id = ?", (calibration_id,))
