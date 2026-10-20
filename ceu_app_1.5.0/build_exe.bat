@echo off
rem Builds dist\CEUTool.exe (one file, no console window). Run from the ceu_app folder.
rem Uses "python -m" so it always matches the Python you run it with.
python -m pip install --no-cache-dir -r requirements.txt
if errorlevel 1 goto fail
python make_version_file.py
if errorlevel 1 goto fail
set EXTRA=
set ICON=
if exist app.ico set ICON=--icon app.ico --add-data "app.ico;."
set EMB=no
if not exist mars_account.json goto noacct
set EXTRA=--add-data "mars_account.json;."
set EMB=yes
goto acctdone
:noacct
echo.
echo WARNING: mars_account.json was not found in this folder.
echo The exe would have NO built-in MARS login and every PC would show demo data or ask for a login.
echo Copy your mars_account.json into this folder first - see mars_account.json.example
set /p GO=Type SKIP to build anyway, or press Enter to stop: 
if /i not "%GO%"=="SKIP" goto fail
:acctdone
if exist dist\CEUTool.exe del /f /q dist\CEUTool.exe
if exist dist\CEUTool.exe (
  echo Cannot replace dist\CEUTool.exe - close CEUTool if it is running, then try again.
  goto fail
)
python -m PyInstaller --noconsole --onefile --name CEUTool --add-data "ui;ui" --add-data "default_names.json;." --add-data "packs;packs" --collect-data reportlab %EXTRA% %ICON% --version-file version_info.txt --hidden-import updater --hidden-import version --hidden-import keyring.backends.Windows --hidden-import openpyxl --hidden-import masterlist --hidden-import winfile --hidden-import names --hidden-import plugins --hidden-import json --hidden-import shutil --hidden-import zipfile --hidden-import hashlib --hidden-import csv --hidden-import importlib.util --hidden-import winchrome --hidden-import products app.py
if errorlevel 1 goto fail
echo.
if not exist dist mkdir dist
>dist\build_info.txt echo embedded_account=%EMB%
echo Done: dist\CEUTool.exe   MARS account built in: %EMB%
echo To publish: python release.py "<release folder>" --notes "what changed"
pause
exit /b 0
:fail
echo.
echo BUILD FAILED - see the error above.
pause
exit /b 1
