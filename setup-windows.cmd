@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup-windows.ps1"
set "RESULT=%ERRORLEVEL%"
echo.
pause
exit /b %RESULT%
