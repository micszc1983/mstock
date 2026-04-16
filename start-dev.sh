#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

if [ ! -d "$BACKEND_DIR/.venv" ]; then
  echo "Brak backend/.venv."
  echo "Uruchom: cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "Brak frontend/node_modules."
  echo "Uruchom: cd frontend && npm install"
  exit 1
fi

mkdir -p "$ROOT_DIR/.run"

(
  cd "$BACKEND_DIR"
  source .venv/bin/activate
  nohup python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000 > "$ROOT_DIR/.run/backend.log" 2>&1 &
  echo $! > "$ROOT_DIR/.run/backend.pid"
)

(
  cd "$FRONTEND_DIR"
  nohup npm run dev -- --host 0.0.0.0 > "$ROOT_DIR/.run/frontend.log" 2>&1 &
  echo $! > "$ROOT_DIR/.run/frontend.pid"
)

echo "Backend PID: $(cat "$ROOT_DIR/.run/backend.pid")"
echo "Frontend PID: $(cat "$ROOT_DIR/.run/frontend.pid")"
echo "Backend:  http://127.0.0.1:8000  (LAN: http://192.168.0.161:8000)"
echo "Frontend: http://127.0.0.1:5173  (LAN: http://192.168.0.161:5173)"
echo "Logi: .run/backend.log i .run/frontend.log"
