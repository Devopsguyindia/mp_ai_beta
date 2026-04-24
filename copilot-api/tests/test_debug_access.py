"""Tests for client debug viewer gate (Jesse-only)."""

from __future__ import annotations

import base64
import json

from app.debug_access import is_jesse_debug_viewer


def _fake_jwt(payload: dict) -> str:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    b64 = base64.urlsafe_b64encode(body).decode("ascii").rstrip("=")
    return f"e30.{b64}.sig"


def test_jesse_from_user_id_no_token() -> None:
    assert is_jesse_debug_viewer(None, "jesse") is True
    assert is_jesse_debug_viewer(None, "Jesse") is True
    assert is_jesse_debug_viewer(None, " other ") is False


def test_jesse_from_jwt_userid() -> None:
    tok = _fake_jwt({"userid": "jesse", "idcompany": 1})
    assert is_jesse_debug_viewer(tok, None) is True


def test_jesse_from_jwt_username_fallback() -> None:
    tok = _fake_jwt({"username": "jesse", "idcompany": 1})
    assert is_jesse_debug_viewer(tok, None) is True


def test_jesse_from_jwt_firstname_fallback() -> None:
    tok = _fake_jwt({"firstname": "Jesse", "idcompany": 1})
    assert is_jesse_debug_viewer(tok, None) is True


def test_non_jesse_jwt() -> None:
    tok = _fake_jwt({"userid": "alice", "idcompany": 1})
    assert is_jesse_debug_viewer(tok, None) is False


def test_empty_token() -> None:
    assert is_jesse_debug_viewer("", None) is False
    assert is_jesse_debug_viewer(None, None) is False


def test_user_id_overrides_when_token_differs() -> None:
    tok = _fake_jwt({"userid": "alice", "idcompany": 1})
    assert is_jesse_debug_viewer(tok, "jesse") is True
