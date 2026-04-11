from __future__ import annotations

import hashlib
from typing import Any


def build_render_cache_key(
    *,
    idcompany_item_pictures: int,
    scene_id: str,
    pipeline_version: str,
) -> str:
    raw = f"{idcompany_item_pictures}|{scene_id}|{pipeline_version}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def stub_render_result(
    *,
    resolved_artwork_url: str,
    idcompany_item_pictures: int,
    scene_id: str,
    pipeline_version: str,
    frame_style: str | None,
    lighting: str | None,
    placement: str | None,
) -> dict[str, Any]:
    """
    MVP: no pixel compositing. Returns pass-through URL + cache key for future compositor / CDN.
    """
    cache_key = build_render_cache_key(
        idcompany_item_pictures=idcompany_item_pictures,
        scene_id=scene_id,
        pipeline_version=pipeline_version,
    )
    return {
        "output_mode": "pass_through",
        "pipeline_version": pipeline_version,
        "cache_key": cache_key,
        "preview_url": resolved_artwork_url,
        "scene_id": scene_id,
        "frame_style": frame_style,
        "lighting": lighting,
        "placement": placement,
        "compositor_status": "not_run",
    }
