@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python Launcher for Windows was not found.
  echo Install 64-bit CPython 3.13 from https://www.python.org/downloads/windows/
  echo Be sure to include the Python Launcher, then run this file again.
  pause
  exit /b 1
)

py -3.13 -c "import struct,sys; raise SystemExit(0 if sys.version_info[:2]==(3,13) and struct.calcsize('P')*8==64 else 1)" >nul 2>nul
if errorlevel 1 (
  echo ML Learning Lab requires 64-bit CPython 3.13.x.
  echo Install it from https://www.python.org/downloads/windows/ and try again.
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap.ps1"
if errorlevel 1 (
  echo.
  echo Startup failed. See the troubleshooting guide and launcher log:
  echo   docs\troubleshooting.md
  echo   %%LOCALAPPDATA%%\MLLearningLab\logs\launcher.log
  pause
  exit /b 1
)

endlocal
