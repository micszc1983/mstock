# MStock 1.0.0 — runbook

## Wdrożenie

```bash
cd /home/tt38dn/MStock
sudo ./install-service.sh
```

Frontend musi działać jako `production static server`, a nie `Vite dev server`:

```bash
systemctl status mstock-frontend --no-pager
curl -fsS http://127.0.0.1:5173/healthz
```

Oczekiwany health:

```json
{"status":"ok","version":"1.0.0"}
```

## Codzienna kontrola

```bash
systemctl is-active mstock-backend mstock-frontend
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:5173/healthz
journalctl -u mstock-backend -u mstock-frontend --since today --no-pager
```

Sprawdź w UI jakość danych, scheduler, status providerów i stany modeli `live/shadow/degraded`.

## Restart

Jednostki są systemowe — nie używaj `systemctl --user`:

```bash
sudo systemctl restart mstock-backend mstock-frontend
```

## Smoke test po wdrożeniu

```bash
curl -fsS http://127.0.0.1:5173/healthz
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/assets >/dev/null
curl -fsS 'http://127.0.0.1:8000/assets/intraday/signals-summary?resolution=15' >/dev/null
```

Następnie otwórz aplikację w świeżej karcie telefonu, wybierz inne aktywo, zamknij kartę i sprawdź przywrócenie wyboru.

## Backup PostgreSQL

```bash
./backup/mstock-backup.sh
tail -n 50 backup/backup.log
```

Backup jest poprawny tylko wtedy, gdy `pg_restore --list` przejdzie pomyślnie i na NAS istnieje zgodna suma `mstock.dump.sha256`.

## Restore PostgreSQL

Restore jest operacją destrukcyjną i wymaga jawnego potwierdzenia. Skrypt przed zmianą tworzy dump bezpieczeństwa bieżącej bazy.

```bash
sudo systemctl stop mstock-backend
./backup/restore-postgres.sh /ścieżka/mstock.dump --confirm
sudo systemctl start mstock-backend
curl -fsS http://127.0.0.1:8000/health
```

## Diagnostyka

```bash
systemctl status mstock-backend mstock-frontend --no-pager -l
journalctl -u mstock-backend -n 200 --no-pager
journalctl -u mstock-frontend -n 100 --no-pager
ss -ltnp | grep -E ':8000|:5173'
```

### Biała strona

W wydaniu 1.0 frontend nie korzysta z cache zależności Vite dev. Sprawdź:

```bash
curl -I http://127.0.0.1:5173/
curl -fsS http://127.0.0.1:5173/healthz
```

HTML ma `Cache-Control: no-store`, natomiast pliki z hashem w `/assets/` mają cache `immutable`.

### ML nie jest live

To nie jest awaria. Automat dopuszcza model dopiero po spełnieniu progów jakości, liczebności, kalibracji, kosztów i monitoringu. Do tego czasu system używa heurystyki, a model pracuje w `shadow`.

## Powrót do poprzedniego wydania

1. zatrzymaj usługi,
2. przywróć poprzedni zatwierdzony commit/tag,
3. odtwórz zgodny dump, jeśli wydanie zmieniło schemat,
4. uruchom `sudo ./install-service.sh`,
5. wykonaj smoke test.
