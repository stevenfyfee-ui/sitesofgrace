@echo off
REM Runs one auto-push cycle. Task Scheduler calls this every 5 minutes.
REM You can also double-click it to force a cycle and watch what happens.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0autopush.ps1"
if "%1"=="/quiet" goto :eof
echo.
echo --- last 20 lines of the log ---
powershell.exe -NoProfile -Command "Get-Content '%~dp0autopush.log' -Tail 20 -ErrorAction SilentlyContinue"
echo.
pause
