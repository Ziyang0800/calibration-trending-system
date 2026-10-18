-- Calibration trending database schema (Phase 2)
--
-- One row per physical standard in `assets`, one row per calibration
-- event in `calibrations`. Nominal value is stored in base ohms so all
-- decades (0.1 Ohm through 1 GOhm) live in the same table without unit
-- confusion at query time.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS assets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    serial          TEXT NOT NULL UNIQUE,
    model           TEXT,
    asset_number    TEXT,          -- e.g. PN010069, EQ358990
    nominal_ohms    REAL NOT NULL,
    source_workbook TEXT,          -- which .xlsx this asset was first seen in
    source_sheet    TEXT,          -- which tab (decade) it lives on
    set_id          TEXT,          -- e.g. "Set 1" - a cross-decade grouping (a matched kit), independent of decade
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS calibrations (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id                INTEGER NOT NULL REFERENCES assets(id),
    cert_number             TEXT,                  -- NULL for rows migrated from Excel (not recorded there)
    cal_date                TEXT NOT NULL,         -- ISO 8601 date, e.g. 2026-07-22
    measured_value          REAL NOT NULL,         -- ohms
    mu_relative             REAL NOT NULL,         -- e.g. 9.7e-7 for 0.97 uOhm/Ohm
    source                  TEXT NOT NULL,         -- 'excel_migration' | 'pdf_import'
    cert_pdf_path           TEXT,                  -- NULL for excel_migration rows
    reviewer_comment        TEXT,                  -- free-text justification, e.g. for an out-of-trend point
    excluded_from_regression INTEGER NOT NULL DEFAULT 0,  -- 1 = verified outlier, left out of the trend fit
    imported_at             TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(asset_id, cal_date)             -- re-running an import/migration is a no-op, not a duplicate
);

CREATE INDEX IF NOT EXISTS idx_calibrations_asset_date ON calibrations(asset_id, cal_date);
