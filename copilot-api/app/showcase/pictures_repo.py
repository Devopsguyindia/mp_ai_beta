from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from ..sql_runner import run_select_query
from .presentation import infer_medium_category_hints
from .url_build import get_asset_base_url, is_url_host_allowed, resolve_picture_url

logger = logging.getLogger(__name__)

# company_item_pictures: only idcompany_item_pictures, idcompany, idcompany_item, picture, server_path
_PICTURES_SQL = """
SELECT
  p.idcompany_item_pictures,
  p.idcompany,
  p.idcompany_item,
  p.picture,
  p.server_path,
  i.title AS item_title,
  i.edition_type AS item_edition_type,
  d.EditionName AS edition_label,
  d.ArtName AS artist_display
FROM company_item_pictures p
INNER JOIN company_item i
  ON i.idcompany_item = p.idcompany_item AND i.idcompany = p.idcompany
LEFT JOIN company_item_data d
  ON d.idcompany_item = i.idcompany_item AND d.idcompany = i.idcompany
WHERE p.idcompany = %(idcompany)s
  AND p.idcompany_item = %(idcompany_item)s
ORDER BY p.idcompany_item_pictures ASC
""".strip()


def _sql_debug_bundle(sql: str, params: dict[str, Any]) -> dict[str, Any]:
    """
    Template + binds + a copy-paste friendly line for MySQL clients (debug only).
    Params are only idcompany/idcompany_item ints from this call path.
    """
    effective = sql
    for key, val in params.items():
        ph = f"%({key})s"
        if ph not in effective:
            continue
        if val is None:
            repl = "NULL"
        elif isinstance(val, bool):
            repl = "1" if val else "0"
        elif isinstance(val, int):
            repl = str(val)
        else:
            s = str(val).replace("\\", "\\\\").replace("'", "''")
            repl = f"'{s}'"
        effective = effective.replace(ph, repl)
    return {
        "sql": sql,
        "sql_params": dict(params),
        "sql_effective": effective.strip(),
    }


def showcase_debug_log_enabled() -> bool:
    """When true, fetch logs a JSON line at INFO and may attach debug to responses (see router)."""
    return os.getenv("SHOWCASE_DEBUG_LOG", "0") in {"1", "true", "TRUE", "yes", "YES"}


def _row_ci(row: dict[str, Any], *keys: str) -> Any:
    """mysql.connector DictCursor keys may vary in case; normalize lookup."""
    if not row:
        return None
    lower_map = {str(k).lower(): v for k, v in row.items()}
    for k in keys:
        if k.lower() in lower_map:
            return lower_map[k.lower()]
    return None


def _summarize_row(row: dict[str, Any], *, max_len: int = 80) -> dict[str, Any]:
    """Safe, truncated snapshot for logs / API debug (no secrets)."""
    out: dict[str, Any] = {}
    for k, v in row.items():
        key = str(k)
        if v is None:
            out[key] = None
        elif isinstance(v, (int, float, bool)):
            out[key] = v
        else:
            s = str(v).strip()
            if len(s) > max_len:
                s = s[: max_len - 3] + "..."
            out[key] = s
    return out


@dataclass
class ItemContext:
    item_title: str | None
    artist_display: str | None
    edition_label: str | None
    item_edition_type: int | None
    category_label: str | None
    medium_label: str | None


