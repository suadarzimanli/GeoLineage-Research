@echo off
REM Run GeoLineage pipeline without activating the venv (avoids PowerShell execution policy).
cd /d "%~dp0"
.venv\Scripts\python.exe -m scripts.run_pipeline --bbox -122.5 37.5 -122.2 37.8 --max-items 5
pause
