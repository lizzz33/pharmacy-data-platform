from __future__ import annotations

from collections.abc import Iterable, Sequence
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import execute_values

from .config import Settings


@contextmanager
def transaction(settings: Settings, service: str):
    connection = psycopg2.connect(settings.dsn(service))
    try:
        with connection:
            with connection.cursor() as cursor:
                yield cursor
    finally:
        connection.close()


def insert_rows(cursor, sql: str, rows: Iterable[Sequence[object]], page_size: int = 2_000) -> int:
    materialized = list(rows)
    if not materialized:
        return 0
    execute_values(cursor, sql, materialized, page_size=page_size)
    return len(materialized)


def ids_by_name(cursor, table: str, name_column: str) -> dict[str, int]:
    cursor.execute(f"SELECT id, {name_column} FROM {table}")
    return {name: row_id for row_id, name in cursor.fetchall()}