def fetch_item_pictures(
    *,
    idcompany: int,
    idcompany_item: int,
    max_rows: int = 50,
    timeout_ms: int = 8000,
    asset_allowlist: str | None = None,
    request_id: str | None = None,
    include_debug_detail: bool = False,
) -> tuple[str | None, ItemContext, list[dict[str, Any]], dict[str, Any] | None]:
    """
    Returns (error_message, item_context, picture_rows, debug_or_none).

    When SHOWCASE_DEBUG_LOG=1 or include_debug_detail=True, debug dict is populated and also logged at INFO.
    """
    want_debug = showcase_debug_log_enabled() or include_debug_detail
    base = get_asset_base_url()
    allow_configured = bool((asset_allowlist or "").strip())

    def _mk_debug(
        *,
        phase: str,
        sql_row_count: int = 0,
        emitted_count: int = 0,
        skips: dict[str, int] | None = None,
        first_row_keys: list[str] | None = None,
        first_row_sample: dict[str, Any] | None = None,
        first_row_p_idcompany: Any | None = None,
        mysql_error: str | None = None,
        sql_bundle: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        hints: list[str] = []
        if sql_row_count == 0:
            hints.append(
                "sql_row_count=0: no company_item_pictures row matches idcompany + idcompany_item, "
                "or INNER JOIN company_item failed (missing item row for that tenant/item)."
            )
        elif emitted_count == 0 and sql_row_count > 0:
            hints.append(
                "Rows from SQL but none emitted: check NULL/empty picture, URL build, or SHOWCASE_ASSET_HOST_ALLOWLIST."
            )
        if first_row_p_idcompany is not None and int(first_row_p_idcompany) != int(idcompany):
            hints.append(
                f"first_row p.idcompany={first_row_p_idcompany} differs from request idcompany={idcompany} "
                "(unexpected if SQL filter is correct)."
            )
        out_dbg: dict[str, Any] = {
            "request_id": request_id,
            "phase": phase,
            "query": {"idcompany": idcompany, "idcompany_item": idcompany_item},
            "sql_row_count": sql_row_count,
            "emitted_count": emitted_count,
            "skips": skips or {},
            "mp_asset_cdn_base": base,
            "asset_host_allowlist_configured": allow_configured,
            "first_row_keys": first_row_keys,
            "first_row_sample": first_row_sample,
            "first_row_p_idcompany": first_row_p_idcompany,
            "mysql_error": mysql_error,
            "hints": hints,
        }
        if sql_bundle:
            out_dbg.update(sql_bundle)
        return out_dbg

    sql_text = _PICTURES_SQL
    query_params = {"idcompany": idcompany, "idcompany_item": idcompany_item}
    sql_dbg = _sql_debug_bundle(sql_text, query_params) if want_debug else None

    try:
        result = run_select_query(
            sql=sql_text,
            params=query_params,
            max_rows=max_rows,
            timeout_ms=timeout_ms,
        )
    except Exception as e:
        logger.exception("showcase pictures query failed")
        err = str(e)
        dbg = None
        if want_debug:
            dbg = _mk_debug(phase="mysql_error", mysql_error=err[:800], sql_bundle=sql_dbg)
            logger.info("showcase.pictures.debug %s", json.dumps(dbg, default=str))
        return (err, ItemContext(None, None, None, None, None, None), [], dbg)

    item_title: str | None = None
    artist_display: str | None = None
    edition_label: str | None = None
    item_edition_type: int | None = None

    skips: dict[str, int] = {
        "missing_picture": 0,
        "empty_picture": 0,
        "url_invalid_or_blocked": 0,
        "missing_pk": 0,
    }
    out: list[dict[str, Any]] = []

    first_row_keys: list[str] | None = None
    first_row_sample: dict[str, Any] | None = None
    first_p_company: Any | None = None
    if result.rows:
        first_row_keys = list(result.rows[0].keys())
        first_row_sample = _summarize_row(result.rows[0])
        first_p_company = _row_ci(result.rows[0], "idcompany")

    for row in result.rows:
        if item_title is None:
            it = _row_ci(row, "item_title", "title")
            if it:
                item_title = str(it)
        if artist_display is None:
            ad = _row_ci(row, "artist_display", "ArtName")
            if ad:
                artist_display = str(ad)
        if edition_label is None:
            el = _row_ci(row, "edition_label", "EditionName")
            if el:
                edition_label = str(el)
        if item_edition_type is None:
            et = _row_ci(row, "item_edition_type", "edition_type")
            if et is not None:
                try:
                    item_edition_type = int(et)
                except Exception:
                    item_edition_type = None

        sp = _row_ci(row, "server_path")
        pic = _row_ci(row, "picture", "Picture")
        if pic is None:
            skips["missing_picture"] += 1
            continue
        pic_s = str(pic).strip()
        if not pic_s:
            skips["empty_picture"] += 1
            continue
        sp_s = str(sp).strip() if sp is not None and str(sp).strip() else None
        resolved = resolve_picture_url(
            base_url=base,
            server_path=sp_s,
            picture=pic_s,
        )
        if not resolved or not is_url_host_allowed(resolved, allowlist_csv=asset_allowlist):
            skips["url_invalid_or_blocked"] += 1
            logger.warning(
                "showcase skip picture id=%s (invalid or disallowed url) resolved=%r",
                _row_ci(row, "idcompany_item_pictures"),
                resolved[:120] if resolved else "",
            )
            continue

        pk = _row_ci(row, "idcompany_item_pictures")
        iitem = _row_ci(row, "idcompany_item")
        if pk is None or iitem is None:
            skips["missing_pk"] += 1
            continue
        out.append(
            {
                "idcompany_item_pictures": int(pk),
                "idcompany_item": int(iitem),
                "picture": pic_s,
                "server_path": sp_s,
                "resolved_url": resolved,
                "is_primary": 0,
                "rank": 0,
                "seq_no": 0,
                "thumbnail_url": None,
            }
        )

    dbg = None
    if want_debug:
        dbg = _mk_debug(
            phase="ok",
            sql_row_count=len(result.rows),
            emitted_count=len(out),
            skips=skips,
            first_row_keys=first_row_keys,
            first_row_sample=first_row_sample,
            first_row_p_idcompany=first_p_company,
            sql_bundle=sql_dbg,
        )
        logger.info("showcase.pictures.debug %s", json.dumps(dbg, default=str))

    if result.rows and not out:
        logger.warning(
            "showcase pictures: SQL returned %d row(s) but none emitted. idcompany=%s idcompany_item=%s",
            len(result.rows),
            idcompany,
            idcompany_item,
        )

    cat_hint, med_hint = infer_medium_category_hints(item_title=item_title, artist_display=artist_display)
    ctx = ItemContext(
        item_title=item_title,
        artist_display=artist_display,
        edition_label=edition_label,
        item_edition_type=item_edition_type,
        category_label=cat_hint,
        medium_label=med_hint,
    )
    return (None, ctx, out, dbg)
