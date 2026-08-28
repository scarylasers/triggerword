@echo off
REM TriggerWord updater. Downloads the latest version from GitHub and
REM replaces the app files in place. Your sounds and settings are safe -
REM they live in your browser, not in this folder.
REM
REM Stage 1: re-run from TEMP so this file can be overwritten mid-update.
if /i "%~1"=="" (
    copy /y "%~f0" "%TEMP%\triggerword-updater.bat" >nul
    start "TriggerWord Updater" cmd /c ""%TEMP%\triggerword-updater.bat" "%~dp0.""
    exit /b 0
)

set "APPDIR=%~1"
title TriggerWord Updater
echo.
echo   Updating TriggerWord in:
echo   %APPDIR%
echo.

echo   Closing TriggerWord if it is running...
powershell -Command "Get-WmiObject Win32_Process -Filter 'Name=\"python.exe\"' | Where-Object { $_.CommandLine -like '*local_server*' -or $_.CommandLine -like '*triggerword_router*' -or $_.CommandLine -like '*http.server 8002*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

set "TMPD=%TEMP%\triggerword-update"
rmdir /s /q "%TMPD%" 2>nul
mkdir "%TMPD%"

echo   Downloading the latest version...
curl -sL -o "%TMPD%\tw.zip" https://github.com/scarylasers/triggerword/archive/refs/heads/master.zip
if errorlevel 1 goto :fail

echo   Unpacking...
tar -xf "%TMPD%\tw.zip" -C "%TMPD%"
if errorlevel 1 goto :fail

echo   Installing...
robocopy "%TMPD%\triggerword-master" "%APPDIR%" /E /NFL /NDL /NJH /NJS >nul
if errorlevel 8 goto :fail

rmdir /s /q "%TMPD%" 2>nul

echo.
echo   Update complete! Starting TriggerWord...
start "" /d "%APPDIR%" start-triggerword.bat
exit /b 0

:fail
echo.
echo   Update failed. Check your internet connection, or re-download
echo   TriggerWord from https://github.com/scarylasers/triggerword
echo.
pause
exit /b 1
