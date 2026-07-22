# MStock 1.0.0

Prywatny system wspomagania decyzji tradingowych dla GPW i rynku USA. Łączy dane cenowe, fundamentalne, news, analizę techniczną, kalibrowane rekomendacje, modele ML, backtest oraz paper trading. Brak pozycji jest pełnoprawną decyzją systemu.

> MStock nie jest automatycznym doradcą inwestycyjnym. Wyniki historyczne i paper trading nie gwarantują przyszłych rezultatów.

## Architektura

- `backend/` — FastAPI, PostgreSQL, SQLAlchemy i migracje Alembic,
- `frontend/` — React z produkcyjnym buildem Vite, serwowany przez lekki serwer Node,
- `backup/` — backup i kontrolowane odtwarzanie PostgreSQL,
- `mstock-*.service` — jednostki systemd.

## Instalacja produkcyjna

Wymagane są Python 3, Node.js/npm, PostgreSQL oraz skonfigurowany `backend/.env`.

```bash
cd /home/tt38dn/MStock
sudo ./install-service.sh
```

Instalator:

1. buduje skompresowany frontend `dist`,
2. instaluje jednostki systemd,
3. wykonuje migracje przy starcie backendu,
4. uruchamia obie usługi.

Adresy w sieci LAN:

- frontend: `http://192.168.0.168:5173`,
- frontend health: `http://192.168.0.168:5173/healthz`,
- backend health: `http://192.168.0.168:8000/health`,
- dokumentacja API: `http://192.168.0.168:8000/docs`.

## Konfiguracja

Skopiuj przykład i ustaw własne wartości:

```bash
cp backend/.env.example backend/.env
```

Najważniejsze zmienne:

- `DATABASE_URL` — połączenie PostgreSQL,
- `ADMIN_API_KEY` — ochrona operacji administracyjnych,
- klucze aktywnych providerów danych,
- parametry schedulera, kosztów i monitoringu ML.

Jeśli operacje administracyjne mają być dostępne z frontendu w LAN, tę samą wartość ustaw podczas buildu jako `VITE_ADMIN_API_KEY`. Należy traktować ją jako sekret urządzeń mających dostęp do aplikacji.

## Testy

```bash
cd backend
.venv/bin/python3 -m pytest -q

cd ../frontend
npm run build
```

## Backup i restore

Ręczny backup PostgreSQL i modeli ML:

```bash
./backup/mstock-backup.sh
```

Kontrolowane odtworzenie:

```bash
sudo systemctl stop mstock-backend
./backup/restore-postgres.sh /ścieżka/mstock.dump --confirm
sudo systemctl start mstock-backend
```

Skrypt restore najpierw tworzy lokalny dump bezpieczeństwa bieżącej bazy.

## Eksploatacja

Pełna procedura wdrożenia, smoke testu, diagnostyki i odtwarzania znajduje się w [RUNBOOK.md](RUNBOOK.md). Historia wydania znajduje się w [CHANGELOG.md](CHANGELOG.md).
