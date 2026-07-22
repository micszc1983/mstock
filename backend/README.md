# MStock Backend 1.0.0

FastAPI, PostgreSQL, SQLAlchemy, Alembic, scheduler analiz oraz warstwa ML.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 -m alembic upgrade head
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

## Tests

```bash
.venv/bin/python3 -m pytest -q
```

## Production

Backend jest uruchamiany przez `mstock-backend.service`. Jednostka wykonuje `alembic upgrade head` przed startem i uruchamia pojedynczy proces uvicorn na porcie `8000`.

```bash
sudo systemctl restart mstock-backend
curl -fsS http://127.0.0.1:8000/health
```

Konfiguracja i sekrety znajdują się w `backend/.env`. Produkcyjna baza powinna być wskazana przez `DATABASE_URL=postgresql+psycopg://...`.

Pełna dokumentacja endpointów: `http://127.0.0.1:8000/docs`. Procedury backupu i odtwarzania opisuje główny `RUNBOOK.md`.
