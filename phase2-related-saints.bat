@echo off
setlocal
REM ===================================================================
REM  Sites of Grace - Phase 2: the related_saints field
REM
REM  What this does, on your LOCAL database only:
REM    1. asks Django to generate the migration for the new field
REM    2. runs the system checks
REM    3. applies the migration locally
REM    4. dry-runs the site-to-saint linking so you see the numbers
REM
REM  It does NOT touch production and does NOT push anything. The
REM  generated migration file is left on disk for you to push after.
REM ===================================================================

set "REPO=%~dp0"
set "REPO=%REPO:~0,-1%"
cd /d "%REPO%"

set "PY=%REPO%\venv\Scripts\python.exe"
set "BOOK=%REPO%\tools\SitesOfGrace_Saints_EXPANSION_2026-09.xlsx"

if not exist "%PY%" (
  echo Could not find the virtualenv python at:
  echo   %PY%
  pause
  exit /b 1
)

echo ============================================================
echo  1 of 4  -  generating the migration
echo ============================================================
"%PY%" manage.py makemigrations catalog
if errorlevel 1 goto failed

echo.
echo ============================================================
echo  2 of 4  -  system checks
echo ============================================================
"%PY%" manage.py check
if errorlevel 1 goto failed

echo.
echo ============================================================
echo  3 of 4  -  applying it to your local database
echo ============================================================
"%PY%" manage.py migrate
if errorlevel 1 goto failed

echo.
echo ============================================================
echo  4 of 4  -  linking sites to saints  (DRY RUN, nothing saved)
echo ============================================================
"%PY%" manage.py link_site_saints "%BOOK%" --dry-run
if errorlevel 1 goto failed

echo.
echo ============================================================
echo  Done. Nothing was pushed and production is untouched.
echo.
echo  Expected from step 4: about 56 principal saints filled and
echo  20 sites given related_saints. If that looks right:
echo.
echo    - to apply it locally, rerun without --dry-run:
echo        venv\Scripts\python manage.py link_site_saints ^
echo          tools\SitesOfGrace_Saints_EXPANSION_2026-09.xlsx
echo.
echo    - to ship it, commit the new migration + models.py and push,
echo      then run the same command in the DigitalOcean console.
echo      Ask Claude and it will do the commit for you.
echo ============================================================
pause
exit /b 0

:failed
echo.
echo Stopped on an error above. Nothing further was run.
echo If step 1 reported "No changes detected", models.py did not
echo pick up the new field - tell Claude.
pause
exit /b 1
