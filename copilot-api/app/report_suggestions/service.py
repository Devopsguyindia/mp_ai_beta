from __future__ import annotations

import json
import os
from typing import Any

import mysql.connector

from ..sql_runner import run_select_query
from .models import (
    PredictHintItem,
    RecentRunItem,
    ReportSuggestionsResponse,
    SmartDefaultItem,
    TopReportItem,
)

_WEEKDAY_LABELS = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")


def _maybe_truncate_filter_data(
    raw: str | None, *, truncate: bool, max_chars: int
) -> tuple[str | None, bool]:
    if raw is None:
        return None, False
    if not truncate or len(raw) <= max_chars:
        return raw, False
    return raw[: max_chars - 3] + "...", True


def _report_name_from_join_row(row: dict[str, Any]) -> tuple[str | None, str | None]:
    """Derive display name and source from LEFT JOIN columns."""
    gname = row.get("global_name")
    cname = row.get("gallery_name")
    if cname and str(cname).strip():
        if gname and str(gname).strip() and str(cname).strip() != str(gname).strip():
            return str(cname).strip(), "gallery"
        return str(cname).strip(), "gallery"
    if gname and str(gname).strip():
        return str(gname).strip(), "global"
    return None, "unknown"


def _fetch_top_reports(
    *,
    idcompany: int,
    user_id: int | None,
    top_n: int,
    timeout_ms: int,
) -> tuple[list[TopReportItem], str | None]:
    user_clause = ""
    params: dict[str, Any] = {"idcompany": idcompany, "top_n": top_n}
    if user_id is not None:
        user_clause = " AND ru.user_id = %(user_id)s"
        params["user_id"] = user_id

    sql = f"""
    SELECT
      ru.report_id AS report_id,
      CAST(SUM(ru.usage_count) AS SIGNED) AS total_usage,
      MAX(rt.name) AS global_name,
      MAX(crt.name) AS gallery_name
    FROM report_usage ru
    LEFT JOIN tb_report_template rt ON rt.idreport_template = ru.report_id
    LEFT JOIN tb_company_report_templates crt
      ON crt.idcompany_report_templates = ru.report_id
     AND crt.idcompany = ru.idcompany
    WHERE ru.idcompany = %(idcompany)s
    {user_clause}
    GROUP BY ru.report_id
    ORDER BY total_usage DESC
    LIMIT %(top_n)s
    """.strip()
    try:
        result = run_select_query(sql=sql, params=params, max_rows=top_n + 5, timeout_ms=timeout_ms)
    except mysql.connector.Error as e:
        return [], str(e)

    out: list[TopReportItem] = []
    for row in result.rows:
        rid = row.get("report_id")
        if rid is None:
            continue
        name, src = _report_name_from_join_row(row)
        tu = row.get("total_usage")
        try:
            total_usage = int(tu) if tu is not None else 0
        except (TypeError, ValueError):
            total_usage = 0
        out.append(
            TopReportItem(
                report_id=int(rid),
                total_usage=total_usage,
                report_name=name,
                name_source=src,
            )
        )
    return out, None


def _fetch_recent_runs(
    *,
    idcompany: int,
    user_id: int | None,
    recent_n: int,
    truncate: bool,
    filter_max: int,
    timeout_ms: int,
) -> tuple[list[RecentRunItem], str | None]:
    user_clause = ""
    params: dict[str, Any] = {"idcompany": idcompany, "recent_n": recent_n}
    if user_id is not None:
        user_clause = " AND ru.user_id = %(user_id)s"
        params["user_id"] = user_id

    sql = f"""
    SELECT
      ru.report_id,
      ru.user_id,
      ru.usage_count,
      ru.last_used,
      ru.filter_hash,
      ru.filter_data,
      rt.name AS global_name,
      crt.name AS gallery_name
    FROM report_usage ru
    LEFT JOIN tb_report_template rt ON rt.idreport_template = ru.report_id
    LEFT JOIN tb_company_report_templates crt
      ON crt.idcompany_report_templates = ru.report_id
     AND crt.idcompany = ru.idcompany
    WHERE ru.idcompany = %(idcompany)s
    {user_clause}
    ORDER BY COALESCE(ru.last_used, ru.updated_at, ru.created_at) DESC
    LIMIT %(recent_n)s
    """.strip()
    try:
        result = run_select_query(sql=sql, params=params, max_rows=recent_n + 5, timeout_ms=timeout_ms)
    except mysql.connector.Error as e:
        return [], str(e)

    out: list[RecentRunItem] = []
    for row in result.rows:
        fd_raw = row.get("filter_data")
        fd_str = fd_raw if isinstance(fd_raw, str) else (json.dumps(fd_raw) if fd_raw is not None else None)
        fd_out, fd_trunc = _maybe_truncate_filter_data(
            fd_str, truncate=truncate, max_chars=filter_max
        )
        name, _ = _report_name_from_join_row(row)
        fh = row.get("filter_hash")
        out.append(
            RecentRunItem(
                report_id=int(row["report_id"]),
                user_id=int(row["user_id"]),
                usage_count=int(row.get("usage_count") or 0),
                last_used=row.get("last_used"),
                filter_hash=str(fh) if fh is not None else "",
                filter_data=fd_out,
                filter_data_truncated=fd_trunc,
                report_name=name,
            )
        )
    return out, None


