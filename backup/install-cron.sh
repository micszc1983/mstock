#!/usr/bin/env bash
# =============================================================================
# INSTALACJA CRONA — uruchom po setup-nas-ssh.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_PATH="$SCRIPT_DIR/mstock-backup.sh"
LOG_PATH="$SCRIPT_DIR/backup.log"
CRON_LOG_PATH="$SCRIPT_DIR/cron.log"

chmod +x "$SCRIPT_PATH"

# Dodaj do crontab (3:00 każdej nocy) — nie duplikuj jeśli już jest
CRON_LINE="0 3 * * * $SCRIPT_PATH >> $CRON_LOG_PATH 2>&1"

# Usuń każdą starszą wersję zadania, również ze starą ścieżką lub logiem.
CURRENT_CRONTAB="$(crontab -l 2>/dev/null || true)"
CLEAN_CRONTAB="$(printf '%s\n' "$CURRENT_CRONTAB" | grep -v 'mstock-backup\.sh' || true)"
{
    printf '%s\n' "$CLEAN_CRONTAB"
    printf '%s\n' "$CRON_LINE"
} | crontab -
echo "Cron ustawiony: backup codziennie o 3:00"

echo ""
echo "Aktualne zadania cron:"
crontab -l

echo ""
echo "Aby uruchomić backup ręcznie teraz:"
echo "  bash $SCRIPT_PATH"
echo ""
echo "Logi backupu:"
echo "  tail -f $LOG_PATH"
echo "  tail -f $CRON_LOG_PATH"
