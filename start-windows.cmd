@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Run setup-windows.cmd first.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -m doctransai.desktop --env-file "%~dp0.env" %*
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" pause
exit /b %RESULT%
