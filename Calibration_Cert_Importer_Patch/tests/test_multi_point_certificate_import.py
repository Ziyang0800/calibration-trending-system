from datetime import datetime
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cal_cert_importer as importer


class FakePage:
    width = 612
    height = 792

    def __init__(self, text=""):
        self.text = text

    def extract_text(self):
        return self.text

    def crop(self, bbox):
        return self


class FakePdf:
    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_scanned_732a_header_identity(monkeypatch, tmp_path):
    header = """DATE: 19 May 2026 CERT#: WO-01394837
ITEM: DC Reference Standard MODEL: 732A
S/N: 3615000 MFR: Fluke"""
    monkeypatch.setattr(importer.pdfplumber, "open", lambda _: FakePdf([FakePage(), FakePage()]))
    monkeypatch.setattr(importer, "_ocr_page", lambda page, cmd=None, psm=6: header)
    result = importer.extract_serial_and_date(str(tmp_path / "scanned.pdf"))
    assert result["serial"] == "3615000"
    assert result["cal_date"] == datetime(2026, 5, 19)
    assert result["cert_number"] == "WO-01394837"


def test_732a_extracts_both_voltage_outputs_and_nv_uncertainty(monkeypatch, tmp_path):
    text = """Nominal Output (V) Measured Voltage (V) Uncertainty (nV)
10 10.000 083 883 35
| 0.999 982 438 24.4"""
    monkeypatch.setattr(importer.pdfplumber, "open", lambda _: FakePdf([FakePage()]))
    monkeypatch.setattr(importer, "_ocr_page", lambda page, cmd=None, psm=6: text)
    points = [
        {"id": 10, "point_name": "10V Output", "nominal_value": 10.0},
        {"id": 11, "point_name": "1V Output", "nominal_value": 1.0},
    ]
    result = importer.extract_multi_point_measurements(str(tmp_path / "dcv.pdf"), "dcv_reference", points)
    assert result["ok"] is True
    assert result["uncertainty_unit"] == "nV"
    assert result["readings"] == [
        {"test_point_id": 10, "measured_value": pytest.approx(10.000083883), "uncertainty": 35.0},
        {"test_point_id": 11, "measured_value": pytest.approx(0.999982438), "uncertainty": 24.4},
    ]


def test_ac_divider_extracts_all_six_frequencies_and_ppm(monkeypatch, tmp_path):
    text = """FREQUENCY RATIO OF RATIO
1KHz 100.9036 3.7 ppm
20KHz 100.9018 11 ppm
100KHz 100.8862 13 ppm
300KHz 100.8259 20 ppm
500KHz 100.7654 43 ppm
1MHz 100.5432 120 ppm"""
    monkeypatch.setattr(importer.pdfplumber, "open", lambda _: FakePdf([FakePage()]))
    monkeypatch.setattr(importer, "_ocr_page", lambda page, cmd=None, psm=6: text)
    points = [
        {"id": i + 1, "point_name": name, "nominal_value": 100.0}
        for i, name in enumerate(["1 kHz", "20 kHz", "100 kHz", "300 kHz", "500 kHz", "1 MHz"])
    ]
    result = importer.extract_multi_point_measurements(str(tmp_path / "divider.pdf"), "ac_divider", points)
    assert result["ok"] is True
    assert result["uncertainty_unit"] == "ppm"
    assert [r["measured_value"] for r in result["readings"]] == pytest.approx(
        [100.9036, 100.9018, 100.8862, 100.8259, 100.7654, 100.5432]
    )
    assert [r["uncertainty"] for r in result["readings"]] == pytest.approx([3.7, 11, 13, 20, 43, 120])


def test_multi_point_parser_refuses_partial_results(monkeypatch, tmp_path):
    text = "1KHz 100.9036 3.7 ppm"
    monkeypatch.setattr(importer.pdfplumber, "open", lambda _: FakePdf([FakePage()]))
    monkeypatch.setattr(importer, "_ocr_page", lambda page, cmd=None, psm=6: text)
    points = [
        {"id": 1, "point_name": "1 kHz"},
        {"id": 2, "point_name": "20 kHz"},
    ]
    result = importer.extract_multi_point_measurements(str(tmp_path / "divider.pdf"), "ac_divider", points)
    assert result["ok"] is False
    assert len(result["readings"]) == 1
    assert any("20 kHz" in warning for warning in result["warnings"])
