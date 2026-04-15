"""Smoke tests for showcase compositor lighting presets (deterministic pixel paths)."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from app.showcase.compositor import _apply_lighting, _normalize_lighting_key


def _sample_rgb(w: int = 64, h: int = 48) -> Image.Image:
    return Image.linear_gradient("L").resize((w, h)).convert("RGB")


@pytest.mark.parametrize(
    "preset",
    [
        "gallery_track_wash",
        "pedestal_spot",
        "warm_ambient",
        "daylight_north",
        "morning_sunlight_beam",
        "oblique_shadow",
        "sunset",
        "tree_shade",
        "hazy",
        "warm",
        "cool",
        "bamboo_shadow",
        "flower_shadow",
    ],
)
def test_apply_lighting_runs(preset: str) -> None:
    base = _sample_rgb()
    out = _apply_lighting(base, preset, "gallery_white_wall")
    assert out.mode == "RGB"
    assert out.size == base.size
    assert out.tobytes() != base.tobytes()


def test_normalize_lighting_aliases() -> None:
    assert _normalize_lighting_key(" ") == "gallery_track_wash"
    assert _normalize_lighting_key(None) == "gallery_track_wash"
    assert _normalize_lighting_key("Tres Shade") == "tree_shade"
    assert _normalize_lighting_key("morning sun") == "morning_sunlight_beam"


def test_unknown_lighting_key_is_noop_except_pedestal_scene_boost() -> None:
    base = _sample_rgb()
    out = _apply_lighting(base, "not_a_real_preset_xyz", "gallery_white_wall")
    assert out.tobytes() == base.tobytes()
    out_ped = _apply_lighting(base, "not_a_real_preset_xyz", "pedestal_sculpture_spot")
    assert out_ped.tobytes() != base.tobytes()


def test_png_roundtrip_after_lighting() -> None:
    base = _sample_rgb(32, 24)
    out = _apply_lighting(base, "sunset", "gallery_white_wall")
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    assert len(buf.getvalue()) > 80