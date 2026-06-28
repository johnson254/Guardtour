#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$PROJECT_DIR"
FRONTEND_DIR="$PROJECT_DIR/static"
VENV_DIR="$PROJECT_DIR/.venv"
PYTHON="${PYTHON:-python3}"

portable_realpath() {
  if command -v realpath >/dev/null 2>&1; then
    realpath "$1"
  else
    python3 - <<'PY' "$1"
import os,sys,pathlib
print(pathlib.Path(sys.argv[1]).resolve())
PY
  fi
}

create_venv() {
  echo "[1/5] Creating virtualenv at: $VENV_DIR"
  if [ -d "$VENV_DIR" ]; then
    echo "      Existing venv found, reusing it."
    return
  fi
  "$PYTHON" -m venv "$VENV_DIR"
}

install_backend() {
  echo "[2/5] Installing backend requirements..."
  "$VENV_DIR/bin/pip" install --upgrade pip >/dev/null
  "$VENV_DIR/bin/pip" install -r "$BACKEND_DIR/requirements.txt"
}

install_frontend() {
  echo "[3/5] Installing frontend dependencies..."
  pushd "$FRONTEND_DIR" >/dev/null
  npm install --silent
  popd >/dev/null
}

maybe_migrate() {
  if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
    echo "[4/5] Running Django migrations..."
    cd "$BACKEND_DIR"
    DJANGO_SETTINGS_MODULE=guardtour.settings "$VENV_DIR/bin/python" manage.py migrate --noinput
  else
    echo "[4/5] Skipping migrations (set RUN_MIGRATIONS=1 to enable)."
  fi
}

summary() {
  echo "[5/5] Setup complete."
  echo
  echo " Backend venv : $VENV_DIR"
  echo " Django app   : $BACKEND_DIR"
  echo " Frontend root: $FRONTEND_DIR"
  echo
  echo " Start the app with:"
  echo "   ./scripts/run.sh"
}

create_venv
install_backend
install_frontend
maybe_migrate
summary
