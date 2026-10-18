CEU Validation Tool - prototype
================================
RUN (needs Python 3.10+ on this PC):
    pip install pywebview requests keyring
    python app.py
With no MARS login it starts in DEMO mode (fake data, orange DEMO DATA badge).
Click "Connect to MARS" (top right) and enter the shared account to use live data.
Or set environment variables MARS_USER and MARS_PASSWORD before starting.

YOUR REAL ETEs
    On first run the app copies default_setup.json to  %APPDATA%\CEUTool\setup.json
    Edit that file: put the real Equipment_IDs of the 19 B-1 ETEs (b1) and of Sets 1-3 (sets).
    The first two b1 entries must be the Calibrator and Amplifier.
    (Delete %APPDATA%\CEUTool\cache.json after changing it, or just press Refresh.)

RULES (logic.py)
    Valid = Current_Whereabout is INU  AND  Cal due date is later than today
            AND (when scanning) the ETE belongs to the selected station.
    RCV = sent for calibration. Due within 30 days = "Expiring Soon" (still valid).

BUILD THE EXE
    Run build_exe.bat  ->  dist\CEUTool.exe  (single file, copy it to the shared drive)

FILES
    app.py      window + bridge to the UI          ui/index.html   the screen
    service.py  state and actions                  logic.py        the validity rules
    mars.py     MARS client + demo data            store.py        local files
