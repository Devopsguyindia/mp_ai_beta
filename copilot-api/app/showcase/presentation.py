from __future__ import annotations

import json
import logging
import os
from typing import Any

from .models import SceneInfo

logger = logging.getLogger(__name__)


def infer_medium_category_hints(*, item_title: str | None, artist_display: str | None) -> tuple[str | None, str | None]:
    """
    Soft inventory-like hints when ERP does not expose category/medium columns in SQL.
    Prefer database fields when present; this only fills gaps.
    """
    blob = f"{item_title or ''} {artist_display or ''}".lower()
    medium: str | None = None
    category: str | None = None

    if any(w in blob for w in ["oil ", "oil,", "acrylic", "watercolor", "gouache", "tempera"]):
        medium = "Painting"
    elif any(w in blob for w in ["bronze", "marble", "steel", "stone", "wood carving", "ceramic", "glass sculpture"]):
        medium = "Sculpture"
    elif any(w in blob for w in ["photograph", "chromogenic", "gelatin silver", "c-print", "archival pigment"]):
        medium = "Photography"
    elif any(w in blob for w in ["etching", "lithograph", "screenprint", "woodcut", "print"]):
        medium = "Work on paper"

    if any(w in blob for w in ["abstract", "non-objective"]):
        category = "Abstract"
    elif any(w in blob for w in ["landscape", "seascape", "cityscape"]):
        category = "Landscape"
    elif any(w in blob for w in ["portrait", "self-portrait"]):
        category = "Portrait"
    elif any(w in blob for w in ["still life"]):
        category = "Still life"

    return (category, medium)


def rule_based_recommendation(
    *,
    item_title: str | None,
    edition_label: str | None,
    artist_display: str | None,
    scenes: list[SceneInfo],
) -> dict[str, Any]:
    """Deterministic taxonomy → scene / frame / lighting (no LLM)."""
    blob = f"{item_title or ''} {edition_label or ''} {artist_display or ''}".lower()
    want_3d = any(
        t in blob
        for t in ["sculpture", "bronze", "marble", "pedestal", "maquette", "installation", "3d", "glass "]
    )
    ranked: list[str] = []

    def _style_boost(scene: SceneInfo) -> float:
        interior = (scene.interior_style or "").lower()
        score = 0.0
        for word in interior.replace(",", " ").split():
            w = word.strip()
            if len(w) > 3 and w in blob:
                score += 0.35
        rc = (scene.room_category or "").lower()
        if rc and rc in blob:
            score += 0.2
        return score

    scored: list[tuple[float, str]] = []
    for s in scenes:
        tags = {t.lower() for t in (s.tags or [])}
        pri = 0.0
        if want_3d and ("3d" in tags or "sculpture" in tags):
            pri += 2.0
        pri += _style_boost(s)
        scored.append((pri, s.scene_id))
    scored.sort(key=lambda x: x[0], reverse=True)
    ranked = [sid for _p, sid in scored]

    frame_style = "floater_modern" if "canvas" in blob or medium_is_canvas(edition_label) else "traditional_matted"
    lighting = "pedestal_spot" if want_3d else "gallery_track_wash"
    placement = "pedestal_center" if want_3d else "wall_eye_level"

    return {
        "recommended_scene_ids": ranked[:5],
        "frame_style": frame_style,
        "lighting": lighting,
        "placement": placement,
        "source": "rules",
    }


def medium_is_canvas(edition_label: str | None) -> bool:
    if not edition_label:
        return False
    return "canvas" in edition_label.lower()


def maybe_enrich_with_llm(
    *,
    item_title: str | None,
    edition_label: str | None,
    artist_display: str | None,
    category_label: str | None,
    medium_label: str | None,
    scenes: list[SceneInfo],
    rule_result: dict[str, Any],
) -> dict[str, Any]:
    if os.getenv("SHOWCASE_PRESENTATION_LLM_ENABLED", "0") not in {"1", "true", "TRUE", "yes", "YES"}:
        return rule_result

    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return rule_result

    scene_ids = [s.scene_id for s in scenes]
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        model = os.getenv("SHOWCASE_PRESENTATION_MODEL", "gpt-4.1-mini")
        prompt = (
            "You help art galleries pick a showroom scene id from a fixed list. "
            "Respond with JSON only: "
            '{"recommended_scene_ids": string[], "frame_style": string, "lighting": string, '
            '"placement": string, "notes": string}. '
            f"Valid scene_id values: {scene_ids}. "
            f"Item title: {item_title!r}. Edition: {edition_label!r}. Artist: {artist_display!r}. "
            f"Category: {category_label!r}. Medium: {medium_label!r}."
        )
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        content = (resp.choices[0].message.content or "").strip()
        data = json.loads(content)
        if not isinstance(data, dict):
            return rule_result
        ids = data.get("recommended_scene_ids")
        if isinstance(ids, list):
            cleaned = [str(x) for x in ids if str(x) in scene_ids]
            if cleaned:
                data["recommended_scene_ids"] = cleaned
        data["source"] = "llm"
        return {**rule_result, **data}
    except Exception as e:
        logger.warning("showcase presentation LLM skipped: %s", e)
        return rule_result


def build_options_payload(
    *,
    item_title: str | None,
    edition_label: str | None,
    artist_display: str | None,
    category_label: str | None,
    medium_label: str | None,
    picture_ids: list[int],
    scenes: list[SceneInfo],
) -> dict[str, Any]:
    cat_hint, med_hint = infer_medium_category_hints(item_title=item_title, artist_display=artist_display)
    merged_category = category_label or cat_hint
    merged_medium = medium_label or med_hint

    rules = rule_based_recommendation(
        item_title=item_title,
        edition_label=edition_label,
        artist_display=artist_display,
        scenes=scenes,
    )
    merged = maybe_enrich_with_llm(
        item_title=item_title,
        edition_label=edition_label,
        artist_display=artist_display,
        category_label=merged_category,
        medium_label=merged_medium,
        scenes=scenes,
        rule_result=rules,
    )
    return {
        "category_label": merged_category,
        "medium_label": merged_medium,
        "recommended_scene_ids": merged.get("recommended_scene_ids"),
        "frame_style": merged.get("frame_style"),
        "lighting": merged.get("lighting"),
        "placement": merged.get("placement"),
        "suitable_picture_ids": picture_ids,
        "presentation_source": merged.get("source"),
        "notes": merged.get("notes") if isinstance(merged.get("notes"), str) else None,
    }
