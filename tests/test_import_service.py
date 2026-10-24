"""Regression tests for safe certificate import and multi-point persistence."""
from pathlib import Path

import pytest

import db
import service as service_module
from service import CalibrationService


@pytest.fixture
def svc_and_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "import_test.db")
    # Initialize schema and keep only the path in the service instance.
    conn = db.connect(db_path)
    conn.close()
    svc = CalibrationService.__new__(CalibrationService)
    monkeypatch.setattr(svc, "get_conn", lambda: db.connect(db_path))
    return svc, db_path


def test_multi_point_import_writes_all_readings_atomically(svc_and_db):
    svc, db_path = svc_and_db
    conn = db.connect(db_path)
    aid = db.upsert_asset(conn, "DIV-SN", "ET 100mV", "PN030000", 10.0, category="ac_divider", unit="Ratio")
    tp1 = db.upsert_test_point(conn, aid, "1 kHz", "Ratio", 10.0, "Ratio", 1)
    tp2 = db.upsert_test_point(conn, aid, "20 kHz", "Ratio", 10.0, "Ratio", 2)
    conn.close()

    pdf = Path(db_path).parent / "certificate.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF")
    result = svc.commit_imported_certificate({
        "asset_id": aid, "cal_date": "2026-10-20", "pdf_path": str(pdf),
        "readings": [
            {"test_point_id": tp1, "measured_value": 10.0001, "uncertainty": 12.5},
            {"test_point_id": tp2, "measured_value": 10.0002, "uncertainty": 13.0},
        ],
    })
    assert result["ok"] is True
    assert result["point_count"] == 2

    conn = db.connect(db_path)
    cal = conn.execute("SELECT id, measured_value, mu_relative FROM calibrations WHERE asset_id=?", (aid,)).fetchone()
    readings = conn.execute(
        "SELECT test_point_id, measured_value, uncertainty FROM calibration_readings WHERE calibration_id=? ORDER BY test_point_id",
        (cal[0],),
    ).fetchall()
    conn.close()
    assert cal[1] == pytest.approx(10.0001)  # legacy summary mirrors first configured point
    assert cal[2] == 0.0                    # no single global MU for multi-point asset
    assert readings == [(tp1, 10.0001, 12.5), (tp2, 10.0002, 13.0)]


def test_multi_point_import_rejects_missing_point_without_writing(svc_and_db):
    svc, db_path = svc_and_db
    conn = db.connect(db_path)
    aid = db.upsert_asset(conn, "DCV-SN", "Fluke 732A", "PN-DCV", 10.0, category="dcv_reference", unit="V")
    tp1 = db.upsert_test_point(conn, aid, "10V Output", "DC Voltage", 10.0, "V", 1)
    tp2 = db.upsert_test_point(conn, aid, "1V Output", "DC Voltage", 1.0, "V", 2)
    conn.close()

    result = svc.commit_imported_certificate({
        "asset_id": aid, "cal_date": "2026-10-20",
        "readings": [{"test_point_id": tp1, "measured_value": 10.000000001, "uncertainty": 2.0}],
    })
    assert result["ok"] is False
    assert "Missing test-point" in result["error"]
    conn = db.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM calibrations WHERE asset_id=?", (aid,)).fetchone()[0] == 0
    conn.close()


def test_duplicate_import_is_reported_as_failure_not_success(svc_and_db):
    svc, db_path = svc_and_db
    conn = db.connect(db_path)
    aid = db.upsert_asset(conn, "RES-SN", "0.1 Ohm", "PN010000", 0.1)
    db.insert_calibration(conn, aid, "2026-10-20", 0.1000001, 1e-7, "pdf_import")
    conn.close()

    result = svc.commit_imported_certificate({
        "asset_id": aid, "cal_date": "2026-10-20", "measured_value": 0.1000002, "mu_relative": 1e-7,
    })
    assert result["ok"] is False
    assert result["duplicate"] is True
    conn = db.connect(db_path)
    row = conn.execute("SELECT measured_value FROM calibrations WHERE asset_id=?", (aid,)).fetchone()
    conn.close()
    assert row[0] == pytest.approx(0.1000001)


def test_multi_point_category_without_configured_points_is_rejected(svc_and_db):
    svc, db_path = svc_and_db
    conn = db.connect(db_path)
    aid = db.upsert_asset(conn, "WFG-SN", "Keysight 33622A", "PN-WFG", 0.0, category="waveform_generator", unit="dB")
    conn.close()

    result = svc.commit_imported_certificate({
        "asset_id": aid, "cal_date": "2026-10-20", "measured_value": 0.0, "mu_relative": 1.0,
    })
    assert result["ok"] is False
    assert "no configured test points" in result["error"]


def test_ocr_unit_assumptions_are_flagged_for_review():
    from cal_cert_importer import _parse_measurement_line
    measured, mu_relative, warnings = _parse_measurement_line(
        "0.100 Q 0.100000761 Q 0.97", known_nominal=0.1
    )
    assert measured == pytest.approx(0.100000761)
    assert mu_relative == pytest.approx(0.97e-6)
    assert any("MU unit/prefix" in warning for warning in warnings)


def test_multi_point_preview_lists_every_configured_point(svc_and_db, monkeypatch):
    svc, db_path = svc_and_db
    conn = db.connect(db_path)
    aid = db.upsert_asset(conn, "WFG-PREVIEW", "Keysight 33622A", "PN-WFG2", 0.0, category="waveform_generator", unit="dB")
    db.upsert_test_point(conn, aid, "cf 10mV @ 4MHz (dB)", "Correction Factor", 0.0, "dB", 1)
    db.upsert_test_point(conn, aid, "cf 100mV @ 4MHz (dB)", "Correction Factor", 0.0, "dB", 2)
    conn.close()

    monkeypatch.setattr(service_module.winfile, "open_file", lambda *args, **kwargs: "fake.pdf")
    monkeypatch.setattr(service_module, "extract_serial_and_date", lambda path: {
        "serial": "WFG-PREVIEW", "cal_date": __import__("datetime").datetime(2026, 10, 20)
    })
    # A multi-point asset must not call the resistor-only scalar parser.
    monkeypatch.setattr(service_module, "extract_measurement", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("scalar parser must not be called")))

    result = svc.import_certificate_file()
    assert result["ok"] is True
    assert result["manual_readings_required"] is True
    assert len(result["test_points"]) == 2
    assert all(point["uncertainty_unit"] is None for point in result["test_points"])
