"""Custom frame_finish drawing (wall art only)."""

from __future__ import annotations

from PIL import Image

from app.showcase.compositor import (
    CompositeParams,
    _custom_frame_active,
    _draw_custom_frame_rect,
    _normalize_frame_finish,
    _normalize_frame_profile,
)


def test_normalize_frame_finish() -> None:
    assert _normalize_frame_finish(None) is None
    assert _normalize_frame_finish("  Rosewood ") == "rosewood"
    assert _normalize_frame_finish("thin-black-metal") == "thin_black_metal"
    assert _normalize_frame_finish("not_a_finish") is None


def test_custom_frame_inactive_on_pedestal() -> None:
    p = CompositeParams(frame_finish="walnut")
    assert _custom_frame_active(p, is_pedestal=False) is True
    assert _custom_frame_active(p, is_pedestal=True) is False


def test_draw_custom_frame_changes_pixels() -> None:
    layer = Image.new("RGBA", (120, 100), (0, 0, 0, 0))
    before = layer.tobytes()
    _draw_custom_frame_rect(layer, (30, 20, 90, 80), finish_key="maple", profile=_normalize_frame_profile("thick"))
    assert layer.tobytes() != before


def test_profile_normalization() -> None:
    assert _normalize_frame_profile(None) == "thin"
    assert _normalize_frame_profile("THICK") == "thick"
