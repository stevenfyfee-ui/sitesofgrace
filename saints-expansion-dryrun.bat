@echo off
setlocal
REM ===================================================================
REM  Sites of Grace - saints expansion, DRY RUN (nothing is saved)
REM
REM  Double-click this first. It reports what the import would do and
REM  rolls everything back. Runs against your LOCAL database only.
REM ===================================================================

set "REPO=%~dp0"
set "REPO=%REPO:~0,-1%"
cd /d "%REPO%"

set "PY=%REPO%\venv\Scripts\python.exe"
set "BOOK=%REPO%\tools\SitesOfGrace_Saints_EXPANSION_2026-09.xlsx"

if not exist "%PY%" (
  echo Could not find the virtualenv python at:
  echo   %PY%
  echo.
  pause
  exit /b 1
)
if not exist "%BOOK%" (
  echo Could not find the workbook at:
  echo   %BOOK%
  echo.
  pause
  exit /b 1
)

echo ============================================================
echo  1 of 2  -  importing 290 new saints  (DRY RUN)
echo ============================================================
"%PY%" manage.py import_catalog "%BOOK%" --only saints --dry-run
echo.
echo ============================================================
echo  2 of 2  -  patching dates on existing saints  (DRY RUN)
echo ============================================================
"%PY%" manage.py patch_saint_dates "%BOOK%" --dry-run
echo.
echo ============================================================
echo  Nothing was saved. If the numbers look right, run
echo  saints-expansion-apply.bat next.
echo ============================================================
pause
