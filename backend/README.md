# ThesisLab Modular

## Start
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export ALPHAVANTAGE_API_KEY="your_key"
export FINNHUB_API_KEY="your_key"
uvicorn main:app --reload
```

## Tests
```bash
pytest
```

## Alembic
Initialize database with migrations:
```bash
alembic upgrade head
```

Create a new migration after model changes:
```bash
alembic revision --autogenerate -m "describe change"
```

## Main endpoints
- `GET /dashboard`
- `GET /assets`
- `GET /assets/{asset_id}/thesis`
- `GET /assets/{asset_id}/break-monitor`
- `GET /assets/{asset_id}/narratives`
- `POST /sync/prices/{asset_id}`
- `POST /sync/news/{asset_id}`
- `POST /sync/all`
- `GET /sync/logs`
- `GET /scheduler/status`


## Test coverage added
- `tests/test_providers.py` — mock HTTP provider responses
- `tests/test_sync_integration.py` — sync service integration with SQLite persistence


- `tests/test_sync_api_integration.py` — end-to-end HTTP tests for `/sync/...` endpoints with mocked providers


## Features and forecasts
- `GET /assets/{asset_id}/features/latest`
- `GET /assets/{asset_id}/features/history`
- `GET /assets/{asset_id}/forecast`
- `GET /assets/{asset_id}/forecast/history`
- `POST /features/rebuild`


## Thesis history
Saved historical theses are available via:
- `GET /assets/{asset_id}/theses/latest`
- `GET /assets/{asset_id}/theses/history`

Historical theses are persisted automatically during feature/forecast rebuilds.


## Thesis outcomes
Evaluate historical thesis performance via:
- `POST /assets/{asset_id}/thesis-outcomes/rebuild`
- `GET /assets/{asset_id}/thesis-outcomes/history`
- `GET /assets/{asset_id}/theses/{thesis_id}/outcomes`

Outcomes are computed for 1d / 5d / 20d horizons from stored theses and historical prices.


## Quality metrics
Aggregate quality metrics are available via:
- `GET /assets/{asset_id}/quality/thesis/summary`
- `GET /assets/{asset_id}/quality/thesis/by-horizon`
- `GET /assets/{asset_id}/quality/forecast/summary`

These endpoints summarize thesis outcomes and stored forecasts at the asset level.


## Frontend integration
A frontend component aligned 1:1 with the backend is included in:
- `frontend/components/ThesisLabDashboard.tsx`

Required backend endpoints now include:
- `GET /assets/{asset_id}/forecast/history`


## API keys
Klucze podajesz w pliku:
- `backend/.env`

Uzupełnij:
```bash
ALPHAVANTAGE_API_KEY=twoj_klucz_alpha_vantage
FINNHUB_API_KEY=twoj_klucz_finnhub
```

Następnie zrestartuj backend:
```bash
uvicorn main:app --reload
```

Możesz też ustawić je tymczasowo w terminalu:
```bash
export ALPHAVANTAGE_API_KEY="twoj_klucz_alpha_vantage"
export FINNHUB_API_KEY="twoj_klucz_finnhub"
```
