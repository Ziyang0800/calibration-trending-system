# Calibration Certificate Importer Patch

## Scope

This patch extends certificate identity extraction to scanned Fluke 732A/C-style reports and adds validated point-level extraction for these sample layouts:

- DCV reference (Fluke 732A sample): 10 V and 1 V output readings, with uncertainty retained in nV.
- AC divider (ET 10 mV / ETAC10MV sample): six frequency ratios, with uncertainty retained in ppm.

It also updates the desktop service's certificate preview payload to include the extracted certificate number and point-level values. Extracted OCR values are explicitly flagged for operator verification. Missing or ambiguous points do not count as a complete extraction.

## Files

- `cal_cert_importer.py` — OCR-aware serial/date/certificate extraction and multi-point table parser.
- `service.py` — returns extracted values for point-level preview/prefill while preserving manual verification.
- `tests/test_multi_point_certificate_import.py` — regression tests for scanned identity extraction, DCV points, divider points, and incomplete-table rejection.

## Apply

Back up the current files, then copy the two Python files to the repository root and the test file into `tests/`. Run:

```bash
python -m py_compile cal_cert_importer.py service.py
pytest -q tests/test_multi_point_certificate_import.py
```

The current supplied repository snapshot did not include `ui/app.js`. Therefore, the preview response now carries point-level values, but UI prefill/rendering must be checked against the current `ui/app.js` before calling the end-to-end UI workflow complete.

## Validation performed against the supplied PDFs

- `WO-01394837_Measurement Report (As Received).pdf`
  - Serial: `3615000`
  - Date: 2026-05-19
  - 10 V: 10.000083883 V, uncertainty 35 nV
  - 1 V: 0.999982438 V, uncertainty 24.4 nV
- `WO-01132606-combined-file.pdf`
  - Serial: `PN030002`
  - Date: 2025-07-14
  - 1 kHz: 100.9036, uncertainty 3.7 ppm
  - 20 kHz: 100.9018, uncertainty 11 ppm
  - 100 kHz: 100.8862, uncertainty 13 ppm
  - 300 kHz: 100.8259, uncertainty 20 ppm
  - 500 kHz: 100.7654, uncertainty 43 ppm
  - 1 MHz: 100.5432, uncertainty 120 ppm

These are OCR-derived values and must be checked against the source certificate in the import preview before committing.

## Not included yet

Waveform generator / Keysight 33622A extraction is deliberately not guessed. Add it after a representative certificate is supplied and its correction-factor and flatness point mapping can be validated.
