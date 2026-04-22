#!/bin/bash
# Swap corrupted thesislab.db with the clean export (thesislab.db.new)
# Run this AFTER stopping the backend process.

set -e
cd "$(dirname "$0")"

echo "=== MStock DB Swap ==="
echo "Sprawdzam pliki..."

if [ ! -f thesislab.db.new ]; then
    echo "BŁĄD: thesislab.db.new nie istnieje!"
    exit 1
fi

# Verify integrity of .new
python3 -c "
import sqlite3
conn = sqlite3.connect('thesislab.db.new')
result = conn.execute('PRAGMA integrity_check').fetchone()[0]
tables = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()
print(f'Integrity: {result}')
print(f'Tabele: {len(tables)}')
conn.close()
"

echo ""
echo "Usuwam stare pliki WAL..."
rm -f thesislab.db-shm thesislab.db-wal

echo "Tworzę kopię zapasową aktualnej (uszkodzonej) bazy..."
mv thesislab.db thesislab.db.corrupted_final

echo "Przesuwam czystą bazę na miejsce aktualnej..."
cp thesislab.db.new thesislab.db

echo ""
echo "=== Gotowe! ==="
echo "Teraz uruchom backend ponownie."
echo "Po restarcie uruchom trening ML przez:"
echo "  curl -X POST http://localhost:8000/ml/models/train-all"
echo ""
echo "Pliki:"
ls -lh thesislab.db thesislab.db.new thesislab.db.corrupted_final 2>/dev/null || true
