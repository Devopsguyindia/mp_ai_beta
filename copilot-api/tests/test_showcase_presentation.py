from app.showcase.models import SceneInfo
from app.showcase.presentation import build_options_payload, infer_medium_category_hints, rule_based_recommendation


def test_infer_medium_from_title():
    c, m = infer_medium_category_hints(item_title="Oil on canvas landscape", artist_display=None)
    assert m == "Painting"
    assert c == "Landscape"


def test_rule_based_prefers_sculpture_scene():
    scenes = [
        SceneInfo(scene_id="gallery_white_wall", label="Wall", tags=["2d", "wall"]),
        SceneInfo(scene_id="pedestal_sculpture_spot", label="Plinth", tags=["3d", "sculpture"]),
    ]
    r = rule_based_recommendation(
        item_title="Bronze maquette",
        edition_label=None,
        artist_display=None,
        scenes=scenes,
    )
    assert r["recommended_scene_ids"][0] == "pedestal_sculpture_spot"


def test_build_options_includes_picture_ids():
    scenes = [
        SceneInfo(scene_id="gallery_white_wall", label="Wall", tags=["2d"]),
    ]
    p = build_options_payload(
        item_title="Work",
        edition_label="Open",
        artist_display=None,
        category_label=None,
        medium_label=None,
        picture_ids=[101, 102],
        scenes=scenes,
    )
    assert p["suitable_picture_ids"] == [101, 102]
    assert "gallery_white_wall" in (p.get("recommended_scene_ids") or [])
