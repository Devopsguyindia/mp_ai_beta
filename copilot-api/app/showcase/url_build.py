from __future__ import annotations

import os
import re
from urllib.parse import urlparse


def _strip_trailing_slash(s: str) -> str:
    return s.rstrip("/")


def _ensure_leading_slash(path: str) -> str:
    if not path:
        return ""
    return path if path.startswith("/") else f"/{path}"


def resolve_picture_url(*, base_url: str, server_path: str | None, picture: str) -> str:
    """
    Build final_url = base + server_path + picture with slash normalization.
    """
    base = _strip_trailing_slash((base_url or "").strip())
    pic = (picture or "").strip().lstrip("/")
    if not base or not pic:
        return ""

    sp = (server_path or "").strip()
    if sp:
        sp_norm = _strip_trailing_slash(_ensure_leading_slash(sp))
        return f"{base}{sp_norm}/{pic}"
    return f"{base}/{pic}"


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
