#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"

echo "== ThesisLab full-stack start =="

if ! command -v python3 >/dev/null 2>&1; then
  echo "Brakuje python3"
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "Brakuje npm"
  exit 1
fi

cd "$BACKEND_DIR"

if [ ! -d ".venv" ]; then
  echo "Tworzenie backend/.venv"
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
pip install -r requirements.txt >/dev/null

DB_FILE=$(python - <<'PY'
from pathlib import Path
db_url = "sqlite:///./thesislab.db"
env_path = Path(".env")
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("DATABASE_URL="):
            db_url = line.split("=", 1)[1].strip()
            break
if db_url.startswith("sqlite:///./"):
    print(db_url.replace("sqlite:///./", ""))
else:
    print("")
PY
)

if [ -n "$DB_FILE" ] && [ -f "$DB_FILE" ]; then
  python - <<PY
import sqlite3, sys
db = r"$DB_FILE"
conn = sqlite3.connect(db)
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = {row[0] for row in cur.fetchall()}
try:
    cur.execute("SELECT version_num FROM alembic_version")
    row = cur.fetchone()
    current = row[0] if row else ""
except Exception:
    current = ""
if {"news_nlp_runs","news_narrative_predictions","alerts","alert_rules"}.issubset(tables) and current and current < "0005_nlp_and_alerts":
    sys.exit(10)
if {"watchlists","watchlist_items","user_preferences","notification_channels","notification_events"}.issubset(tables) and current and current < "0006_watchlists_reports_notifications":
    sys.exit(11)
PY
  RC=$?
  if [ "$RC" = "10" ]; then
    echo "Stamping alembic -> 0005_nlp_and_alerts"
    alembic stamp 0005_nlp_and_alerts
  elif [ "$RC" = "11" ]; then
    echo "Stamping alembic -> 0006_watchlists_reports_notifications"
    alembic stamp 0006_watchlists_reports_notifications
  fi
fi

echo "Applying migrations..."
alembic upgrade head

if [ -f "$PROJECT_DIR/backend.pid" ] && kill -0 "$(cat "$PROJECT_DIR/backend.pid")" >/dev/null 2>&1; then
  echo "Backend already running"
else
  echo "Starting backend..."
  nohup "$BACKEND_DIR/.venv/bin/uvicorn" main:app --reload --host 0.0.0.0 --port 8000 > "$PROJECT_DIR/backend.log" 2>&1 &
  echo $! > "$PROJECT_DIR/backend.pid"
fi

cd "$FRONTEND_DIR"
if [ ! -d "node_modules" ]; then
  npm install >/dev/null
fi

if [ -f "$PROJECT_DIR/frontend.pid" ] && kill -0 "$(cat "$PROJECT_DIR/frontend.pid")" >/dev/null 2>&1; then
  echo "Frontend already running"
else
  echo "Starting frontend..."
  nohup npm run dev -- --host 0.0.0.0 > "$PROJECT_DIR/frontend.log" 2>&1 &
  echo $! > "$PROJECT_DIR/frontend.pid"
fi

echo ""
echo "Gotowe."
echo "Backend:  http://127.0.0.1:8000  (LAN: http://192.168.0.161:8000)"
echo "Frontend: http://127.0.0.1:5173  (LAN: http://192.168.0.161:5173)"
echo ""
echo "Logi:"
echo "  tail -f backend.log"
echo "  tail -f frontend.log"
