# Changelog

## 1.0.1 — 2026-07-22

### Dane GPW

- EODHD jako opcjonalne źródło główne z automatycznym mapowaniem `CODE.WAR`,
- Yahoo Finance jako bezpłatny fallback i niezależna kontrola zgodności cen,
- odrzucanie źródła głównego przy systematycznej rozbieżności ponad konfigurowany próg,
- poprawiony ticker Grupy Pracuj: wewnętrzne ID `prc`, ticker `GPP`, Yahoo `GPP.WA`,
- pełny upsert metadanych wbudowanych aktywów przy starcie,
- domyślnie wyłączone fallbacki RapidAPI, aby nie powtarzać błędów 403/429,
- domyślnie wyłączony limitowany fallback newsów Alpha Vantage po pustym RSS,
- maskowanie kluczy API również w historycznych logach synchronizacji.

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
