@echo off

:: Change to the directory where the script is located
cd /d "%~dp0"

echo Starting server with debug mode...
echo ================================

:: Use the full path to your conda environment's Python with debug logging
"C:\Users\%USERNAME%\miniconda3\envs\triggerword\python.exe" -m uvicorn local_server:app --reload --port 8001 --app-dir "%~dp0" --log-level debug

echo.
echo ================================
echo Server stopped. Press any key to close...
pause >nul
