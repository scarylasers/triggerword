@echo off

:: Change to the directory where the script is located
cd /d "%~dp0"

:: Set the path to conda
set CONDA_PATH=C:\Users\%USERNAME%\miniconda3\Scripts\conda.bat

:: Activate conda environment
call "%CONDA_PATH%" activate triggerword

:: Open the browser
start "" http://localhost:8001

:: Start the server
uvicorn local_server:app --reload --port 8001 --app-dir "%~dp0"

pause
