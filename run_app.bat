@echo off
title TriggerWord App Launcher
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
    echo Creating the environment and installing dependencies...
    call conda create -n whisper-env python=3.10 -y
    call conda activate whisper-env
    pip install fastapi uvicorn torch torchaudio openai-whisper python-multipart
    if %ERRORLEVEL% NEQ 0 (
        echo Error: Failed to install required packages.
        pause
        exit /b 1
    )
)

:: Check if required packages are installed
pip show fastapi uvicorn torch whisper >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Installing required packages...
    pip install fastapi uvicorn torch torchaudio openai-whisper python-multipart
    if %ERRORLEVEL% NEQ 0 (
        echo Error: Failed to install required packages.
        pause
        exit /b 1
    )
)

echo.
echo Starting the application...
echo Access the app at: http://127.0.0.1:8000
echo Press Ctrl+C to stop the server
echo ===================================

:: Run the FastAPI application
uvicorn local_server:app --reload

:: Keep the window open if there's an error
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Application failed to start. Press any key to exit...
    pause >nul
)
