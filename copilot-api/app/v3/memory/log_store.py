from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import mysql.connector


def _memory_file() -> Path:
    configured = os.getenv("V3_MEMORY_LOG_PATH", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3] / "tests" / "output" / "v3_memory_log.jsonl"


def _use_mysql_memory() -> bool:
    return os.getenv("V3_MEMORY_USE_MYSQL", "1").strip() in {"1", "true", "TRUE", "yes", "YES"}


def _memory_table_name() -> str:
    return os.getenv("V3_MEMORY_TABLE_NAME", "ai_v3_memory_events").strip() or "ai_v3_memory_events"


def _connect_mysql():
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        database=os.getenv("MYSQL_DATABASE"),
        user=os.getenv("MYSQL_USERNAME"),
        password=os.getenv("MYSQL_PASSWORD"),
        autocommit=True,
        connection_timeout=5,
    )


def _append_memory_event_mysql(event: dict[str, Any]) -> None:
    table_name = _memory_table_name()
    sql = (
        f"INSERT INTO `{table_name}` "
        "(request_id, idcompany, user_id, copilot, intent, question, sql_text, rows_returned, meta_json) "
        "VALUES (%(request_id)s, %(idcompany)s, %(user_id)s, %(copilot)s, %(intent)s, %(question)s, %(sql_text)s, "
        "%(rows_returned)s, %(meta_json)s) "
        "ON DUPLICATE KEY UPDATE rows_returned = VALUES(rows_returned), meta_json = VALUES(meta_json)"
    )
    payload = {
        "request_id": str(event.get("request_id") or ""),
        "idcompany": int(event.get("idcompany") or 0),
        "user_id": event.get("user_id"),
        "copilot": str(event.get("copilot") or "unknown"),
        "intent": event.get("intent"),
        "question": str(event.get("question") or ""),
        "sql_text": event.get("sql"),
        "rows_returned": int(event.get("rows_returned") or 0),
        "meta_json": json.dumps(
            {
                "ts_utc": event.get("ts_utc"),
                "source": "v3_orchestrator",
            },
            ensure_ascii=True,
        ),
    }
    conn = _connect_mysql()
    try:
        cur = conn.cursor()
        try:
            cur.execute(sql, payload)
        finally:
            cur.close()
    finally:
        conn.close()


def _normalize_event_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        normalized.append(
            {
                "request_id": row.get("request_id"),
                "idcompany": row.get("idcompany"),
                "user_id": row.get("user_id"),
                "copilot": row.get("copilot"),
                "intent": row.get("intent"),
                "question": row.get("question"),
                # Keep `sql` key for compatibility with existing memory agent.
                "sql": row.get("sql_text"),
                "rows_returned": row.get("rows_returned"),
                "created_at": str(row.get("created_at") or ""),
            }
        )
    return normalized


def _get_recent_events_mysql(*, idcompany: int, limit: int = 10, query: str | None = None) -> list[dict[str, Any]]:
    table_name = _memory_table_name()
    recent_sql = (
        f"SELECT request_id, idcompany, user_id, copilot, intent, question, sql_text, rows_returned, created_at "
        f"FROM `{table_name}` "
        "WHERE idcompany = %(idcompany)s "
        "ORDER BY created_at DESC "
        "LIMIT %(limit)s"
    )
    fts_sql = (
        f"SELECT request_id, idcompany, user_id, copilot, intent, question, sql_text, rows_returned, created_at, "
        "MATCH(question, sql_text) AGAINST (%(query)s IN NATURAL LANGUAGE MODE) AS relevance "
        f"FROM `{table_name}` "
        "WHERE idcompany = %(idcompany)s "
        "AND MATCH(question, sql_text) AGAINST (%(query)s IN NATURAL LANGUAGE MODE) > 0 "
        "ORDER BY relevance DESC, created_at DESC "
        "LIMIT %(limit)s"
    )

    safe_limit = int(max(limit, 1))
    safe_query = (query or "").strip()
    conn = _connect_mysql()
    try:
        cur = conn.cursor(dictionary=True)
        try:
            rows: list[dict[str, Any]] = []
            if safe_query:
                try:
                    cur.execute(fts_sql, {"idcompany": int(idcompany), "limit": safe_limit, "query": safe_query})
                    rows = list(cur.fetchall())
                except Exception:
                    # Fall back to recency retrieval if full-text query is unavailable.
                    rows = []

            if not rows:
                cur.execute(recent_sql, {"idcompany": int(idcompany), "limit": safe_limit})
                rows = list(cur.fetchall())
        finally:
            cur.close()
    finally:
        conn.close()

    rows.reverse()
    return _normalize_event_rows(rows)


def _append_memory_event_file(event: dict[str, Any]) -> None:
    path = _memory_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=True) + "\n")


def _get_recent_events_file(*, idcompany: int, limit: int = 10, query: str | None = None) -> list[dict[str, Any]]:
    path = _memory_file()
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    rows: list[dict[str, Any]] = []
    lowered_query_tokens = [t for t in (query or "").lower().split() if len(t) > 1]
    for line in reversed(lines):
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if int(payload.get("idcompany", -1)) != int(idcompany):
            continue
        if lowered_query_tokens:
            hay = f"{payload.get('question', '')} {payload.get('sql', '')}".lower()
            if not any(token in hay for token in lowered_query_tokens):
                continue
        rows.append(payload)
        if len(rows) >= limit:
            break
    rows.reverse()
    return rows


def append_memory_event(event: dict[str, Any]) -> None:
    if _use_mysql_memory():
        try:
            _append_memory_event_mysql(event)
            return
        except Exception:
            # Fallback to file log to keep V3 requests resilient.
            pass
    _append_memory_event_file(event)


def get_recent_events(*, idcompany: int, limit: int = 10, query: str | None = None) -> list[dict[str, Any]]:
    if _use_mysql_memory():
        try:
            return _get_recent_events_mysql(idcompany=idcompany, limit=limit, query=query)
        except Exception:
            # Fallback to file log if MySQL memory retrieval fails.
            pass
    return _get_recent_events_file(idcompany=idcompany, limit=limit, query=query)
