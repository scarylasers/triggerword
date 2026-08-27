@echo off
REM Start TriggerWord. Works from wherever this folder happens to live -
REM %~dp0 is this file's own directory, so no path is hardcoded.
title TriggerWord

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

REM Find a Chromium browser so TriggerWord opens in a dedicated app window
REM (no tabs, no address bar) instead of looking like another webpage.
set "BROWSER="
for %%p in (
    "%ProgramFiles%\Google\Chrome\Application\chrome.exe"
    "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
    "%LocalAppData%\Google\Chrome\Application\chrome.exe"
    "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
    "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
) do if not defined BROWSER if exist %%p set "BROWSER=%%~p"

REM Full mode when the FastAPI server's packages are installed (see
REM "Advanced install" in the README). A fresh download has neither package
REM and uses the zero-dependency file server below instead.
python -c "import fastapi, uvicorn" >nul 2>&1
if errorlevel 1 goto :simple

REM ---------------------------------------------------------------- full mode
REM Server and router run hidden (output goes to triggerword-*.log). Closing
REM the TriggerWord window shuts everything down: the server notices when the
REM last window disconnects and stops itself and the router. This launcher
REM window closes on its own once the app window is open.

REM Desktop splash animation while everything boots (exits on its own;
REM harmless no-op if Pillow/numpy are missing)
powershell -Command "Start-Process python -ArgumentList 'splash.py' -WorkingDirectory '%~dp0.' -WindowStyle Hidden"

python -c "import keyboard, pywinauto, win32api" >nul 2>&1
if not errorlevel 1 (
    echo   Starting global hotkey router...
    powershell -Command "Start-Process python -ArgumentList 'triggerword_router_improved.py' -WorkingDirectory '%~dp0.' -WindowStyle Hidden -RedirectStandardOutput '%~dp0triggerword-router.log' -RedirectStandardError '%~dp0triggerword-router-err.log'"
)

echo   Starting TriggerWord server...
powershell -Command "Start-Process python -ArgumentList 'local_server.py' -WorkingDirectory '%~dp0.' -WindowStyle Hidden -RedirectStandardOutput '%~dp0triggerword-server.log' -RedirectStandardError '%~dp0triggerword-server-err.log'"

echo   Waiting for the server, then opening TriggerWord...
if defined BROWSER (
    powershell -Command "for($i=0;$i -lt 60;$i++){try{Invoke-WebRequest 'http://127.0.0.1:8002' -UseBasicParsing -TimeoutSec 1|Out-Null;break}catch{Start-Sleep -Milliseconds 500}}; Start-Process -FilePath '%BROWSER%' -ArgumentList '--app=http://localhost:8002/?fresh=%RANDOM%','--window-size=1200,800','--autoplay-policy=no-user-gesture-required'"
) else (
    powershell -Command "for($i=0;$i -lt 60;$i++){try{Invoke-WebRequest 'http://127.0.0.1:8002' -UseBasicParsing -TimeoutSec 1|Out-Null;break}catch{Start-Sleep -Milliseconds 500}}; Start-Process 'http://localhost:8002/?fresh=%RANDOM%'"
)
exit /b 0

REM -------------------------------------------------------------- simple mode
:simple
echo.
echo   TriggerWord is starting...
echo.
echo   LEAVE THIS WINDOW OPEN. Closing it stops the app.
echo.

if defined BROWSER (
    start "" powershell -WindowStyle Hidden -Command "for($i=0;$i -lt 60;$i++){try{Invoke-WebRequest 'http://127.0.0.1:8002' -UseBasicParsing -TimeoutSec 1|Out-Null;break}catch{Start-Sleep -Milliseconds 500}}; Start-Process -FilePath '%BROWSER%' -ArgumentList '--app=http://localhost:8002/?fresh=%RANDOM%','--window-size=1200,800','--autoplay-policy=no-user-gesture-required'"
) else (
    start "" powershell -WindowStyle Hidden -Command "for($i=0;$i -lt 60;$i++){try{Invoke-WebRequest 'http://127.0.0.1:8002' -UseBasicParsing -TimeoutSec 1|Out-Null;break}catch{Start-Sleep -Milliseconds 500}}; Start-Process 'http://localhost:8002/?fresh=%RANDOM%'"
)

python -m http.server 8002 --bind 127.0.0.1

echo.
echo   TriggerWord stopped.
pause
