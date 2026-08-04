@echo off

:: Change to the directory where the script is located
cd /d "%~dp0"

:: Start the server directly using Python
python -m uvicorn local_server:app --reload --port 8001

pause
