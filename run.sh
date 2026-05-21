#!/usr/bin/env bash
# MMCVRPTW-MLT V4 launcher (macOS / Linux).
# - Creates .venv if missing, installs pinned Python deps.
# - Installs frontend deps if missing.
# - Runs MANDATORY self-tests per spec §15 BEFORE launching servers;
#   if any fail, the launcher aborts. This is the anti-shortcut gate.
# - Starts backend (uvicorn) on :8000 and frontend (vite) on :5173.

set -e
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# ---- Python check ----
# We require 3.11 or 3.12 specifically. 3.13/3.14 are too new for the pinned
# deps (numpy 1.26.4 tops out at 3.12; highspy 1.7.2 wheels are 3.10-3.12).
if command -v python3.12 &>/dev/null; then
    PYTHON=$(command -v python3.12)
elif command -v python3.11 &>/dev/null; then
    PYTHON=$(command -v python3.11)
else
    echo "ERROR: Python 3.11 or 3.12 required (3.13/3.14 are too new for the pinned deps)."
    echo "  Easiest: brew install python@3.12  (or grab the 3.12 installer from https://www.python.org/downloads/)."
    echo "  Then re-run this script."
    exit 1
fi
echo "Using $($PYTHON --version) from $PYTHON"

# ---- Node check ----
if ! command -v node &>/dev/null; then
    echo "ERROR: Node.js 18+ required."
    echo "  Install Node from https://nodejs.org/  and re-run this script."
    exit 1
fi
NODE_MAJOR=$(node -v | sed 's/v//' | cut -d. -f1)
if [ "$NODE_MAJOR" -lt 18 ]; then
    echo "ERROR: Node $(node -v) found, but 18+ required."
    exit 1
fi
echo "Using node $(node -v)"

# ---- Backend venv + deps ----
# Self-heal a broken .venv: if the directory exists but the activate script is
# missing (or points to the wrong Python), nuke it and recreate. This recovers
# from cross-platform-leftover venvs (e.g. an old Linux one).
if [ -d ".venv" ] && [ ! -f ".venv/bin/activate" ]; then
    echo "Found a broken .venv (no bin/activate); recreating..."
    rm -rf .venv
fi
if [ ! -d ".venv" ]; then
    echo "Creating .venv with $($PYTHON --version)..."
    $PYTHON -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q --upgrade pip
echo "Installing Python dependencies..."
pip install -q -r requirements.txt

# ---- MANDATORY self-tests (§15) — block launch on failure ----
echo ""
echo "==> Running mandatory self-tests (S1-S6) per spec §15..."
echo "    (These solve real MILPs and may take several minutes.)"
if ! pytest backend/tests/ -v --tb=short; then
    echo ""
    echo "ERROR: Self-tests failed. Refusing to launch."
    echo "  This is the anti-shortcut gate. Fix the failing test(s) and re-run."
    echo "  See README §Troubleshooting and spec §15 for what each test enforces."
    exit 1
fi
echo "==> All self-tests passed."
echo ""

# ---- Frontend deps ----
if [ ! -d "frontend/node_modules" ]; then
    echo "Installing frontend dependencies..."
    (cd frontend && npm install)
fi

# ---- Launch ----
echo "Starting backend on http://localhost:8000 ..."
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --log-level info &
BACKEND_PID=$!

echo "Starting frontend on http://localhost:5173 ..."
(cd frontend && npm run dev) &
FRONTEND_PID=$!

# Open browser after a short delay
sleep 4
if command -v open &>/dev/null; then open http://localhost:5173 || true
elif command -v xdg-open &>/dev/null; then xdg-open http://localhost:5173 || true
fi

cleanup() {
    echo ""
    echo "Shutting down..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
}
trap cleanup EXIT INT TERM

wait
