# ThesisLab Runbook

## Start
```bash
chmod +x start.sh stop.sh
./start.sh
```

## Stop
```bash
./stop.sh
```

## Gdzie wpisać klucze API
Plik:
```bash
backend/.env
```

Przykład:
```bash
DATABASE_URL=sqlite:///./thesislab.db
ALPHAVANTAGE_API_KEY=twoj_klucz_alpha_vantage
FINNHUB_API_KEY=twoj_klucz_finnhub

SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=twoj_smtp_user
SMTP_PASSWORD=twoje_haslo
SMTP_FROM_EMAIL=alerts@example.com

TWILIO_ACCOUNT_SID=twoj_twilio_sid
TWILIO_AUTH_TOKEN=twoj_twilio_token
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
REPORTS_DIR=./generated_reports
```

## Gdy SQLite zgłasza konflikt migracji
Najpierw:
```bash
./stop.sh
./start.sh
```

Skrypt próbuje automatycznie naprawić typowy konflikt `table already exists`.

Jeśli to nadal dev i nie potrzebujesz danych:
```bash
cd backend
rm -f thesislab.db
source .venv/bin/activate
alembic upgrade head
cd ..
./start.sh
```

## Szybka diagnostyka
```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/assets
curl -X POST http://127.0.0.1:8000/assets/aapl/bootstrap
```


## Audit-fix changes
This package additionally:
- removes `Base.metadata.create_all(...)` from backend startup
- adds shared `backend/app/utils/datetime.py`
- normalizes UTC handling in analytics, feature builder, outcomes and alerts
- secures report download route to `/reports/download/{file_name}`
- fixes `Hero.tsx` / `App.tsx` prop mismatch


## ML foundation
Dodane endpointy:
- `GET /ml/status`
- `POST /ml/mode`
- `POST /ml/dataset/build`
- `GET /ml/dataset/stats`
- `POST /ml/models/train`
- `GET /ml/models`
- `POST /ml/backtests/run`
- `GET /ml/backtests`
- `POST /assets/{asset_id}/ml/score`
- `GET /assets/{asset_id}/ml/prediction/latest`

Workflow:
1. pozwól systemowi zbierać dane przez dni/tygodnie
2. uruchom build dataset
3. gdy liczba wierszy będzie sensowna, wytrenuj model
4. uruchom backtest
5. przełącz tryb heurystyka/ML w interfejsie


## Walk-forward and comparison
Dodane endpointy:
- `POST /ml/backtests/walkforward`
- `POST /assets/{asset_id}/evaluation/compare`
- `GET /assets/{asset_id}/evaluation/latest`
- `GET /evaluation/comparisons`

Po treningu modelu możesz:
1. uruchomić zwykły backtest
2. uruchomić walk-forward backtest
3. porównać heurystykę z ML dla wybranego aktywa
4. obserwować w UI, który tryb jest obecnie lepszy
