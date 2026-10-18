# CalibrationSystem.spec
#
# Build with:  pyinstaller CalibrationSystem.spec
# (Run this ON WINDOWS to get a .exe - PyInstaller cannot cross-compile;
#  building on Linux/Mac produces a Linux/Mac binary, not a .exe.)
#
# Produces dist/CalibrationSystem/CalibrationSystem.exe (a folder, not a
# single file - see PHASE6_INSTRUCTIONS.md for why --onefile is deliberately
# NOT used here).

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
        ('schema.sql', '.'),
        ('htbasic_templates', 'htbasic_templates'),
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
    console=True,   # keep the console window - it shows the URL, DB path, and any errors
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='CalibrationSystem',
)
