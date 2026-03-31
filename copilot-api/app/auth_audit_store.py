"""
Best-effort MySQL inserts for Copilot login / logout audit (ai_v3_copilot_auth_audit).
Never raises to callers; failures are swallowed so auth responses stay unchanged.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Literal

import mysql.connector

logger = logging.getLogger(__name__)

AuthEventType = Literal["login_success", "login_failure", "logout"]


def _audit_enabled() -> bool:
    return os.getenv("COPILOT_AUTH_AUDIT_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}


def _use_mysql() -> bool:
    return os.getenv("COPILOT_AUTH_AUDIT_USE_MYSQL", "1").strip().lower() in {"1", "true", "yes"}


def _table_name() -> str:
    return os.getenv("COPILOT_AUTH_AUDIT_TABLE", "ai_v3_copilot_auth_audit").strip() or "ai_v3_copilot_auth_audit"


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


def append_auth_audit_event(
    *,
    event_type: AuthEventType,
    client_ip: str,
    user_agent: str,
    auth_session_id: str | None = None,
    idcompany: int | None = None,
    txt_company: str | None = None,
    userid: str | None = None,
    username: str | None = None,
    failure_code: str | None = None,
    failure_message: str | None = None,
    role_id: str | None = None,
    meta_json: dict[str, Any] | None = None,
) -> None:
    if not _audit_enabled() or not _use_mysql():
        return
    occurred = datetime.now(timezone.utc)
    meta_str: str | None = None
    if meta_json is not None:
        try:
            meta_str = json.dumps(meta_json, ensure_ascii=True)
        except (TypeError, ValueError):
            meta_str = None

    def _s(val: str | None, max_len: int) -> str | None:
        if val is None:
            return None
        s = str(val).strip()
        if not s:
            return None
        return s[:max_len]

    payload = {
        "event_type": event_type[:32],
        "occurred_at_utc": occurred,
        "auth_session_id": _s(auth_session_id, 36),
        "idcompany": idcompany,
        "txt_company": _s(txt_company, 200),
        "userid": _s(userid, 64),
        "username": _s(username, 200),
        "failure_code": _s(failure_code, 64),
        "failure_message": _s(failure_message, 512),
        "client_ip": _s(client_ip, 45),
        "user_agent": _s(user_agent, 512),
        "role_id": _s(role_id, 64),
        "meta_json": meta_str,
    }

    table = _table_name()
    sql = (
        f"INSERT INTO `{table}` "
        "(event_type, occurred_at_utc, auth_session_id, idcompany, txt_company, userid, username, "
        "failure_code, failure_message, client_ip, user_agent, role_id, meta_json) "
        "VALUES (%(event_type)s, %(occurred_at_utc)s, %(auth_session_id)s, %(idcompany)s, %(txt_company)s, "
        "%(userid)s, %(username)s, %(failure_code)s, %(failure_message)s, %(client_ip)s, %(user_agent)s, "
        "%(role_id)s, %(meta_json)s)"
    )

    try:
        conn = _connect_mysql()
        try:
            cur = conn.cursor()
            try:
                cur.execute(sql, payload)
            finally:
                cur.close()
        finally:
            conn.close()
    except Exception as e:
        logger.warning("auth audit insert failed: %s", e, exc_info=False)


def client_ip_from_request_headers(forwarded_for: str | None, direct_host: str | None) -> str:
    if forwarded_for:
        first = forwarded_for.split(",")[0].strip()
        if first:
            return first[:45]
    if direct_host:
        return direct_host[:45]
    return ""
