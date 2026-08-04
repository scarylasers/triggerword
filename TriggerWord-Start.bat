@echo off
cd /d "C:\Users\wilco\PycharmProjects\TriggerWord"
echo Starting TriggerWord...
echo ========================
start "TriggerWord Browser" "http://localhost:8002"
python local_server.py
pause
