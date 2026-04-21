#!/bin/bash
# =============================================================================
# CODZIENNY BACKUP MSTOCK → QNAP NAS
# Uruchamiany automatycznie przez cron o 3:00 w nocy.
# Wymaga wcześniejszego uruchomienia setup-nas-ssh.sh
# =============================================================================

set -euo pipefail

# ── Konfiguracja ─────────────────────────────────────────────────────────────
NAS_USER="dev"
NAS_HOST="192.168.0.200"
NAS_BASE="/share/Pliki_ms/dev_backup/mstock"
KEY_FILE="$HOME/.ssh/nas_mstock"

BACKEND_DIR="/home/tt38dn/MStock/backend"
DB_FILE="$BACKEND_DIR/thesislab.db"
MODELS_DIR="$BACKEND_DIR/ml_models"

LOG_FILE="/run/media/tt38dn/dane2/Gielda-fixed/backup/backup.log"
TMP_DB="/tmp/mstock-backup-$(date +%s).db"

DATE=$(date +%Y-%m-%d)
NAS_DIR="$NAS_BASE/$DATE"
NAS="$NAS_USER@$NAS_HOST"

# ── Funkcje ──────────────────────────────────────────────────────────────────
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

cleanup() { rm -f "$TMP_DB"; }
trap cleanup EXIT

# ── Start ────────────────────────────────────────────────────────────────────
log "========================================"
log "Backup $DATE — start"

# Sprawdź czy NAS osiągalny
if ! ping -c1 -W3 "$NAS_HOST" &>/dev/null; then
    log "BŁĄD: NAS $NAS_HOST niedostępny — backup pominięty"
    exit 1
fi

# Utwórz folder dnia na NAS
ssh -i "$KEY_FILE" -o ConnectTimeout=10 "$NAS" "mkdir -p $NAS_DIR"

# ── 1. Baza danych (bezpieczna kopia SQLite przez Python) ────────────────────
log "Kopia bazy danych..."
python3 - <<EOF
import sqlite3, shutil, sys
src = "$DB_FILE"
dst = "$TMP_DB"
try:
    src_conn = sqlite3.connect(src)
    dst_conn = sqlite3.connect(dst)
    src_conn.backup(dst_conn)
    dst_conn.close()
    src_conn.close()
    print("SQLite backup OK")
except Exception as e:
    print(f"BŁĄD backup: {e}", file=sys.stderr)
    sys.exit(1)
EOF
BACKUP_SIZE=$(du -sh "$TMP_DB" | cut -f1)
rsync -az --progress \
    -e "ssh -i $KEY_FILE -o ConnectTimeout=10" \
    "$TMP_DB" "$NAS:$NAS_DIR/thesislab.db"
log "  Baza OK — $BACKUP_SIZE"

# ── 2. Modele ML (tylko zmienione pliki — delta sync) ────────────────────────
log "Kopia modeli ML..."
MODEL_COUNT=$(ls "$MODELS_DIR"/*.joblib 2>/dev/null | wc -l)
rsync -az --delete \
    -e "ssh -i $KEY_FILE -o ConnectTimeout=10" \
    "$MODELS_DIR/" "$NAS:$NAS_DIR/ml_models/"
log "  Modele OK — $MODEL_COUNT plików"

# ── 3. Suma kontrolna bazy (wykryj uszkodzone kopie) ─────────────────────────
DB_CHECKSUM=$(md5sum "$TMP_DB" | cut -d' ' -f1)
ssh -i "$KEY_FILE" "$NAS" \
    "echo '$DB_CHECKSUM  thesislab.db' > $NAS_DIR/thesislab.db.md5"
log "  Checksum: $DB_CHECKSUM"

# ── 4. Usuń kopie starsze niż 30 dni ─────────────────────────────────────────
log "Czyszczenie starych backupów (>30 dni)..."
DELETED=$(ssh -i "$KEY_FILE" "$NAS" \
    "find $NAS_BASE -maxdepth 1 -type d -name '20*' -mtime +30 \
     -exec rm -rf {} + -print 2>/dev/null | wc -l")
log "  Usunięto: $DELETED starych folderów"

# ── Podsumowanie ─────────────────────────────────────────────────────────────
TOTAL=$(ssh -i "$KEY_FILE" "$NAS" "du -sh $NAS_DIR" | cut -f1)
log "Backup $DATE — ZAKOŃCZONY pomyślnie (łącznie: $TOTAL)"
log "========================================"
