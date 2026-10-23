"""
tests/test_db_queries.py - Verifies database duplicate protection,
multi-point drift calculations, and epoch status evaluation.
"""

import pytest
from db import connect, upsert_asset, insert_calibration, upsert_test_point, insert_calibration_reading
from queries import get_asset_detail


@pytest.fixture
def temp_db(tmp_path):
    db_path = str(tmp_path / "test_metrology.db")
    return connect(db_path)


def test_insert_calibration_duplicate_protection(temp_db):
    """Ensures duplicate insertions return None and do not overwrite existing data silently."""
    aid = upsert_asset(temp_db, "74076", "742A-1", "PN010002", 1.0)
    
    # 1. First insert
    cid1 = insert_calibration(temp_db, aid, "2025-01-15", 1.000004, 1e-6, "test", cert_number="WO-101")
    assert cid1 is not None

    # 2. Duplicate insert without allow_overwrite
    cid2 = insert_calibration(temp_db, aid, "2025-01-15", 9.999999, 5e-6, "test", cert_number="WO-999", allow_overwrite=False)
    assert cid2 is None, "Duplicate calibration must return None when allow_overwrite=False"

    # Verify original reading preserved
    row = temp_db.execute("SELECT measured_value, cert_number FROM calibrations WHERE id = ?", (cid1,)).fetchone()
    assert row[0] == 1.000004
    assert row[1] == "WO-101"

    # 3. Explicit overwrite with allow_overwrite=True
    cid3 = insert_calibration(temp_db, aid, "2025-01-15", 1.000005, 2e-6, "test", cert_number="WO-101-REV", allow_overwrite=True)
    assert cid3 == cid1
    row_updated = temp_db.execute("SELECT measured_value, cert_number FROM calibrations WHERE id = ?", (cid1,)).fetchone()
    assert row_updated[0] == 1.000005
    assert row_updated[1] == "WO-101-REV"


def test_multipoint_matrix_drift_with_baseline(temp_db):
    """Ensures drift is strictly '—' for a single baseline cal, and correctly formatted ppm for dual cals."""
    aid = upsert_asset(temp_db, "PN030002_SN", "ET 10mV", "PN030002", 100.0, category="ac_divider", unit="Ratio")
    tp_id = upsert_test_point(temp_db, aid, "1 kHz", "Ratio", 100.0, "Ratio", 1)

    # Case A: Only 1 calibration exists
    cid1 = insert_calibration(temp_db, aid, "2024-01-01", 100.0050, 2e-5, "test")
    insert_calibration_reading(temp_db, cid1, tp_id, 100.0050, uncertainty=20.0)

    detail1 = get_asset_detail(temp_db, aid)
    tp1 = detail1["test_points"][0]
    assert tp1["drift"] is None
    assert tp1["drift_display"] == "—", "Single calibration must render '—' drift, never 0.00 ppm"

    # Case B: Second calibration exists with drift
    cid2 = insert_calibration(temp_db, aid, "2025-01-01", 100.0070, 2e-5, "test")
    insert_calibration_reading(temp_db, cid2, tp_id, 100.0070, uncertainty=20.0)

    detail2 = get_asset_detail(temp_db, aid)
    tp2 = detail2["test_points"][0]
    # (100.0070 - 100.0050) / 100.0 * 1e6 = +20.00 ppm
    assert tp2["drift_ppm"] == pytest.approx(20.0, abs=0.01)
    assert tp2["drift_display"] == "+20.00 ppm"


def test_multi_point_asset_is_not_marked_in_trend_with_only_two_cals(temp_db):
    from queries import list_assets
    aid = upsert_asset(temp_db, "SN_STATUS", "ET 100mV", "PN030001", 10.0, category="ac_divider", unit="Ratio")
    tp = upsert_test_point(temp_db, aid, "1 kHz", "Ratio", 10.0, "Ratio", 1)
    for day, value in (("2024-01-01", 10.0001), ("2025-01-01", 10.0002)):
        cid = insert_calibration(temp_db, aid, day, value, 1e-6, "test")
        insert_calibration_reading(temp_db, cid, tp, value, uncertainty=12.0)
    item = next(a for a in list_assets(temp_db) if a["id"] == aid)
    assert item["status"] == "insufficient_data"


def test_missing_test_point_reading_does_not_fall_back_to_summary_value(temp_db):
    aid = upsert_asset(temp_db, "SN_NO_FALLBACK", "Fluke 732A", "PN-DCV2", 10.0, category="dcv_reference", unit="V")
    tp_10v = upsert_test_point(temp_db, aid, "10V Output", "DC Voltage", 10.0, "V", 1)
    tp_1v = upsert_test_point(temp_db, aid, "1V Output", "DC Voltage", 1.0, "V", 2)
    cid = insert_calibration(temp_db, aid, "2025-01-01", 10.0000001, 1e-7, "test")
    insert_calibration_reading(temp_db, cid, tp_10v, 10.0000001, uncertainty=2.0)

    detail = get_asset_detail(temp_db, aid, selected_point_id=tp_1v)
    assert detail["calibrations"] == []
    assert detail["trend"] is None


def test_non_duplicate_integrity_error_is_not_misreported_as_duplicate(temp_db):
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        insert_calibration(temp_db, 999999, "2025-01-01", 1.0, 1e-6, "test")
