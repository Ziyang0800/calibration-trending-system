"""
generate_blank_templates.py - Phase 1 regression tests.

These lock in the two OCR/parsing bugs we already found and fixed
(the ".100 000 761" decimal-point bug, the 0/Q OCR confusion, the
stray-letter-mangled MU unit) so a future change to the parser can't
silently reintroduce them. Run with:

    pip install pytest
    pytest generate_blank_templates.py -v

When you hit a new cert that fails to parse: fix the parser, then copy
the cert PDF into tests/fixtures/ and add a case here with its expected
values, the same way the two below were added. That turns every bug we
debug by hand into a permanent guardrail instead of a one-off fix.
"""

from pathlib import Path

import pytest

from cal_cert_importer import extract_serial_and_date, extract_measurement

FIXTURES = Path(__file__).parent / "fixtures"

CASES = [
    # (pdf filename, known_nominal, expected serial, expected date, expected measured, expected mu_relative)
    ("WO-01261128.pdf", 0.1, "73137", "2025-12-17", 0.100000761, 9.7e-7),
    ("WO-01467782.pdf", 0.1, "73137", "2026-07-22", 0.100000947, 1.2e-7),
]


@pytest.mark.parametrize("filename,nominal,exp_serial,exp_date,exp_measured,exp_mu", CASES)
def test_known_cert(filename, nominal, exp_serial, exp_date, exp_measured, exp_mu):
    pdf_path = str(FIXTURES / filename)

    id_fields = extract_serial_and_date(pdf_path)
    assert id_fields["serial"] == exp_serial
    assert id_fields["cal_date"].date().isoformat() == exp_date

    result = extract_measurement(pdf_path, known_nominal=nominal)
    assert result["measured_value"] == pytest.approx(exp_measured, abs=1e-9)
    assert result["mu_relative"] == pytest.approx(exp_mu, rel=1e-6)


def test_missing_nominal_still_parses_reasonably():
    """Without a known nominal, the parser falls back to its own nominal
    guess from the certificate - should still get the right answer on a
    clean cert, just without the extra safety net."""
    pdf_path = str(FIXTURES / "WO-01261128.pdf")
    result = extract_measurement(pdf_path, known_nominal=None)
    assert result["measured_value"] == pytest.approx(0.100000761, abs=1e-9)
