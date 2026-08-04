@echo off
REM Start TriggerWord. Works from wherever this folder happens to live -
REM %~dp0 is this file's own directory, so no path is hardcoded.
title TriggerWord - close this window to stop

cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo.
    echo   Python was not found.
    echo.
    echo   Install it from https://www.python.org/downloads/
    echo   and tick "Add Python to PATH" during setup.
    echo.
    pause
    exit /b 1
)

echo.
echo   TriggerWord is starting...
echo   Opening http://localhost:8002 in your browser.
echo.
echo   LEAVE THIS WINDOW OPEN. Closing it stops the app.
echo.

start "" "http://localhost:8002"
python -m http.server 8002 --bind 127.0.0.1

echo.
echo   TriggerWord stopped.
pause
