#!/bin/bash
# =============================================================================
# INSTALACJA CRONA — uruchom po setup-nas-ssh.sh
# =============================================================================

SCRIPT_PATH="/run/media/tt38dn/dane2/Gielda-fixed/backup/mstock-backup.sh"

chmod +x "$SCRIPT_PATH"

# Dodaj do crontab (3:00 każdej nocy) — nie duplikuj jeśli już jest
CRON_LINE="0 3 * * * $SCRIPT_PATH >> /var/log/mstock-backup.log 2>&1"

if crontab -l 2>/dev/null | grep -qF "$SCRIPT_PATH"; then
    echo "Cron już skonfigurowany — brak zmian."
else
    (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
    echo "Cron dodany: backup codziennie o 3:00"
fi

echo ""
echo "Aktualne zadania cron:"
crontab -l

echo ""
echo "Aby uruchomić backup ręcznie teraz:"
echo "  bash $SCRIPT_PATH"
echo ""
echo "Logi backupu:"
echo "  tail -f /run/media/tt38dn/dane2/Gielda-fixed/backup/backup.log"
