from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

def fetch_remote_image_bytes(
    url: str,
    *,
    timeout_s: float,
    max_bytes: int,
) -> tuple[bytes, str | None]:
    """
    Fetch an http(s) resource into memory (bounded by max_bytes).
    URL must only be used after DB + allowlist validation (SSRF mitigation).
    """
    ua = (os.getenv("SHOWCASE_IMAGE_FETCH_UA") or "copilot-api-showcase/1.0").strip()
    req = Request(url, headers={"User-Agent": ua})
    with urlopen(req, timeout=timeout_s) as resp:  # noqa: S310
        content_type = resp.headers.get("Content-Type")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = resp.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise OSError("image exceeds SHOWCASE_IMAGE_PROXY_MAX_BYTES")
            chunks.append(chunk)
    return b"".join(chunks), content_type


def fetch_remote_image_bytes_first_available(
    urls: Sequence[str],
    *,
    timeout_s: float,
    max_bytes: int,
) -> tuple[bytes, str | None]:
    """Try each URL until one succeeds (same ordering as compositor artwork fetch)."""
    ordered: list[str] = []
    seen: set[str] = set()
    for u in urls:
        t = (u or "").strip()
        if t and t not in seen:
            seen.add(t)
            ordered.append(t)
    if not ordered:
        raise OSError("no artwork URLs to fetch")
    last_err: Exception | None = None
    for u in ordered:
        try:
            return fetch_remote_image_bytes(u, timeout_s=timeout_s, max_bytes=max_bytes)
        except Exception as e:
            last_err = e
            logger.info("showcase fetch: artwork URL failed %s: %s", u[:96], e)
    assert last_err is not None
    raise last_err

