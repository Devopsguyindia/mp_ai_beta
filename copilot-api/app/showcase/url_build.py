from __future__ import annotations

import os
import re
from urllib.parse import quote, unquote, urlparse


def _strip_trailing_slash(s: str) -> str:
    return s.rstrip("/")


def _ensure_leading_slash(path: str) -> str:
    if not path:
        return ""
    return path if path.startswith("/") else f"/{path}"


def _quote_path_segments(rel: str) -> str:
    """Percent-encode each path segment (handles spaces in ERP filenames); normalizes prior % escapes."""
    rel = (rel or "").strip().lstrip("/")
    if not rel:
        return ""
    parts = [p for p in rel.split("/") if p != ""]
    return "/".join(quote(unquote(p), safe="") for p in parts)


def _hostname_of_base(base_url: str) -> str:
    try:
        return (urlparse(base_url).hostname or "").strip().lower()
    except Exception:
        return ""


def _strip_redundant_host_path_segments(rel: str, host: str) -> str:
    """
    ERP sometimes stores the CDN hostname as the first path segment (e.g. picture =
    'masterpiece.s3.amazonaws.com/uuid.JPG') while MP_ASSET_CDN_BASE already includes that host.
    Strip one or more leading segments that duplicate the base hostname (case-insensitive).
    """
    if not host or not rel:
        return rel.strip().lstrip("/")
    parts = [p for p in rel.strip().lstrip("/").split("/") if p != ""]
    hl = host.lower()
    while parts and parts[0].lower() == hl:
        parts = parts[1:]
    return "/".join(parts)


def resolve_artwork_fetch_url_candidates(*, base_url: str, server_path: str | None, picture: str) -> list[str]:
    """
    Ordered URLs to try when downloading artwork bytes (compositor / batch). Public
    ``resolved_url`` from resolve_picture_url stays canonical (no repeated host segment).

    When server_path is only the CDN hostname, many buckets store the object under that
    prefix — try that URL first, then the root-style URL.
    """
    primary = resolve_picture_url(base_url=base_url, server_path=server_path, picture=picture)
    root = resolve_picture_url(base_url=base_url, server_path=None, picture=picture)

    base = _strip_trailing_slash((base_url or "").strip())
    base_host = _hostname_of_base(base)
    sp = (server_path or "").strip()
    pic_raw = (picture or "").strip()

    prefixed: str | None = None
    if (
        base_host
        and sp
        and sp.lower() == base_host.lower()
        and pic_raw
        and not pic_raw.lower().startswith(("http://", "https://"))
    ):
        pic = _strip_redundant_host_path_segments(pic_raw, base_host)
        pic_enc = _quote_path_segments(pic)
        if pic_enc:
            prefixed = f"{base}/{_quote_path_segments(sp)}/{pic_enc}"

    out: list[str] = []
    if prefixed:
        out.append(prefixed)
    for u in (primary, root):
        if u and u not in out:
            out.append(u)
    return out


def resolve_picture_url(*, base_url: str, server_path: str | None, picture: str) -> str:
    """
    Build final_url = base + server_path + picture with slash normalization.
    """
    base = _strip_trailing_slash((base_url or "").strip())
    pic_raw = (picture or "").strip()
    if not base or not pic_raw:
        return ""

    if pic_raw.lower().startswith(("http://", "https://")):
        return pic_raw

    base_host = _hostname_of_base(base)
    pic = _strip_redundant_host_path_segments(pic_raw, base_host)
    if not pic:
        return ""

    sp = (server_path or "").strip()
    if sp:
        sp_norm = _strip_trailing_slash(_ensure_leading_slash(sp))
        raw_sp = sp_norm.strip("/")
        sp_inner = _strip_redundant_host_path_segments(raw_sp, base_host)
        pic_enc = _quote_path_segments(pic)
        if not pic_enc:
            return ""
        sp_enc = _quote_path_segments(sp_inner) if sp_inner else ""
        if sp_enc:
            return f"{base}/{sp_enc}/{pic_enc}"
        # server_path stripped to nothing (e.g. only duplicated the CDN hostname): do not append it.
        return f"{base}/{pic_enc}"

    pic_enc = _quote_path_segments(pic)
    if not pic_enc:
        return ""
    return f"{base}/{pic_enc}"


def get_asset_base_url() -> str:
    return (os.getenv("MP_ASSET_CDN_BASE") or os.getenv("ASSET_BASE_URL") or "https://masterpiece.s3.amazonaws.com").strip()


def is_url_host_allowed(resolved_url: str, *, allowlist_csv: str | None) -> bool:
    """
    If allowlist_csv is empty, all http(s) URLs are allowed.
    Otherwise resolved host must match one entry (case-insensitive).
    """
    raw = (allowlist_csv or "").strip()
    if not raw:
        return _is_http_url(resolved_url)

    try:
        host = (urlparse(resolved_url).hostname or "").lower()
    except Exception:
        return False
    if not host:
        return False
    allowed = {a.strip().lower() for a in raw.split(",") if a.strip()}
    return host in allowed


def _is_http_url(url: str) -> bool:
    try:
        p = urlparse(url)
        return p.scheme in {"http", "https"} and bool(p.netloc)
    except Exception:
        return False


def sanitize_filename_hint(name: str) -> str:
    """Best-effort strip for logging; not a security boundary."""
    return re.sub(r"[^\w.\-]+", "_", (name or "")[:200])
