# ThesisLab Frontend

## Setup
```bash
npm install
cp .env.example .env
npm run dev
```

## Notes
- Frontend runs on `http://127.0.0.1:5173`
- Set backend URL in `.env`:
```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
```


## Obsługa błędów i naprawa aktywa
Frontend ma:
- bardziej czytelne komunikaty błędów przez `humanizeError`
- przycisk **Napraw / bootstrap asset**, który wywołuje:
  - `POST /assets/{asset_id}/bootstrap`
