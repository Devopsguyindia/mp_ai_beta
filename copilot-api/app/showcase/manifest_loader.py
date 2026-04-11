from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

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
        scenes.append(
            SceneInfo(
                scene_id=sid,
                label=label,
                description=str(s.get("description")).strip() if s.get("description") else None,
                preview_asset_url=str(s.get("preview_asset_url")).strip() if s.get("preview_asset_url") else None,
                qa_status=str(s.get("qa_status")).strip() if s.get("qa_status") else None,
                tags=tag_list,
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
