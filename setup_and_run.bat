@echo off

:: Change to the directory where the script is located
cd /d "%~dp0"

echo Creating Python virtual environment...
python -m venv venv

call venv\Scripts\activate.bat

echo Installing required packages...
pip install fastapi uvicorn torch torchaudio openai-whisper python-multipart

echo Starting the application...
start "" http://localhost:8001

uvicorn local_server:app --reload --port 8001 --app-dir "%~dp0"

pause
