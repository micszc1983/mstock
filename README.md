# ThesisLab Fullstack

Gotowy projekt z rozdzielonym:
- `backend/` — FastAPI + Alembic + SQLite
- `frontend/` — Vite + React + Recharts

## Szybki start lokalny

### 1. Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --reload
```

### 2. Frontend
W drugim terminalu:
```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

## Start jedną komendą po wcześniejszej instalacji
```bash
./start-dev.sh
```

## Zatrzymanie
```bash
./stop-dev.sh
```

## Adresy
- backend: `http://127.0.0.1:8000`
- frontend: `http://127.0.0.1:5173`

## Dopięte poprawki
- backend i frontend rozdzielone na osobne katalogi
- CORS w backendzie dla Vite
- poprawka importu `Boolean` w modelach
- frontend korzysta z konfigurowalnego `apiBase`


## Gdzie wpisać klucze API
Klucze dla providerów wpisujesz w:
- `backend/.env`

Przykład:
```bash
DATABASE_URL=sqlite:///./thesislab.db
ALPHAVANTAGE_API_KEY=twoj_klucz_alpha_vantage
FINNHUB_API_KEY=twoj_klucz_finnhub
SYNC_TIMEOUT_SECONDS=20
AUTO_SYNC_ENABLED=true
AUTO_SYNC_INTERVAL_MINUTES=60
```


## NLP 2.0 + Alerts Engine
This bundle adds:
- `news_nlp_runs`
- `news_narrative_predictions`
- `alerts`
- `alert_rules`
- NLP enrichment endpoints
- Alerts Engine with:
  - `dominant_narrative_changed`
  - `fragility_high`
  - `forecast_downgrade`
- Frontend alert panel
- Frontend humanized error messages
- `POST /assets/{asset_id}/bootstrap`

### Where to put API keys
Edit:
- `backend/.env`

Use:
```bash
ALPHAVANTAGE_API_KEY=your_alpha_vantage_key
FINNHUB_API_KEY=your_finnhub_key
```
Then restart backend.

### New endpoints
- `POST /assets/{asset_id}/bootstrap`
- `GET /assets/{asset_id}/alerts`
- `GET /alerts`
- `POST /alerts/{alert_id}/mark-seen`
- `POST /alerts/{alert_id}/resolve`
- `GET /alert-rules`
- `POST /alert-rules`
- `POST /assets/{asset_id}/news/enrich`
- `POST /news/enrich/all`
- `GET /news/{news_id}/nlp`


## Added in this package
- Watchlists and personalization
- Aggregate dashboard for multiple assets
- Asset comparison view
- PDF export / daily report
- Email notifications
- WhatsApp notifications (via Twilio WhatsApp API)

## Where to put API keys and notification config
Edit:
- `backend/.env`

Add:
```bash
ALPHAVANTAGE_API_KEY=your_alpha_vantage_key
FINNHUB_API_KEY=your_finnhub_key

SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your_smtp_user
SMTP_PASSWORD=your_smtp_password
SMTP_FROM_EMAIL=alerts@example.com

TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
```

## New backend endpoints
- `GET /watchlists`
- `POST /watchlists`
- `POST /watchlists/{watchlist_id}/assets/{asset_id}`
- `DELETE /watchlists/{watchlist_id}/assets/{asset_id}`
- `GET /preferences`
- `POST /preferences`
- `GET /dashboard/aggregate?asset_ids=aapl,nvda,gold`
- `GET /compare/assets?asset_ids=aapl,nvda,gold`
- `POST /reports/daily/asset/{asset_id}`
- `POST /reports/daily/watchlist/{watchlist_id}`
- `GET /reports/download?file_path=...`
- `GET /notification-channels`
- `POST /notification-channels`
- `GET /notification-events`
- `POST /notifications/email/{channel_id}`
- `POST /notifications/whatsapp/{channel_id}`


## Stable startup package
This version adds:
- safer `start.sh`
- `stop.sh`
- common SQLite/Alembic conflict handling for dev
- `RUNBOOK.md`
- fixed frontend `src/lib/api.ts`
- safer backend startup rebuild


## Audit fix package
This version closes the main runtime stability gaps:
- no `create_all` on startup
- shared UTC datetime helper
- patched timezone-sensitive services
- fixed frontend Hero/App contract
- safer report download path


## ML foundation package
This version prepares the system for future ML while keeping heuristics available at all times.


## Walk-forward + heuristic vs ML package
This version adds:
- walk-forward backtesting
- heuristic vs ML comparison endpoints
- frontend panel for comparing both modes
