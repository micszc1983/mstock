#!/usr/bin/env bash
# Instaluje MStock jako usługi systemd (autostart przy starcie systemu).
# Wymaga sudo. Uruchom raz: sudo ./install-service.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_USER="tt38dn"

if [ "$(id -u)" -ne 0 ]; then
  echo "Uruchom instalator przez sudo: sudo ./install-service.sh"
  exit 1
fi

echo "== Instalacja MStock jako usług systemd =="

# Upewnij się że .venv istnieje
if [ ! -f "$PROJECT_DIR/backend/.venv/bin/uvicorn" ]; then
  echo "Brak .venv — najpierw uruchom ./start.sh żeby zainstalować zależności."
  exit 1
fi

# Upewnij się że node_modules istnieje
if [ ! -d "$PROJECT_DIR/frontend/node_modules" ]; then
  echo "Brak node_modules — najpierw uruchom ./start.sh żeby zainstalować zależności."
  exit 1
fi

echo "Budowanie produkcyjnego frontendu..."
runuser -u "$SERVICE_USER" -- /bin/bash -c "cd '$PROJECT_DIR/frontend' && npm run build"

# Skopiuj service files do systemd
cp "$PROJECT_DIR/mstock-backend.service"  /etc/systemd/system/
cp "$PROJECT_DIR/mstock-frontend.service" /etc/systemd/system/

systemctl daemon-reload

systemctl enable mstock-backend
systemctl enable mstock-frontend

echo ""
echo "Usługi zainstalowane i włączone do autostartu."
echo ""
echo "Dostępne polecenia:"
echo "  sudo systemctl start   mstock-backend mstock-frontend   # ręczny start"
echo "  sudo systemctl stop    mstock-backend mstock-frontend   # zatrzymanie"
echo "  sudo systemctl restart mstock-backend                   # restart backendu"
echo "  sudo systemctl status  mstock-backend                   # sprawdź status"
echo "  journalctl -u mstock-backend -f                         # logi backendu na żywo"
echo "  journalctl -u mstock-frontend -f                        # logi frontendu na żywo"
echo ""
echo "Uruchamiam teraz..."
systemctl restart mstock-backend mstock-frontend
systemctl status mstock-backend --no-pager
systemctl status mstock-frontend --no-pager
