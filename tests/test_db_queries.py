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