from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from .compositor_geometry import parse_focal_rect_from_json, parse_quad_from_json, valid_focal_rect, valid_placement_quad
from .models import SceneInfo

logger = logging.getLogger(__name__)

_MANIFEST_NAME = "scene_library_manifest.json"


def _default_manifest_path() -> Path:
    return Path(__file__).resolve().parent / "data" / _MANIFEST_NAME


def load_scene_manifest() -> tuple[str, list[SceneInfo]]:
    """
    Load curated scene library (S3 URLs optional). pipeline_version groups cache/render keys.
    Override path with SHOWCASE_SCENE_MANIFEST_PATH; or set SHOWCASE_SCENE_MANIFEST_JSON inline for tests.
    """
    raw_env = (os.getenv("SHOWCASE_SCENE_MANIFEST_JSON") or "").strip()
    if raw_env:
        try:
            payload = json.loads(raw_env)
        except json.JSONDecodeError as e:
            logger.warning("SHOWCASE_SCENE_MANIFEST_JSON invalid: %s", e)
            payload = {}
    else:
        path_s = (os.getenv("SHOWCASE_SCENE_MANIFEST_PATH") or "").strip()
        path = Path(path_s) if path_s else _default_manifest_path()
        if not path.is_file():
            logger.warning("showcase manifest missing at %s", path)
            return ("scene-lib-missing", [])
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("showcase manifest read failed: %s", e)
            return ("scene-lib-read-error", [])

    if not isinstance(payload, dict):
        return ("scene-lib-invalid", [])

    version = str(payload.get("pipeline_version") or "scene-lib-unknown")
    scenes_raw = payload.get("scenes")
    if not isinstance(scenes_raw, list):
        return (version, [])

    scenes: list[SceneInfo] = []
    for s in scenes_raw:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("scene_id") or "").strip()
        label = str(s.get("label") or "").strip()
        if not sid or not label:
            continue
        tags = s.get("tags")
        tag_list = [str(t) for t in tags] if isinstance(tags, list) else []
        layout_raw = s.get("layout_index")
        try:
            layout_idx = int(layout_raw) if layout_raw is not None else 0
        except (TypeError, ValueError):
            layout_idx = 0
        focal_wall_rect = None
        fr_raw = s.get("focal_wall_rect")
        if fr_raw is not None:
            ft = parse_focal_rect_from_json(fr_raw)
            if ft and valid_focal_rect(ft):
                focal_wall_rect = ft
        placement_quad = None
        pq_raw = s.get("placement_quad")
        if pq_raw is not None:
            pq = parse_quad_from_json(pq_raw)
            if pq and valid_placement_quad(pq):
                placement_quad = pq
        try:
            eye_level_fraction = float(s["eye_level_fraction"])
            eye_level_fraction = max(0.0, min(1.0, eye_level_fraction))
        except (KeyError, TypeError, ValueError):
            eye_level_fraction = 0.48
        try:
            wall_span_cm = float(s["wall_span_cm"]) if s.get("wall_span_cm") else None
        except (TypeError, ValueError):
            wall_span_cm = None
        scenes.append(
            SceneInfo(
                scene_id=sid,
                label=label,
                description=str(s.get("description")).strip() if s.get("description") else None,
                preview_asset_url=str(s.get("preview_asset_url")).strip() if s.get("preview_asset_url") else None,
                qa_status=str(s.get("qa_status")).strip() if s.get("qa_status") else None,
                tags=tag_list,
                room_category=str(s.get("room_category")).strip() if s.get("room_category") else None,
                interior_style=str(s.get("interior_style")).strip() if s.get("interior_style") else None,
                placement_hint=str(s.get("placement_hint")).strip() if s.get("placement_hint") else None,
                layout_index=max(0, min(7, layout_idx)),
                focal_wall_rect=focal_wall_rect,
                placement_quad=placement_quad,
                eye_level_fraction=eye_level_fraction,
                wall_span_cm=wall_span_cm,
            )
        )
    return (version, scenes)


def manifest_dict_for_pipeline() -> dict[str, Any]:
    """Minimal dict for batch tooling / documentation (not an API response)."""
    v, scenes = load_scene_manifest()
    return {
        "pipeline_version": v,
        "scene_count": len(scenes),
        "manifest_path_default": str(_default_manifest_path()),
    }
