@echo off
setlocal
REM ===================================================================
REM  Sites of Grace - turn on automatic pushing
REM
REM  Double-click once. After that, any file change made in this folder
REM  by any Claude session gets committed and pushed to main on its own,
REM  which deploys it to the live site.
REM ===================================================================

set "REPO=%~dp0"
set "REPO=%REPO:~0,-1%"
set "RUNNER=%REPO%\tools\autopush-run.bat"
set "SILENT=%REPO%\tools\autopush-silent.vbs"
set "TASKNAME=SitesOfGrace AutoPush"

echo ===================================================================
echo  Sites of Grace - automatic push setup
echo ===================================================================
echo.
echo  Folder: %REPO%
echo.

if not exist "%RUNNER%" (
  echo  ERROR: cannot find %RUNNER%
  echo  Setup stopped. Nothing was changed.
  goto :end
)
if not exist "%SILENT%" (
  echo  ERROR: cannot find %SILENT%
  echo  Setup stopped. Nothing was changed.
  goto :end
)

echo "%REPO%" | findstr /C:" " >nul
if not errorlevel 1 (
  echo  NOTE: this folder path contains a space, so the task is being
  echo  registered with extra quoting. If the log stays empty, tell Claude.
  echo.
  schtasks /Create /TN "%TASKNAME%" /SC MINUTE /MO 5 /F /TR "wscript.exe //B \"%SILENT%\"" >nul
) else (
  schtasks /Create /TN "%TASKNAME%" /SC MINUTE /MO 5 /F /TR "wscript.exe //B %SILENT%" >nul
)

if errorlevel 1 (
  echo.
  echo  ERROR: could not create the scheduled task.
  echo  Close this window, right-click setup-autopush.bat, and choose
  echo  "Run as administrator", then try again.
  goto :end
)

echo  Scheduled task created - it will check every 5 minutes, silently.
echo.
echo  Running one cycle now so you can see it work. If a GitHub sign-in
echo  window opens, approve it - that only happens the first time.
echo.
call "%RUNNER%" /quiet
echo.
echo --- log ---
powershell.exe -NoProfile -Command "Get-Content '%REPO%\tools\autopush.log' -Tail 15 -ErrorAction SilentlyContinue"
echo.
echo ===================================================================
echo  Automatic pushing is ON.
echo.
echo  The cycle you just watched only took note of the changes. The one
echo  five minutes from now is what actually pushes. That pause is
echo  deliberate - it keeps a half-written file off the live site.
echo.
echo  To pause it:   create an empty file named .autopush-pause here
echo  To resume:     delete that file
echo  To turn off:   run tools\uninstall-autopush.bat
echo  To see what happened: open tools\autopush.log
echo.
echo  If anything is ever wrong it refuses to push and writes
echo  AUTOPUSH-BLOCKED.txt in this folder explaining why.
echo ===================================================================

:end
echo.
pause
endlocal
