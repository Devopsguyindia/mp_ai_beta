from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from fastapi import HTTPException
from fastapi.responses import Response

DEFAULT_GENERATE_BASE = "https://v12-api.masterpiecemanager.com/reports/generateReport"


def _generate_base_url() -> str:
    return os.getenv("MP_REPORT_GENERATE_URL", DEFAULT_GENERATE_BASE).rstrip("?")


def build_report_generate_url(filter_data: str) -> str:
    """
    Build GET URL with query string from filter_data JSON object.

    Masterpiece expects every parameter key present (including empty values), e.g.
    mailingVendors=&mailingArtists=&... matching the stored filter JSON order.
    """
    try:
        data = json.loads(filter_data)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_filter_data_json", "message": str(e)},
        ) from e
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=400,
            detail={"error": "filter_data_not_object", "message": "filter_data must be a JSON object"},
        )
    pairs: list[tuple[str, str]] = []
    for k, v in data.items():
        if v is None:
            s = ""
        else:
            s = str(v)
        pairs.append((str(k), s))
    qs = urllib.parse.urlencode(pairs)
    base = _generate_base_url()
    return f"{base}?{qs}" if qs else base


def _authorization_value(access_token: str) -> str:
    """
    Value for the Authorization header on generateReport (same token as sign-in API).

    Default: raw JWT/string only (Masterpiece expects the sign-in token as the header value).
    Set MP_REPORT_AUTH_BEARER=1 to send ``Bearer <token>`` instead.
    """
    token = access_token.strip()
    bearer = os.getenv("MP_REPORT_AUTH_BEARER", "").lower() in {"1", "true", "yes"}
    if bearer:
        if token.lower().startswith("bearer "):
            return token
        return f"Bearer {token}"
    return token


def proxy_generate_report_get(*, access_token: str, filter_data: str) -> Response:
    """
    Server-side GET to MP generateReport (avoids browser CORS).

    Sends header: Authorization: <sign-in token> (raw by default; Bearer if MP_REPORT_AUTH_BEARER=1).
    """
    url = build_report_generate_url(filter_data)
    timeout = int(os.getenv("MP_REPORT_GENERATE_TIMEOUT_SEC", "120"))
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": _authorization_value(access_token),
            "Accept": "*/*",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            ct = resp.headers.get("Content-Type", "application/octet-stream")
            cd = resp.headers.get("Content-Disposition")
            headers: dict[str, str] = {}
            if cd:
                headers["Content-Disposition"] = cd
            return Response(content=body, media_type=ct, headers=headers)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:4000]
        raise HTTPException(
            status_code=e.code,
            detail={
                "error": "upstream_generate_report_failed",
                "message": err_body[:800],
                "host": urllib.parse.urlparse(url).netloc,
            },
        ) from e
    except urllib.error.URLError as e:
        raise HTTPException(
            status_code=502,
            detail={"error": "upstream_unreachable", "message": str(e.reason or e)},
        ) from e
