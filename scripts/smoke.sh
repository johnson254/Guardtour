#!/usr/bin/env bash
# scripts/smoke.sh — local smoke test for GuardTour_Full
# Starts Django dev server, curls key endpoints, kills server.
set -euo pipefail

PORT="${1:-8080}"
BASE_URL="http://127.0.0.1:${PORT}"
LOG_FILE="/tmp/guardtour_smoke_$$.log"

echo "[smoke] Starting Django dev server on port ${PORT}..."
python3 manage.py runserver "${PORT}" > "${LOG_FILE}" 2>&1 &
SERVER_PID=$!

cleanup() {
  echo "[smoke] Stopping server (pid ${SERVER_PID})..."
  kill "${SERVER_PID}" 2>/dev/null || true
  wait "${SERVER_PID}" 2>/dev/null || true
}
trap cleanup EXIT

# Wait for server to be ready
echo "[smoke] Waiting for server..."
for i in $(seq 1 30); do
  if curl -s -o /dev/null "${BASE_URL}/login/" 2>/dev/null; then
    echo "[smoke] Server ready after ${i}s"
    break
  fi
  sleep 1
done

PASS=0
FAIL=0

check() {
  local desc="$1"
  local expected="$2"
  local actual="$3"
  if [ "${expected}" = "${actual}" ]; then
    echo "[PASS] ${desc} -> ${actual}"
    PASS=$((PASS+1))
  else
    echo "[FAIL] ${desc} -> expected ${expected}, got ${actual}"
    FAIL=$((FAIL+1))
  fi
}

# 1. Login page returns 200 or 302
LOGIN_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/login/")
check "GET /login/" "200|302" "${LOGIN_CODE}"

# 2. Bad creds on /api/login/ returns 400/401
API_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${BASE_URL}/api/login/" \
  -H "Content-Type: application/json" \
  -d '{"username":"bad","password":"bad"}')
check "POST /api/login/ bad creds" "400|401" "${API_CODE}"

# 3. Dashboard redirects without auth (302) or returns 200
DASH_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/dashboard/")
check "GET /dashboard/" "200|302" "${DASH_CODE}"

echo ""
echo "[smoke] Results: ${PASS} passed, ${FAIL} failed"
if [ "${FAIL}" -gt 0 ]; then
  echo "[smoke] Server log tail:"
  tail -20 "${LOG_FILE}"
  exit 1
fi
