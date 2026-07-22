# Changelog

## 1.0.0 — 2026-07-22

Pierwsze stabilne wydanie MStock do prywatnego użycia w sieci LAN.

### Najważniejsze funkcje

- walidacja jakości OHLCV i kontrola danych point-in-time,
- backtest z kapitałem, prowizją, poślizgiem i metrykami ryzyka,
- paper trading z rachunkiem, zleceniami i dziennikiem,
- rekomendacje kalibrowane osobno dla rynku i reżimu, z kosztami oraz decyzją „brak transakcji”,
- purged temporal CV, CPCV/PBO, RF/XGBoost challenger, triple-barrier i meta-labeling,
- automatyczna aktywacja, shadow mode, monitoring driftu i degradacji modeli ML,
- PostgreSQL z migracjami Alembic oraz retencją 15 przebiegów modeli,
- dane fundamentalne, news, earnings, insider, short interest, anomaly/PEAD i intraday,
- responsywny frontend z trwałym wyborem aktywa.

### Stabilność wydania

- frontend serwowany z produkcyjnego `dist`, bez cache Vite dev,
- prekompresja Brotli/Gzip i długie cache dla wersjonowanych assetów,
- ciężkie zakładki ładowane dopiero po wybraniu,
- jedno zbiorcze żądanie sygnałów intraday zamiast żądania dla każdego aktywa,
- backup i kontrolowany restore dostosowane do PostgreSQL.
