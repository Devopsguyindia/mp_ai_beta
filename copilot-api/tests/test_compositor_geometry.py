"""Tests for homography helpers and manifest placement fields."""

from PIL import Image

from app.showcase.compositor_geometry import (
    focal_rect_to_pixels,
    pil_perspective_coeffs,
    quad_bbox_wh,
    quad_norm_to_pixels,
    valid_focal_rect,
    valid_placement_quad,
)
from app.showcase.manifest_loader import load_scene_manifest


def test_focal_rect_to_pixels():
    l, t, r, b = focal_rect_to_pixels((0.1, 0.2, 0.9, 0.8), 1000, 500)
    assert (l, t, r, b) == (100, 100, 900, 400)


def test_valid_focal_rect():
    assert valid_focal_rect((0.1, 0.1, 0.9, 0.9))
    assert not valid_focal_rect(None)
    assert not valid_focal_rect((0.5, 0.5, 0.5, 0.6))


def test_quad_norm_and_bbox():
    q = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    pts = quad_norm_to_pixels(q, 200, 100)
    assert pts[0] == (0.0, 0.0)
    assert pts[2] == (200.0, 100.0)
    assert quad_bbox_wh(pts) == (200, 100)
    assert valid_placement_quad(q)


def test_pil_perspective_coeffs_maps_corners():
    src = [(0.0, 0.0), (50.0, 0.0), (50.0, 50.0), (0.0, 50.0)]
    dst = [(10.0, 10.0), (90.0, 5.0), (95.0, 80.0), (5.0, 85.0)]
    c = pil_perspective_coeffs(dst, src)
    im = Image.new("RGBA", (50, 50), (255, 0, 0, 255))
    out = im.transform((100, 100), Image.PERSPECTIVE, c, Image.Resampling.BICUBIC, fillcolor=(0, 0, 0, 0))
    assert out.getpixel((50, 45))[0] > 200


def test_manifest_loads_focal_and_quad(monkeypatch):
    import json

    payload = {
        "pipeline_version": "t-geom",
        "scenes": [
            {
                "scene_id": "s1",
                "label": "S",
                "focal_wall_rect": [0.1, 0.1, 0.9, 0.85],
                "placement_quad": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.8], [0.1, 0.8]],
            }
        ],
    }
    monkeypatch.setenv("SHOWCASE_SCENE_MANIFEST_JSON", json.dumps(payload))
    _v, scenes = load_scene_manifest()
    assert len(scenes) == 1
    assert scenes[0].focal_wall_rect == (0.1, 0.1, 0.9, 0.85)
    assert len(scenes[0].placement_quad or []) == 4
