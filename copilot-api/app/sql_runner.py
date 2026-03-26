from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import mysql.connector


@dataclass(frozen=True)
class QueryResult:
    columns: list[str]
    rows: list[dict[str, Any]]
    # True when the query returned more rows than max_rows (extra rows were drained, not returned).
    truncated: bool = False


def _connect():
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        database=os.getenv("MYSQL_DATABASE"),
        user=os.getenv("MYSQL_USERNAME"),
        password=os.getenv("MYSQL_PASSWORD"),
        autocommit=True,
        connection_timeout=5,
    )


def run_select_query(*, sql: str, params: dict[str, Any], max_rows: int, timeout_ms: int) -> QueryResult:
    """
    Executes a SELECT query using mysql-connector with dict cursor.
    Note: we also enforce max_rows client-side to avoid UI overload.
    """
    conn = _connect()
    try:
        cur = conn.cursor(dictionary=True)
        try:
            # MySQL max execution time (session) — supported in MySQL 5.7+ via optimizer hint,
            # but safest is to use server-side timeouts and client-side connection limits.
            # We still set a statement timeout hint if available.
            hinted_sql = f"/*+ MAX_EXECUTION_TIME({int(timeout_ms)}) */ {sql}"
            cur.execute(hinted_sql, params)

            rows = []
            for i, row in enumerate(cur):
                if i >= max_rows:
                    break
                rows.append(row)
            # Unbuffered cursor: must consume the rest of the result set before close/execute
            # or mysql-connector raises InterfaceError: Unread result found (common for capped
            # "trend over time" queries that return more rows than MYSQL_MAX_ROWS).
            remainder: list[dict[str, Any]] = []
            try:
                remainder = list(cur.fetchall())
            except Exception:
                pass
            truncated = len(remainder) > 0

            columns = list(rows[0].keys()) if rows else []
            return QueryResult(columns=columns, rows=rows, truncated=truncated)
        finally:
            cur.close()
    finally:
        conn.close()

