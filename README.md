# Calibration Trending System 1.0.0

Desktop entry point: `app.py`. The pywebview bridge calls `CalibrationService`; `queries.py` and `trending.py` supply point-specific analysis; `db.py` manages SQLite schema version 2. `MainApp.py` is the optional local Flask interface. `frontend/` is an optional Next.js server frontend and is not included in the Windows desktop package. The CEU tools in `ceu_app/` and `ceu_app_1.5.0/` are separate applications.

## Development

Use the existing project environment or create one with Python 3.14 on Windows. Install `requirements-dev.txt` into that environment. The pinned direct dependency versions match the environment used to validate this repair; a fresh online installation was not tested. Tesseract OCR and Microsoft Edge WebView2 are external desktop prerequisites. Install Tesseract in a standard location or add its executable folder to PATH.

Run the tested Windows release with `Start-CalibrationSystem.cmd`, which explicitly selects the project database. You can also run the desktop source with `.venv\Scripts\python.exe app.py`. The launcher resolves paths relative to this project folder and reads the most recently validated release from `dist/current-release.json`. The working-tree `calibration.db` stays in use. A frozen application checks for an existing database beside its executable, then uses `%APPDATA%\CalibrationSystem\calibration.db`. `CALIBRATION_LOCAL_DB` explicitly selects another database. Do not distribute a production database inside a release.

Run Python regressions with `.venv\Scripts\python.exe -B -m pytest tests -p no:cacheprovider`. Run JavaScript regressions with `node --test tests/test_ui.cjs`. Tests use temporary databases. Certificate fixtures are read-only inputs under `tests/fixtures/`.

## Calibration behavior

- The latest calibration is held out of the regression fit. At least three usable historical points are required in the active epoch.
- Resistors read page 3 only. Keysight 33622A reads the final page only and matches 15 dB points.
- DC reference uncertainties are nV; AC-divider uncertainties are ppm. WFG values remain dB. The resistor event uncertainty is a relative ratio.
- AC/DC duplicate result rows are left blank for manual verification.
- Desktop imports with a selected PDF archive it by SHA-256 beside the active database in `certs/`. For existing linked PDFs, run `python tools/finalize_database.py --database calibration.db --backup-dir <outside-project-backup-folder> --apply`. This takes a verified SQLite backup, archives available linked certificates, updates only their paths, and checks that calibration measurements and other metadata remain identical. Missing documents are reported and preserved. Direct service callers may still create verified manual events without a PDF.
- Editing validates all inputs before one transaction. Omitted metadata is preserved. Event exclusion affects all points; individual point exclusions remain available.
- Network backups create separate timestamped workstation folders under `<configured database stem>_backups/`. They include a SQLite snapshot, available certificates/attachments, and a manifest. They do not overwrite the configured shared database and do not merge workstation changes. Partial runs end in `.partial` and are not valid backups. Missing documents are listed in the manifest and reported in the desktop UI.

## Optional web frontend

`MainApp.py --no-browser` serves Flask on loopback only. Network serving is disabled. HTML forms use session CSRF tokens, and writes use the desktop edit/import validation. The legacy scalar import form cannot commit multi-point assets; use the desktop point-verification dialog for those imports.

For Next.js, run Flask on port 5000 and the Next.js server on localhost. `/api/` and `/legacy/` proxy to Flask, including CSRF-protected report forms. Production Next.js requires a server (`npm run build`, then `npm start`); static export is intentionally disabled because it cannot implement these proxies. Next.js and eslint-config-next are pinned to the patched 16.4.3 release. The full production build and TypeScript checks passed, and npm audit reported zero known vulnerabilities after the update.

## Release

Use `powershell -File tools/build_release.ps1` from the project root. It runs Python/JavaScript tests, builds the canonical `CalibrationSystem.spec` into a new `dist/verified-*` generation, and invokes the packaged headless self-test. Existing release folders and their databases are preserved. Compatibility spec files delegate to the same canonical spec. UI assets and the offline SVG chart renderer are bundled; there is no remote script dependency in the desktop shell.

On a separate Windows machine, verify WebView2 and Tesseract, open each asset category, inspect charts, exercise point edits and certificate previews, export Excel/PDF/HTBasic, and verify a restored backup with remapped document paths. The automated self-test verifies resources and core calculations without opening the production database; it does not replace interactive acceptance testing.

## Source control

Production databases, certificate archives, attachments, generated MARS exports and build/distribution output are excluded from Git. The frontend is ordinary source within this repository; no separate repository checkout is needed. Historical Git objects are retained. Source-only CI builds and tests both frontends and publishes a Windows build artifact without production data.

Local calibration records and PDFs are maintained in the project data folders and external backups, not pushed to GitHub. Existing workbooks, exports and separate CEU tools are retained because they may still be needed. See `CHANGELOG.md` for the finalized release notes.
