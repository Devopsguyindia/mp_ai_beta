"""Who may request client-visible debug payloads (aligned with copilot-widget-v3 AuthService)."""

from __future__ import annotations

import base64
import json
from typing import Any


def _decode_jwt_payload_unverified(token: str) -> dict[str, Any]:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8")
        data = json.loads(decoded)
        if isinstance(data, dict):
            return data
        return {}
    except Exception:
        return {}


def is_jesse_debug_viewer(access_token: str | None, user_id: str | None = None) -> bool:
    """True when explicit user_id or JWT claims identify login ``jesse`` (case-insensitive)."""
    candidates: list[str] = []
    if user_id is not None and str(user_id).strip():
        candidates.append(str(user_id).strip().lower())
    tok = (access_token or "").strip()
    if tok:
        payload = _decode_jwt_payload_unverified(tok)
        for key in ("userid", "user_id", "sub", "username", "firstname", "fullname"):
            v = payload.get(key)
            if v is not None and str(v).strip():
                candidates.append(str(v).strip().lower())
    return "jesse" in candidates
