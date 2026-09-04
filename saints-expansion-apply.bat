@echo off
setlocal
REM ===================================================================
REM  Sites of Grace - saints expansion, FOR REAL
REM
REM  Runs against your LOCAL database. The new pages are created
REM  hidden (not live), so nothing appears on the public saints
REM  directory until you publish it.
REM
REM  This does NOT touch the live site. See the plan doc for the one
REM  command that runs the same import against production.
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

echo.
echo This will add 290 saint pages and correct dates on 43 existing ones.
echo Local database only.
echo.
choice /c YN /m "Go ahead"
if errorlevel 2 exit /b 0

echo.
echo ============================================================
echo  1 of 3  -  importing 290 new saints
echo ============================================================
"%PY%" manage.py import_catalog "%BOOK%" --only saints
if errorlevel 1 goto failed

echo.
echo ============================================================
echo  2 of 3  -  hiding the new stubs until they have content
echo ============================================================
"%PY%" manage.py stub_saints --unpublish
if errorlevel 1 goto failed

echo.
echo ============================================================
echo  3 of 3  -  patching dates on existing saints
echo ============================================================
"%PY%" manage.py patch_saint_dates "%BOOK%"
if errorlevel 1 goto failed

echo.
echo ============================================================
echo  Done. Next:
echo    - open /admin/ and check a few of the new pages
echo    - write the summary text, then publish them in batches with
echo      venv\Scripts\python manage.py stub_saints --publish --ready
echo ============================================================
pause
exit /b 0

:failed
echo.
echo Something failed above. Nothing further was run.
pause
exit /b 1
