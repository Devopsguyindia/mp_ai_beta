from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..sql_runner import run_select_query
from .presentation import infer_medium_category_hints
from .url_build import get_asset_base_url, is_url_host_allowed, resolve_picture_url

logger = logging.getLogger(__name__)

_PICTURES_SQL = """
SELECT
  p.idcompany_item_pictures,
  p.idcompany_item,
  p.picture,
  p.server_path,
  COALESCE(p.is_primary, 0) AS is_primary,
  COALESCE(p.`rank`, 0) AS pic_rank,
  COALESCE(p.seq_no, 0) AS seq_no,
  p.thumbnail_url,
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
  AND COALESCE(p.is_deleted, 0) = 0
  AND COALESCE(i.is_delete, 0) = 0
ORDER BY is_primary DESC, pic_rank ASC, seq_no ASC, p.idcompany_item_pictures ASC
"""


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
) -> tuple[str | None, ItemContext, list[dict[str, Any]]]:
    """
    Returns (error_message, item_context, picture_rows).

    picture_rows match ItemPictureRow (no duplicate item fields per row).
    category/medium: reserved for ERP columns; soft hints fill medium_label when null.
    """
    base = get_asset_base_url()
    try:
        result = run_select_query(
            sql=_PICTURES_SQL.strip(),
            params={"idcompany": idcompany, "idcompany_item": idcompany_item},
            max_rows=max_rows,
            timeout_ms=timeout_ms,
        )
    except Exception as e:
        logger.exception("showcase pictures query failed")
        return (str(e), ItemContext(None, None, None, None, None, None), [])

    item_title: str | None = None
    artist_display: str | None = None
    edition_label: str | None = None
    item_edition_type: int | None = None

    out: list[dict[str, Any]] = []
    for row in result.rows:
        if item_title is None and row.get("item_title"):
            item_title = str(row["item_title"])
        if artist_display is None and row.get("artist_display"):
            artist_display = str(row["artist_display"])
        if edition_label is None and row.get("edition_label"):
            edition_label = str(row["edition_label"])
        if item_edition_type is None and row.get("item_edition_type") is not None:
            try:
                item_edition_type = int(row["item_edition_type"])
            except Exception:
                item_edition_type = None

        sp = row.get("server_path")
        pic = row.get("picture")
        if pic is None:
            continue
        resolved = resolve_picture_url(
            base_url=base,
            server_path=str(sp) if sp is not None else None,
            picture=str(pic),
        )
        if not resolved or not is_url_host_allowed(resolved, allowlist_csv=asset_allowlist):
            logger.warning(
                "showcase skip picture id=%s (invalid or disallowed url)",
                row.get("idcompany_item_pictures"),
            )
            continue
        thumb = row.get("thumbnail_url")
        thumb_s = str(thumb).strip() if thumb else None
        if thumb_s and not is_url_host_allowed(thumb_s, allowlist_csv=asset_allowlist):
            thumb_s = None

        out.append(
            {
                "idcompany_item_pictures": int(row["idcompany_item_pictures"]),
                "idcompany_item": int(row["idcompany_item"]),
                "picture": str(pic),
                "server_path": str(sp) if sp is not None else None,
                "resolved_url": resolved,
                "is_primary": int(row.get("is_primary") or 0),
                "rank": int(row.get("pic_rank") or 0),
                "seq_no": int(row.get("seq_no") or 0),
                "thumbnail_url": thumb_s,
            }
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
    return (None, ctx, out)
