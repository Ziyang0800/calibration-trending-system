@echo off
rem Builds dist\CEUTool.exe (one file, no console window). Run from this folder.
pip install -r requirements.txt
pyinstaller --noconsole --onefile --name CEUTool ^
  --add-data "ui;ui" --add-data "default_setup.json;." ^
  --hidden-import keyring.backends.Windows app.py
echo.
echo Done: dist\CEUTool.exe  (copy this single file to the shared drive)
pause
