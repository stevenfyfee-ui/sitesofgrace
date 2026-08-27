@echo off
REM Turns automatic pushing off. Your files and git history are untouched.
schtasks /Delete /TN "SitesOfGrace AutoPush" /F
if errorlevel 1 (
  echo.
  echo Could not remove the task - it may already be gone.
) else (
  echo.
  echo Automatic pushing is OFF. Push by hand with: git push origin main
)
echo.
pause
