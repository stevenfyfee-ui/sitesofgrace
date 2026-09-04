@echo off
setlocal
cd /d "%~dp0"
title Sites of Grace - Pilgrimage Trails (local)

echo ==========================================================
echo   Pilgrimage Trails - set up on THIS machine
echo ==========================================================
echo.
echo  This does four things:
echo    1. starts the local database
echo    2. adds the two new trail tables
echo    3. imports the Mission Trail, the Camino, and 3 new sites
echo    4. starts the dev server so you can look at it
echo.
echo  Nothing is pushed. Nothing touches the live site.
echo.
pause

echo.
echo [1/5] Starting the local database container...
docker compose up -d db
if errorlevel 1 goto :nodb
echo Waiting for Postgres to accept connections...
timeout /t 10 /nobreak >nul

call venv\Scripts\activate.bat
if errorlevel 1 goto :novenv

echo.
echo [2/5] Applying the migration (adds two new tables, changes nothing else)...
python manage.py migrate
if errorlevel 1 goto :failed

echo.
echo [3/5] DRY RUN - this saves nothing, it just shows what would happen.
echo.
python manage.py import_trails catalog/data/california-mission-trail.json --dry-run
if errorlevel 1 goto :failed
echo.
python manage.py import_trails catalog/data/camino-de-santiago.json --dry-run
if errorlevel 1 goto :failed
echo.
python manage.py import_trails catalog/data/new-sites-2026-09.json --dry-run
if errorlevel 1 goto :failed

echo.
echo ==========================================================
echo   Read the three summaries above. Expect roughly:
echo.
echo     sites: 21 created  trails: 1 created  stops: 21 created
echo     sites:  0 created  trails: 1 created  stops: 18 created
echo     sites:  3 created  trails: 0 created  stops:  0 created
echo.
echo   A warning about 'santiago-de-compostela' is fine - it just
echo   means the Camino's last stop stays a plain waypoint.
echo ==========================================================
echo.
set /p GO="Import it for real? (Y/N) "
if /i not "%GO%"=="Y" goto :cancelled

echo.
echo [4/5] Importing for real...
python manage.py import_trails catalog/data/california-mission-trail.json
if errorlevel 1 goto :failed
python manage.py import_trails catalog/data/camino-de-santiago.json
if errorlevel 1 goto :failed
python manage.py import_trails catalog/data/new-sites-2026-09.json
if errorlevel 1 goto :failed

echo.
echo Rebuilding the search index...
python manage.py update_index

echo.
echo [5/5] Starting the dev server.
echo.
echo ==========================================================
echo   Open these in your browser:
echo.
echo     http://127.0.0.1:8000/explore/pilgrimage-routes/
echo     http://127.0.0.1:8000/interactive-map/
echo     http://127.0.0.1:8000/explore/shrines-and-basilicas/
echo.
echo   Press Ctrl+C in this window when you are done looking.
echo ==========================================================
echo.
python manage.py runserver
goto :end

:nodb
echo.
echo  ---- Could not start the database ----
echo  Docker Desktop is probably not running. Start it, wait for
echo  the whale icon to go steady, then run this file again.
echo.
pause
exit /b 1

:novenv
echo.
echo  ---- Could not activate the virtual environment ----
echo  Expected it at: %CD%\venv\Scripts\activate.bat
echo.
pause
exit /b 1

:cancelled
echo.
echo  Nothing was saved. The dry run rolled everything back.
echo.
pause
exit /b 0

:failed
echo.
echo  ---- Something above failed. Nothing further was run. ----
echo  Copy the error text and send it to me.
echo.
pause
exit /b 1

:end
endlocal
