@echo off
REM MMCVRPTW-MLT V4 launcher (Windows). Mirror of run.sh logic.
REM - Creates .venv if missing, installs pinned Python deps.
REM - Installs frontend deps if missing.
REM - Runs MANDATORY self-tests per spec §15 BEFORE launching servers.
REM - Starts backend on :8000 and frontend on :5173.

setlocal enabledelayedexpansion
cd /d "%~dp0"

REM ---- Python check ----
set PYTHON=
where python3.12 >nul 2>&1 && set PYTHON=python3.12
if "%PYTHON%"=="" where python3.11 >nul 2>&1 && set PYTHON=python3.11
if "%PYTHON%"=="" where python >nul 2>&1 && (
    for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do (
        set "PYVER=%%v"
    )
    set PYTHON=python
)
if "%PYTHON%"=="" (
    echo ERROR: Python 3.11+ required. Install from https://www.python.org/downloads/
    exit /b 1
)
echo Using Python: %PYTHON%

REM ---- Node check ----
where node >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js 18+ required. Install from https://nodejs.org/
    exit /b 1
)

REM ---- Backend venv + deps ----
if not exist .venv (
    echo Creating .venv...
    %PYTHON% -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --quiet --upgrade pip
echo Installing Python dependencies...
pip install --quiet -r requirements.txt

REM ---- Self-tests gate ----
echo.
echo ==^> Running mandatory self-tests (S1-S6) per spec section 15...
pytest backend\tests\ -v --tb=short
if errorlevel 1 (
    echo.
    echo ERROR: Self-tests failed. Refusing to launch.
    exit /b 1
)
echo ==^> All self-tests passed.
echo.

REM ---- Frontend deps ----
if not exist frontend\node_modules (
    echo Installing frontend dependencies...
    pushd frontend
    call npm install
    popd
)

REM ---- Launch ----
echo Starting backend on http://localhost:8000 ...
start "MMCVRPTW backend" cmd /k "call .venv\Scripts\activate.bat && uvicorn backend.main:app --host 0.0.0.0 --port 8000"

echo Starting frontend on http://localhost:5173 ...
pushd frontend
start "MMCVRPTW frontend" cmd /k "npm run dev"
popd

timeout /t 4 >nul
start "" http://localhost:5173

echo.
echo Backend + frontend launched in separate windows. Close those windows to stop.
endlocal
