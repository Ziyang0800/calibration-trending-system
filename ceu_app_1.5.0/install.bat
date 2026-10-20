@echo off
rem Installs CEUTool for the current user (no admin needed) and adds Desktop + Start Menu shortcuts.
set DEST=%LOCALAPPDATA%\Programs\CEUTool
if not exist "%DEST%" mkdir "%DEST%"
copy /Y "%~dp0CEUTool.exe" "%DEST%\CEUTool.exe" >nul
if errorlevel 1 goto fail
powershell -NoProfile -Command "$s=New-Object -ComObject WScript.Shell; foreach($p in @([Environment]::GetFolderPath('Desktop'),[Environment]::GetFolderPath('Programs'))){$l=$s.CreateShortcut($p+'\CEU Validation Tool.lnk');$l.TargetPath='%DEST%\CEUTool.exe';$l.WorkingDirectory='%DEST%';$l.Save()}"
echo Installed to %DEST%
echo Start it from the Desktop or Start Menu shortcut "CEU Validation Tool".
pause
exit /b 0
:fail
echo Could not copy CEUTool.exe - close the app if it is running and try again.
pause
exit /b 1
