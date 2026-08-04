@echo off
title TriggerWord - Press Ctrl+C to close everything
echo Starting TriggerWord Application...
echo ===================================

:: Set the working directory to the script's directory
cd /d "%~dp0"

:: Check if conda is available
where conda >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Error: Conda is not in your PATH. Please ensure Anaconda/Miniconda is installed.
    pause
    exit /b 1
)

:: Activate the conda environment
call conda activate whisper-env
if %ERRORLEVEL% NEQ 0 (
    echo Error: Could not activate conda environment 'whisper-env'.
    echo Please run setup first or check environment name.
    pause
    exit /b 1
)

echo.
echo Starting server and opening browser...
echo Press Ctrl+C in this window to close EVERYTHING
echo ===================================

:: Start uvicorn server in background and capture its PID
start /B uvicorn local_server:app --reload --port 8002 --app-dir "%~dp0"

:: Wait a moment for server to start
timeout /t 3 /nobreak >nul

:: Open Chrome with specific flags to make it easier to close
start "TriggerWord Browser" chrome --new-window --app=http://127.0.0.1:8002 --disable-web-security --user-data-dir="%TEMP%\triggerword_chrome"

:: Wait for user to press Ctrl+C, then cleanup
echo.
echo Browser opened. Press Ctrl+C to close everything...
echo (This will close both the server and browser)

:: This infinite loop keeps the script running until Ctrl+C
:wait_loop
timeout /t 1 /nobreak >nul
goto wait_loop

:: This won't be reached normally, but serves as cleanup if script ends otherwise
:cleanup
echo Cleaning up...
taskkill /F /IM "uvicorn.exe" >nul 2>&1
taskkill /F /IM "python.exe" /FI "COMMANDLINE=*uvicorn*" >nul 2>&1
taskkill /F /IM "chrome.exe" /FI "COMMANDLINE=*triggerword*" >nul 2>&1
echo Done.
