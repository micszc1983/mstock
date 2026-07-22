#!/usr/bin/env python3
"""Jednorazowy, transakcyjny transfer danych MStock z SQLite do PostgreSQL.

Przed uruchomieniem tego skryptu docelowa baza musi mieć schemat utworzony przez:

    DATABASE_URL=postgresql+psycopg://... alembic upgrade head

Skrypt nie czyści bazy docelowej. Celowo odmawia pracy, jeśli którakolwiek tabela
aplikacyjna zawiera rekordy. Dzięki temu pomyłka w URL nie nadpisze danych.
"""
from __future__ import annotations

import argparse
import os
from collections.abc import Iterable

from sqlalchemy import create_engine, func, inspect, select, text

from app.db.models import *  # noqa: F401,F403
from app.db.session import Base


def _redact(url: str) -> str:
    if "://" not in url or "@" not in url:
        return url
    scheme, rest = url.split("://", 1)
    credentials, host = rest.rsplit("@", 1)
    user = credentials.split(":", 1)[0]
    return f"{scheme}://{user}:***@{host}"


def _chunks(rows: Iterable, size: int):
    batch = []
    for row in rows:
        batch.append(dict(row._mapping))
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _count(connection, table) -> int:
    return int(connection.scalar(select(func.count()).select_from(table)) or 0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="sqlite:///./thesislab.db")
    parser.add_argument("--target", default=os.getenv("POSTGRES_DATABASE_URL", ""))
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    if not args.source.startswith("sqlite"):
        parser.error("--source musi wskazywać SQLite")
    if not args.target.startswith(("postgresql://", "postgresql+psycopg://")):
        parser.error("--target/POSTGRES_DATABASE_URL musi wskazywać PostgreSQL")
    if args.batch_size < 100:
        parser.error("--batch-size musi być >= 100")

    source_engine = create_engine(args.source)
    target_engine = create_engine(args.target)
    tables = list(Base.metadata.sorted_tables)
    print(f"Źródło: {args.source}")
    print(f"Cel:    {_redact(args.target)}")

    target_tables = set(inspect(target_engine).get_table_names())
    missing = [table.name for table in tables if table.name not in target_tables]
    if missing:
        raise SystemExit(f"Brak tabel docelowych; uruchom Alembic: {missing}")

    with source_engine.connect() as source, target_engine.connect() as target:
        source_counts = {table.name: _count(source, table) for table in tables}
        target_counts = {table.name: _count(target, table) for table in tables}
        occupied = {name: count for name, count in target_counts.items() if count}
        if occupied:
            raise SystemExit(f"Baza docelowa nie jest pusta: {occupied}")
        print(f"Tabele: {len(tables)}, rekordy: {sum(source_counts.values())}")
        if not args.execute:
            print("Dry-run zakończony. Dodaj --execute, aby rozpocząć transfer.")
            return 0

    with source_engine.connect() as source, target_engine.begin() as target:
        for table in tables:
            expected = source_counts[table.name]
            if not expected:
                print(f"{table.name}: 0")
                continue
            result = source.execution_options(stream_results=True).execute(
                select(table).order_by(*table.primary_key.columns)
            )
            copied = 0
            for batch in _chunks(result, args.batch_size):
                target.execute(table.insert(), batch)
                copied += len(batch)
            print(f"{table.name}: {copied}")

        # INSERT z jawnym id nie przesuwa sekwencji PostgreSQL.
        for table in tables:
            integer_pk = [
                column for column in table.primary_key.columns
                if column.autoincrement is True or column.autoincrement == "auto"
            ]
            if len(integer_pk) != 1:
                continue
            column = integer_pk[0]
            if column.type.python_type is not int:
                continue
            target.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{table.name}', '{column.name}'), "
                f"COALESCE(MAX({column.name}), 1), MAX({column.name}) IS NOT NULL) FROM {table.name}"
            ))

    with source_engine.connect() as source, target_engine.connect() as target:
        mismatches = {}
        for table in tables:
            source_count = _count(source, table)
            target_count = _count(target, table)
            if source_count != target_count:
                mismatches[table.name] = (source_count, target_count)
        if mismatches:
            raise SystemExit(f"Niezgodne liczby rekordów: {mismatches}")
    print("Transfer zakończony; liczby rekordów są zgodne.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
