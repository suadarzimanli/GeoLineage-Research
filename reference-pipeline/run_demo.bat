@echo off
REM Run GeoLineage Streamlit demo without activating the venv (avoids PowerShell execution policy).
REM Must use "streamlit run", not "python demo/app.py".
cd /d "%~dp0"
echo Starting GeoLineage demo...
echo.
echo If the browser did not open automatically, go to: http://localhost:8501
echo.
.venv\Scripts\streamlit.exe run demo/app.py
pause
