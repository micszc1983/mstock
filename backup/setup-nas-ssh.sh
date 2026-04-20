#!/bin/bash
# =============================================================================
# JEDNORAZOWA KONFIGURACJA SSH DO QNAP NAS
# Uruchom raz: bash setup-nas-ssh.sh
# Hasło będzie potrzebne tylko podczas tego kroku.
# =============================================================================

NAS_USER="dev"
NAS_HOST="192.168.0.200"
KEY_FILE="$HOME/.ssh/nas_mstock"

echo ">>> Generowanie klucza SSH (bez hasła — do cron)..."
ssh-keygen -t ed25519 -f "$KEY_FILE" -N "" -C "mstock-backup@$(hostname)"

echo ""
echo ">>> Kopiowanie klucza publicznego na QNAP NAS..."
echo "    Zostaniesz poproszony o hasło użytkownika '$NAS_USER' — wpisz: Lenovos10!"
echo ""
ssh-copy-id -i "$KEY_FILE.pub" -p 22 "${NAS_USER}@${NAS_HOST}"

echo ""
echo ">>> Test połączenia (nie powinno pytać o hasło)..."
ssh -i "$KEY_FILE" "${NAS_USER}@${NAS_HOST}" "echo 'Połączenie SSH OK — $(date)'"

echo ""
echo ">>> Tworzenie folderu backupów na NAS..."
ssh -i "$KEY_FILE" "${NAS_USER}@${NAS_HOST}" "mkdir -p /share/Pliki_ms/dev_backup/mstock"

echo ""
echo "================================================================"
echo "  Konfiguracja zakończona."
echo "  Klucz prywatny: $KEY_FILE"
echo "  Teraz uruchom: bash install-cron.sh"
echo "================================================================"