def _fetch_smart_defaults(
    *,
    idcompany: int,
    user_id: int | None,
    limit_reports: int,
    truncate: bool,
    filter_max: int,
    timeout_ms: int,
    restrict_report_ids: list[int] | None,
) -> tuple[list[SmartDefaultItem], str | None]:
    user_clause = ""
    params: dict[str, Any] = {"idcompany": idcompany}
    if user_id is not None:
        user_clause = " AND user_id = %(user_id)s"
        params["user_id"] = user_id

    restrict_clause = ""
    if restrict_report_ids:
        safe_ids = ",".join(str(int(x)) for x in restrict_report_ids[:50])
        restrict_clause = f" AND report_id IN ({safe_ids})"

    sql = f"""
    SELECT
      report_id,
      filter_hash,
      filter_data,
      CAST(SUM(usage_count) AS SIGNED) AS usage_sum
    FROM report_usage
    WHERE idcompany = %(idcompany)s
    {user_clause}
    {restrict_clause}
    GROUP BY report_id, filter_hash, filter_data
    ORDER BY report_id ASC, usage_sum DESC
    """.strip()
    try:
        result = run_select_query(
            sql=sql, params=params, max_rows=2000, timeout_ms=timeout_ms
        )
    except mysql.connector.Error as e:
        return [], str(e)

    best_by_report: dict[int, dict[str, Any]] = {}
    for row in result.rows:
        rid = row.get("report_id")
        if rid is None:
            continue
        rid_i = int(rid)
        us = row.get("usage_sum")
        try:
            usage_sum = int(us) if us is not None else 0
        except (TypeError, ValueError):
            usage_sum = 0
        prev = best_by_report.get(rid_i)
        prev_u = int(prev.get("usage_sum") or 0) if prev else -1
        if prev is None or usage_sum > prev_u:
            best_by_report[rid_i] = row

    if not best_by_report:
        return [], None

    if restrict_report_ids:
        ordered_ids = [rid for rid in restrict_report_ids if rid in best_by_report][
            :limit_reports
        ]
    else:
        ordered_ids = sorted(
            best_by_report.keys(),
            key=lambda r: -int(best_by_report[r].get("usage_sum") or 0),
        )[:limit_reports]

    picked = {rid: best_by_report[rid] for rid in ordered_ids}
    report_ids = list(ordered_ids)
    try:
        names_by_id = _fetch_report_names_bulk(idcompany, report_ids, timeout_ms)
    except mysql.connector.Error:
        names_by_id = {}

    out: list[SmartDefaultItem] = []
    for rid in sorted(picked.keys()):
        row = picked[rid]
        fd_raw = row.get("filter_data")
        fd_str = fd_raw if isinstance(fd_raw, str) else (json.dumps(fd_raw) if fd_raw is not None else None)
        fd_out, fd_trunc = _maybe_truncate_filter_data(
            fd_str, truncate=truncate, max_chars=filter_max
        )
        gname, cname = names_by_id.get(rid, (None, None))
        name_row = {"global_name": gname, "gallery_name": cname}
        name, _ = _report_name_from_join_row(name_row)
        fh = row.get("filter_hash")
        us = row.get("usage_sum")
        try:
            usage_sum = int(us) if us is not None else 0
        except (TypeError, ValueError):
            usage_sum = 0
        out.append(
            SmartDefaultItem(
                report_id=rid,
                filter_hash=str(fh) if fh is not None else "",
                usage_sum=usage_sum,
                filter_data=fd_out,
                filter_data_truncated=fd_trunc,
                report_name=name,
            )
        )
    return out, None


def _fetch_report_names_bulk(
    idcompany: int, report_ids: list[int], _timeout_ms: int = 0
) -> dict[int, tuple[str | None, str | None]]:
    """Map report_id -> (global_name, gallery_name)."""
    if not report_ids:
        return {}
    import mysql.connector as mc

    conn = mc.connect(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        database=os.getenv("MYSQL_DATABASE"),
        user=os.getenv("MYSQL_USERNAME"),
        password=os.getenv("MYSQL_PASSWORD"),
        autocommit=True,
        connection_timeout=5,
    )
    global_names: dict[int, str | None] = {}
    gallery_names: dict[int, str | None] = {}
    try:
        cur = conn.cursor(dictionary=True)
        try:
            placeholders = ", ".join(["%s"] * len(report_ids))
            sql_rt = f"""
            SELECT idreport_template AS rid, name AS n FROM tb_report_template
            WHERE idreport_template IN ({placeholders})
            """
            cur.execute(sql_rt, tuple(report_ids))
            global_names = {int(r["rid"]): r.get("n") for r in cur.fetchall()}

            sql_crt = f"""
            SELECT idcompany_report_templates AS rid, name AS n FROM tb_company_report_templates
            WHERE idcompany = %s AND idcompany_report_templates IN ({placeholders})
            """
            cur.execute(sql_crt, (idcompany, *tuple(report_ids)))
            gallery_names = {int(r["rid"]): r.get("n") for r in cur.fetchall()}
        finally:
            cur.close()
    finally:
        conn.close()

    out: dict[int, tuple[str | None, str | None]] = {}
    for rid in report_ids:
        out[rid] = (global_names.get(rid), gallery_names.get(rid))
    return out


