@echo off
title Nimble Notes - Install
cd /d "%~dp0"

echo ==========================================
echo   Nimble Notes - one time setup
echo ==========================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found on your PATH.
  echo Install Python 3.10+ from python.org then run this again.
  pause
  exit /b 1
)

echo Creating virtual environment...
python -m venv .venv
if errorlevel 1 ( echo Failed to create venv. & pause & exit /b 1 )

echo Installing packages...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 ( echo Package install failed. & pause & exit /b 1 )

echo.
echo Done. Launch with  launch_nimble_notes.bat
pause
