# MStock Frontend 1.0.0

## Development

```bash
npm install
npm run dev
```

## Production

```bash
npm run build
npm run serve
```

`npm run build` tworzy wersjonowane assety oraz ich warianty Brotli/Gzip. `npm run serve` udostępnia wyłącznie katalog `dist`, ustawia bezpieczne nagłówki i endpoint `/healthz`.

Domyślny adres to `http://0.0.0.0:5173`. Opcjonalne zmienne procesu: `HOST` oraz `PORT`.

API jest automatycznie kierowane na port `8000` bieżącego hosta. `VITE_API_BASE_URL` służy tylko do jawnego nadpisania adresu podczas buildu.
