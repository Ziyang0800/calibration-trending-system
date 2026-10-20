CEU Validation Tool - prototype
================================
RUN (needs Python 3.10+ on this PC):
    pip install pywebview requests reportlab keyring
    python app.py
With no MARS login it starts in DEMO mode (fake data, orange DEMO DATA badge).
Click "Connect to MARS" (top right) and enter the shared account to use live data.
Or set environment variables MARS_USER and MARS_PASSWORD before starting.

YOUR REAL ETEs
    On first run the OGC pack makes  %APPDATA%\CEUTool\setup_ogc.json  (from the old setup.json if there is one, else packs\ogc\default_setup.json). setup.json now holds only app settings
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

NO LOGIN SCREEN (embedded MARS account)
    Copy mars_account.json.example to mars_account.json (same folder as build_exe.bat),
    fill in the generic account, then run build_exe.bat. The file is bundled into CEUTool.exe
    and the app logs in by itself. NEVER share mars_account.json or put it in a shared folder.
    Anyone who has the exe can extract the password from it, so use a dedicated read-only
    account and change its password (and rebuild) if the exe ever leaks.

SETUP SCREEN
    The "Setup" button edits the B-1 ETEs and the Sets and saves setup.json for you
    (the previous version is kept as setup.json.bak).

--- v5 ---
ETEs button: all ETEs with cal due / whereabout, search, filters, sort, Export CSV, Import masterlist (Excel).
Setup: pick Model Number first, then Equipment ID. Changing one ETE in Calibrator/Amplifier, AC Dividers or
Standard Resistors asks to switch the whole group to the same Set (needs the masterlist Set column).
First step on each PC: ETEs > Import masterlist (Excel), choose ETEs.xlsm (needs openpyxl at build time).

--- v6 ---
Icon: put app.ico next to build_exe.bat (python make_icon.py logo.png makes one) and rebuild.
MARS auto refresh: every 45 minutes while the app is open ("refresh_minutes" in setup.json changes it).
B-2 warning: once per day per PC. Last used B-2 Set is remembered and pre-selected.

--- v7 (version 1.0.0): versioning and updates ---
FIRST INSTALL (once per PC): run install.bat from the release folder (copies CEUTool.exe to %LOCALAPPDATA%\Programs\CEUTool
and adds Desktop / Start Menu shortcuts). Do not run the exe from the shared drive.
SET THE RELEASE FOLDER: in %APPDATA%\CEUTool\setup.json add  "update_path": "\\\\server\\share\\CEUTool"
(or set the CEU_UPDATE_PATH environment variable). Without it the update check is off.
PUBLISH A NEW VERSION:
  1. edit version.py (e.g. 1.0.1) and CHANGELOG.md, git commit, git tag v1.0.1
  2. build_exe.bat
  3. python release.py "<release folder>" --notes "what changed"      (add --min-version 1.0.1 to force everyone to update)
Every running app checks at start-up and every 45 minutes, and offers "Update now" / "Later".
Test locally first: set update_path to a folder on your own PC, release 1.0.0, install it, release 1.0.1, and watch it update.
