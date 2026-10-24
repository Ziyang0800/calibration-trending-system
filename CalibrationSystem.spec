from pathlib import Path

PROJECT_ROOT = Path(SPEC).resolve().parent

# CalibrationSystem.spec
#
# Build with:  pyinstaller CalibrationSystem.spec
# (Run this ON WINDOWS to get a .exe - PyInstaller cannot cross-compile;
#  building on Linux/Mac produces a Linux/Mac binary, not a .exe.)
#
# Produces dist/CalibrationSystem/CalibrationSystem.exe (a folder, not a
# single file, so bundled scientific libraries and UI assets remain inspectable).

a = Analysis(
    [str(PROJECT_ROOT / 'app.py')],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        (str(PROJECT_ROOT / 'ui'), 'ui'),
        (str(PROJECT_ROOT / 'templates'), 'templates'),  # retained for legacy report/template code
        (str(PROJECT_ROOT / 'static'), 'static'),       # retained for legacy assets
        (str(PROJECT_ROOT / 'schema.sql'), '.'),
        (str(PROJECT_ROOT / 'VERSION'), '.'),
        (str(PROJECT_ROOT / 'htbasic_templates'), 'htbasic_templates'),
    ],
    hiddenimports=[
        'openpyxl.cell._writer',  # openpyxl sometimes needs this spelled out for PyInstaller
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CalibrationSystem',
    debug=False,
    strip=False,
    upx=False,
    console=False,  # native windowed desktop shell; diagnostics go to %APPDATA%\CalibrationSystem\app.log
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='CalibrationSystem',
)
