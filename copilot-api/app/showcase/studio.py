from __future__ import annotations

import re
from typing import Any

from .models import SceneInfo


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def detect_artwork_kind(*, title: str | None, category_label: str | None, medium_label: str | None) -> str:
    blob = f"{title or ''} {category_label or ''} {medium_label or ''}".lower()
    if any(
        t in blob
        for t in [
            "sculpture",
            "bronze",
            "marble",
            "pedestal",
            "maquette",
            "installation",
            "3d",
            "ceramic",
            "glass sculpture",
        ]
    ):
        return "3d_pedestal"
    if any(w in blob for w in ["photo", "photograph", "chromogenic", "gelatin silver", "c-print", "archival pigment"]):
        return "photography"
    if any(w in blob for w in ["etching", "lithograph", "screenprint", "woodcut", "work on paper", "print"]):
        return "works_on_paper"
    return "2d_wall"


def _art_style_keywords(blob: str) -> set[str]:
    out: set[str] = set()
    for k in [
        "abstract",
        "modern",
        "minimal",
        "contemporary",
        "classical",
        "warm",
        "cool",
        "neutral",
        "luxury",
        "traditional",
    ]:
        if k in blob:
            out.add(k)
    return out


def analyze_artwork_for_showcase(
    *,
    item_title: str | None,
    category_label: str | None,
    medium_label: str | None,
    scenes: list[SceneInfo],
) -> dict[str, Any]:
    """
    Phase 1 Studio: rule-based artwork type, placement, frame/lighting suggestions, style ↔ interior matching.
    No LLM — safe for core API isolation.
    """
    title = item_title or ""
    blob = f"{title} {category_label or ''} {medium_label or ''}".lower()
    kind = detect_artwork_kind(title=title, category_label=category_label, medium_label=medium_label)

    if kind == "3d_pedestal":
        placement = "pedestal_center"
        frame_suggestions = ["none", "minimal_plinth"]
        lighting_suggestions = ["pedestal_spot", "gallery_track_wash"]
    elif kind == "photography":
        placement = "wall_eye_level"
        frame_suggestions = ["thin_black", "gallery_white", "traditional_matted"]
        lighting_suggestions = [
            "gallery_track_wash",
            "daylight_north",
            "warm_ambient",
            "morning_sunlight_beam",
            "sunset",
        ]
    elif kind == "works_on_paper":
        placement = "wall_eye_level"
        frame_suggestions = ["traditional_matted", "thin_black", "gold_ornate"]
        lighting_suggestions = [
            "gallery_track_wash",
            "daylight_north",
            "oblique_shadow",
            "tree_shade",
            "hazy",
        ]
    else:
        placement = "wall_eye_level"
        frame_suggestions = ["floater_modern", "traditional_matted", "gallery_white", "gold_ornate"]
        lighting_suggestions = [
            "gallery_track_wash",
            "warm_ambient",
            "daylight_north",
            "bamboo_shadow",
            "flower_shadow",
        ]

    art_kw = _art_style_keywords(blob)
    style_matches: list[dict[str, Any]] = []
    for s in scenes:
        score = 0.0
        interior = _norm(s.interior_style)
        tags_l = " ".join(s.tags or []).lower()
        room = _norm(s.room_category)
        for kw in art_kw:
            if kw in interior or kw in tags_l:
                score += 0.22
        if kind == "3d_pedestal" and any(t.lower() in {"3d", "sculpture"} for t in (s.tags or [])):
            score += 0.45
        if kind != "3d_pedestal" and any(t.lower() in {"2d", "wall"} for t in (s.tags or [])):
            score += 0.25
        if room and room in tags_l:
            score += 0.06
        score = min(round(score, 2), 1.0)
        style_matches.append({"scene_id": s.scene_id, "label": s.label, "score": score})

    style_matches.sort(key=lambda x: float(x["score"]), reverse=True)
    scene_ranking = [str(x["scene_id"]) for x in style_matches]

    notes_parts: list[str] = []
    if re.search(r"\b\d+\s*(cm|mm|in|inch)\b", blob):
        notes_parts.append("Dimensions detected in title — use physical width/height for realistic scale.")
    if not art_kw:
        notes_parts.append("Add style keywords in inventory for tighter room matching.")

    return {
        "artwork_kind": kind,
        "detected_placement": placement,
        "frame_suggestions": frame_suggestions,
        "lighting_suggestions": lighting_suggestions,
        "style_matches": style_matches[: min(16, len(style_matches))],
        "scene_ranking": scene_ranking,
        "notes": " ".join(notes_parts) if notes_parts else None,
    }