def _fetch_predict_hints(
    *,
    idcompany: int,
    user_id: int | None,
    timeout_ms: int,
) -> tuple[list[PredictHintItem], str | None]:
    """Lightweight weekday clustering for the gallery's most-used report (Phase 3 lite)."""
    user_clause = ""
    params: dict[str, Any] = {"idcompany": idcompany}
    if user_id is not None:
        user_clause = " AND user_id = %(user_id)s"
        params["user_id"] = user_id

    top_sql = f"""
    SELECT report_id, CAST(SUM(usage_count) AS SIGNED) AS total_usage
    FROM report_usage
    WHERE idcompany = %(idcompany)s
    {user_clause}
    GROUP BY report_id
    ORDER BY total_usage DESC
    LIMIT 1
    """.strip()
    try:
        top = run_select_query(sql=top_sql, params=params, max_rows=2, timeout_ms=timeout_ms)
    except mysql.connector.Error as e:
        return [], str(e)

    if not top.rows:
        return [], None

    top_rid = int(top.rows[0]["report_id"])
    params2 = {"idcompany": idcompany, "report_id": top_rid}
    u2 = ""
    if user_id is not None:
        u2 = " AND user_id = %(user_id)s"
        params2["user_id"] = user_id

    dow_sql = f"""
    SELECT
      DAYOFWEEK(COALESCE(last_used, updated_at)) AS dow,
      COUNT(*) AS run_count
    FROM report_usage
    WHERE idcompany = %(idcompany)s AND report_id = %(report_id)s
    {u2}
      AND COALESCE(last_used, updated_at) IS NOT NULL
    GROUP BY DAYOFWEEK(COALESCE(last_used, updated_at))
    HAVING run_count >= 2
    ORDER BY run_count DESC
    LIMIT 3
    """.strip()
    try:
        dow = run_select_query(sql=dow_sql, params=params2, max_rows=5, timeout_ms=timeout_ms)
    except mysql.connector.Error as e:
        return [], str(e)

    names = _fetch_report_names_bulk(idcompany, [top_rid], timeout_ms)
    g, c = names.get(top_rid, (None, None))
    rname, _ = _report_name_from_join_row({"global_name": g, "gallery_name": c})

    hints: list[PredictHintItem] = []
    for row in dow.rows:
        dow_i = int(row["dow"])
        idx = (dow_i - 1) % 7
        label = _WEEKDAY_LABELS[idx] if 0 <= idx < 7 else str(dow_i)
        hints.append(
            PredictHintItem(
                report_id=top_rid,
                report_name=rname,
                weekday=dow_i,
                weekday_label=label,
                run_count=int(row.get("run_count") or 0),
            )
        )
    return hints, None


def build_report_suggestions(
    *,
    idcompany: int,
    user_id: int | None,
    top_n: int,
    recent_n: int,
    smart_default_limit: int,
    truncate_filter_data: bool,
    filter_data_max_chars: int,
) -> ReportSuggestionsResponse:
    warnings: list[str] = []
    timeout_ms = int(os.getenv("MYSQL_QUERY_TIMEOUT_MS", "8000"))

    top, err_top = _fetch_top_reports(
        idcompany=idcompany, user_id=user_id, top_n=top_n, timeout_ms=timeout_ms
    )
    if err_top:
        warnings.append(f"top_reports: {err_top}")

    restrict_ids = [t.report_id for t in top] if top else None

    recent, err_recent = _fetch_recent_runs(
        idcompany=idcompany,
        user_id=user_id,
        recent_n=recent_n,
        truncate=truncate_filter_data,
        filter_max=filter_data_max_chars,
        timeout_ms=timeout_ms,
    )
    if err_recent:
        warnings.append(f"recent_runs: {err_recent}")

    smart, err_smart = _fetch_smart_defaults(
        idcompany=idcompany,
        user_id=user_id,
        limit_reports=smart_default_limit,
        truncate=truncate_filter_data,
        filter_max=filter_data_max_chars,
        timeout_ms=timeout_ms,
        restrict_report_ids=restrict_ids,
    )
    if err_smart:
        warnings.append(f"smart_defaults: {err_smart}")

    hints, err_hints = _fetch_predict_hints(
        idcompany=idcompany, user_id=user_id, timeout_ms=timeout_ms
    )
    if err_hints:
        warnings.append(f"predict_hints: {err_hints}")

    return ReportSuggestionsResponse(
        ok=len(warnings) == 0,
        idcompany=idcompany,
        scoped_to_user_id=user_id,
        top_reports=top,
        recent_runs=recent,
        smart_defaults=smart,
        predict_hints=hints,
        warnings=warnings,
    )
