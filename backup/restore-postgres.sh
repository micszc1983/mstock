#!/usr/bin/env bash
# Kontrolowane odtworzenie PostgreSQL z dumpa MStock.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
DUMP_FILE="${1:-}"
CONFIRM="${2:-}"

if [ -z "$DUMP_FILE" ] || [ ! -f "$DUMP_FILE" ]; then
  echo "Użycie: $0 /ścieżka/mstock.dump --confirm"
  exit 2
fi
if [ "$CONFIRM" != "--confirm" ]; then
  echo "Odtworzenie zastąpi dane w aktywnej bazie. Dodaj --confirm po sprawdzeniu pliku."
  exit 2
fi
if systemctl is-active --quiet mstock-backend 2>/dev/null; then
  echo "Najpierw zatrzymaj zapisy: sudo systemctl stop mstock-backend"
  exit 3
fi

eval "$(cd "$BACKEND_DIR" && .venv/bin/python3 - <<'PY'
import shlex
from sqlalchemy.engine import make_url
from app.core.config import settings

url = make_url(settings.database_url)
if not url.drivername.startswith("postgresql"):
    raise SystemExit("Restore 1.0 wymaga PostgreSQL")
for key, value in {
    "PGHOST": url.host or "localhost", "PGPORT": url.port or 5432,
    "PGUSER": url.username or "", "PGPASSWORD": url.password or "",
    "PGDATABASE": url.database or "",
}.items():
    print(f"{key}={shlex.quote(str(value))}")
PY
)"
export PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE

pg_restore --list "$DUMP_FILE" >/dev/null
mkdir -p "$BACKEND_DIR/backups"
SAFETY_DUMP="$BACKEND_DIR/backups/pre-restore-$(date +%Y%m%d-%H%M%S).dump"
echo "Tworzę awaryjny dump bieżącej bazy: $SAFETY_DUMP"
pg_dump --format=custom --no-owner --file="$SAFETY_DUMP"

echo "Odtwarzam bazę z: $DUMP_FILE"
pg_restore --clean --if-exists --no-owner --exit-on-error --dbname="$PGDATABASE" "$DUMP_FILE"
(cd "$BACKEND_DIR" && .venv/bin/python3 -m alembic upgrade head)

echo "Restore zakończony. Uruchom: sudo systemctl start mstock-backend"
echo "Awaryjna kopia stanu sprzed restore: $SAFETY_DUMP"
