@echo off
powershell.exe -NoProfile -File "%~dp0tools\start_desktop.ps1"
if errorlevel 1 pause
