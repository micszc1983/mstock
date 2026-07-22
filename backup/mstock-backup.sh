#!/usr/bin/env bash
# Codzienny backup MStock 1.0: PostgreSQL + modele ML -> QNAP NAS.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
MODELS_DIR="$BACKEND_DIR/ml_models"
LOG_FILE="$PROJECT_DIR/backup/backup.log"

NAS_USER="dev"
NAS_HOST="192.168.0.200"
NAS_BASE="/share/Pliki_ms/dev_backup/mstock"
KEY_FILE="$HOME/.ssh/nas_mstock"
DATE="$(date +%Y-%m-%d)"
NAS_DIR="$NAS_BASE/$DATE"
NAS="$NAS_USER@$NAS_HOST"
TMP_DUMP="$(mktemp /tmp/mstock-backup-XXXXXX.dump)"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }
cleanup() { rm -f "$TMP_DUMP"; }
trap cleanup EXIT

load_postgres_connection() {
  eval "$(cd "$BACKEND_DIR" && .venv/bin/python3 - <<'PY'
import shlex
from sqlalchemy.engine import make_url
from app.core.config import settings

url = make_url(settings.database_url)
if not url.drivername.startswith("postgresql"):
    raise SystemExit("Backup 1.0 wymaga DATABASE_URL wskazującego PostgreSQL")
values = {
    "PGHOST": url.host or "localhost",
    "PGPORT": url.port or 5432,
    "PGUSER": url.username or "",
    "PGPASSWORD": url.password or "",
    "PGDATABASE": url.database or "",
}
for key, value in values.items():
    print(f"{key}={shlex.quote(str(value))}")
PY
)"
  export PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE
}

log "========================================"
log "Backup PostgreSQL $DATE — start"

if ! ping -c1 -W3 "$NAS_HOST" >/dev/null 2>&1; then
  log "BŁĄD: NAS $NAS_HOST niedostępny"
  exit 1
fi
if [ ! -f "$KEY_FILE" ]; then
  log "BŁĄD: brak klucza $KEY_FILE"
  exit 1
fi

load_postgres_connection
ssh -i "$KEY_FILE" -o ConnectTimeout=10 "$NAS" "mkdir -p '$NAS_DIR'"

log "Tworzenie spójnego dumpa PostgreSQL..."
pg_dump --format=custom --no-owner --file="$TMP_DUMP"
pg_restore --list "$TMP_DUMP" >/dev/null
DUMP_SIZE="$(du -sh "$TMP_DUMP" | cut -f1)"
rsync -az -e "ssh -i $KEY_FILE -o ConnectTimeout=10" \
  "$TMP_DUMP" "$NAS:$NAS_DIR/mstock.dump"
log "  Baza OK — $DUMP_SIZE, format zweryfikowany przez pg_restore"

if [ -d "$MODELS_DIR" ]; then
  MODEL_COUNT="$(find "$MODELS_DIR" -maxdepth 1 -type f -name '*.joblib' | wc -l)"
  rsync -az --delete -e "ssh -i $KEY_FILE -o ConnectTimeout=10" \
    "$MODELS_DIR/" "$NAS:$NAS_DIR/ml_models/"
  log "  Modele OK — $MODEL_COUNT plików"
else
  log "  Modele: katalog nie istnieje — pominięto"
fi

CHECKSUM="$(sha256sum "$TMP_DUMP" | cut -d' ' -f1)"
ssh -i "$KEY_FILE" "$NAS" "printf '%s  %s\n' '$CHECKSUM' 'mstock.dump' > '$NAS_DIR/mstock.dump.sha256'"
log "  SHA-256: $CHECKSUM"

log "Czyszczenie backupów starszych niż 30 dni..."
DELETED="$(ssh -i "$KEY_FILE" "$NAS" \
  "find '$NAS_BASE' -mindepth 1 -maxdepth 1 -type d -name '20*' -mtime +30 -print -exec rm -rf -- {} +" | wc -l)"
TOTAL="$(ssh -i "$KEY_FILE" "$NAS" "du -sh '$NAS_DIR'" | cut -f1)"
log "Backup zakończony: $TOTAL, usunięte stare katalogi: $DELETED"
log "========================================"
