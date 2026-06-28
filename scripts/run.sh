#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$REPO_ROOT"
FRONTEND_DIR="$BACKEND_DIR/static"
VENV_DIR="/home/jay/Desktop/projects/venv"
LOG_DIR="$REPO_ROOT/.logs"

PY="${VENV_DIR}/bin/python"
NPM="npm"
NODE="${NODE:-node}"

DAPHNE_PORT="${DAPHNE_PORT:-8080}"
VITE_PORT="${VITE_PORT:-5173}"
NGROK_PORT="${NGROK_PORT:-${DAPHNE_PORT:-8080}}"

die() {
  printf '%s\n' "$*" >&2
  exit 1
}
port_in_use() {
  ss -tlnp | awk -v p=":$1 " 'index($0, p) {found=1} END {exit found?0:1}'
}
wait_for_port() {
  local port="$1"
  local tries=60
  local delay=0.5
  for i in $(seq 1 "$tries"); do
    if ss -tlnp | awk -v p=":$1 " 'index($0, p) {found=1} END {exit found?0:1}'; then
      return 0
    fi
    sleep "$delay"
  done
  return 1
}

# Check optional dependencies
if ! command -v ngrok >/dev/null 2>&1; then
  echo "Warning: ngrok not installed. Skipping ngrok tunnel."
  START_NGROK=false
else
  START_NGROK=true
fi
# Remove stale pyc and cache dirs without nuking real code.
find "$REPO_ROOT" \( -name '__pycache__' -o -name '*.pyc' \) -prune -print | while IFS= read -r p; do
  rm -rf -- "$p"
done

if [ ! -x "$PY" ] && [ ! -f "$VENV_DIR/bin/python" ]; then
  die "Backend venv not found at: $VENV_DIR\nRun scripts/setup.sh first."
fi
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  die "Frontend deps missing at: $FRONTEND_DIR/node_modules\nRun scripts/setup.sh first."
fi
if [ ! -f "$BACKEND_DIR/manage.py" ]; then
  die "manage.py not found in: $BACKEND_DIR"
fi

echo "Pre-flight checks passed."
echo

if port_in_use "$DAPHNE_PORT"; then
  die "Daphne port $DAPHNE_PORT is already in use. Pick another one with DAPHNE_PORT=."
fi
if port_in_use "$VITE_PORT"; then
  die "Vite port $VITE_PORT is already in use. Pick another one with VITE_PORT=."
fi

# Build Vite assets first so the manifest exists and Django can resolve them.
echo "Building frontend assets..."
pushd "$FRONTEND_DIR" >/dev/null
"$NPM" run build
popd >/dev/null

# Start Daphne in the background, funnel logs through a pager-friendly file.
echo "Starting Daphne on http://127.0.0.1:$DAPHNE_PORT ..."
(
  cd "$BACKEND_DIR"
  DJANGO_SETTINGS_MODULE=guardtour.settings "$PY" manage.py runserver 0.0.0.0:"$DAPHNE_PORT" --noreload > "$LOG_DIR/daphne.log" 2>&1
) &
BACKEND_PID=$!

# Optional: start Vite dev proxy on its own port.
echo "Starting Vite on http://127.0.0.1:$VITE_PORT ..."
(
  cd "$FRONTEND_DIR"
  "$NPM" run dev > "$LOG_DIR/vite.log" 2>&1
) &
FRONTEND_PID=$!

cleanup() {
  set +e
  echo
  echo "Shutting down..."
  kill "$BACKEND_PID" >/dev/null 2>&1 || true
  kill "$FRONTEND_PID" >/dev/null 2>&1 || true
}
trap cleanup INT TERM EXIT

if ! wait_for_port "$DAPHNE_PORT"; then
  die "Daphne did not bind port $DAPHNE_PORT in time.\nTail $LOG_DIR/daphne.log"
fi
if ! wait_for_port "$VITE_PORT"; then
  die "Vite did not bind port $VITE_PORT in time.\nTail $LOG_DIR/vite.log"
fi

echo
echo "Ready"
echo "  Django : http://127.0.0.1:$DAPHNE_PORT"
echo "  Vite   : http://127.0.0.1:$VITE_PORT"
echo "  Logs   : $LOG_DIR"
echo
echo "Press Ctrl+C to stop both."

wait
