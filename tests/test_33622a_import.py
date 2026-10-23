"""Final-page extraction and verification regressions; only temporary databases."""
from pathlib import Path

import pytest
import cal_cert_importer as importer
import db
import service
from test_multi_point_certificate_import import FakePage, FakePdf
from test_import_service import svc_and_db

FIXTURES = Path(__file__).parent / "fixtures"
NAMES = [f"cf {v} @ {f}MHz (dB)"
         for v, fs in (("10mV", [4]), ("100mV", [4, 8, 10]),
                       ("1V", [4, 8, 10]), ("3V", [2, 4, 8, 10])) for f in fs]
NAMES += [f"Flatness Error {f}MHz (dB)" for f in [2, 4, 8, 10]]
VALUES = [-.02491, -.00758, -.01981, -.02024, -.01010, -.02213,
          -.02403, -.02715, -.02846, -.03843, -.03955, -.027, -.018, -.021, -.028]
POINTS = [dict(id=100+i, point_name=n, unit="dB") for i, n in enumerate(NAMES)]


@pytest.fixture(scope="module")
def final_text():
    with importer.pdfplumber.open(FIXTURES / "WO-01524852.pdf") as pdf:
        return importer._ocr_page(pdf.pages[-1], psm=6)


def test_supplied_33622a_pdf():
    result = importer.extract_multi_point_measurements(str(FIXTURES / "WO-01524852.pdf"), "waveform_generator", list(reversed(POINTS)))
    assert result["ok"]
    by_id = {r["test_point_id"]: r["measured_value"] for r in result["readings"]}
    assert [by_id[p["id"]] for p in POINTS] == pytest.approx(VALUES)
    assert all(r["uncertainty"] is None for r in result["readings"])


@pytest.mark.parametrize("mode", ["complete", "missing", "duplicate", "wrong_column", "no_final_data"])
def test_only_final_page_and_ambiguous_rows_are_blank(monkeypatch, final_text, mode):
    row = "10mV @ 4MHz -0.299 0.0439 -0.2864 -0.02491"
    assert row in final_text
    text = final_text
    if mode == "missing":
        text = text.replace(row, "")
    elif mode == "duplicate":
        text += "\n" + row
    elif mode == "wrong_column":
        text = text.replace(row, "10mV @ 4MHz -0.299 0.0439 -0.2864")
    elif mode == "no_final_data":
        text = "Unrelated final page"
    monkeypatch.setattr(importer.pdfplumber, "open", lambda _: FakePdf([FakePage(final_text), FakePage(text)]))
    result = importer.extract_multi_point_measurements("fake.pdf", "waveform_generator", POINTS)
    assert result["ok"] == (mode == "complete")
    assert any(r["test_point_id"] == 100 for r in result["readings"]) == (mode == "complete")
    assert len(result["readings"]) == (15 if mode == "complete" else 0 if mode == "no_final_data" else 14)


@pytest.mark.parametrize("count", [2, 4])
def test_resistor_never_uses_other_pages(monkeypatch, count):
    good = "MEASURED\n0.100 Q 0.100000761 Q 0.97"
    pages = [FakePage(good), FakePage(good)]
    if count == 4:
        pages += [FakePage("No measurement here"), FakePage(good)]
    monkeypatch.setattr(importer.pdfplumber, "open", lambda _: FakePdf(pages))
    assert importer.extract_measurement("fake.pdf", .1)["measured_value"] is None


def test_supplied_resistor_pdf():
    result = importer.extract_measurement(str(FIXTURES / "WO-01523560.pdf"), .1)
    assert result["measured_value"] == pytest.approx(.099998941, abs=1e-12)
    assert result["mu_relative"] == pytest.approx(.61e-6)


def test_preview_all_15_without_writes_then_duplicate_protection(svc_and_db, monkeypatch):
    svc, path = svc_and_db
    conn = db.connect(path)
    aid = db.upsert_asset(conn, "SG53800187", "Keysight 33622A", "TEST", 0,
                          category="waveform_generator", unit="dB")
    ids = [db.upsert_test_point(conn, aid, name, "CF" if i < 11 else "Flatness Error", 0, "dB", i)
           for i, name in enumerate(NAMES)]
    conn.close()
    monkeypatch.setattr(service.winfile, "open_file", lambda *a, **kw: str(FIXTURES / "WO-01524852.pdf"))
    preview = svc.import_certificate_file()
    assert preview["ok"] and preview["auto_extraction_complete"]
    assert [p["id"] for p in preview["test_points"]] == ids
    assert [p["measured_value"] for p in preview["test_points"]] == pytest.approx(VALUES)
    assert all(p["extraction_status"] == "extracted" for p in preview["test_points"])
    conn = db.connect(path)
    assert conn.execute("SELECT count(*) FROM calibrations").fetchone()[0] == 0
    conn.close()
    payload = dict(asset_id=aid, cal_date=preview["cal_date"], readings=preview["extracted_readings"])
    assert svc.commit_imported_certificate(payload)["ok"]
    assert svc.commit_imported_certificate(payload)["duplicate"]
    conn = db.connect(path)
    rows = conn.execute("SELECT measured_value FROM calibration_readings ORDER BY test_point_id").fetchall()
    assert [r[0] for r in rows] == pytest.approx(VALUES)
    conn.close()
