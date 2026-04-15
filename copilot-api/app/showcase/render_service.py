from __future__ import annotations

import hashlib
from typing import Any


def build_render_cache_key(
    *,
    idcompany_item_pictures: int,
    scene_id: str,
    pipeline_version: str,
    frame_style: str | None = None,
    frame_finish: str | None = None,
    frame_profile: str | None = None,
    lighting: str | None = None,
    placement: str | None = None,
    layout_variant: int | None = None,
    cutout: bool = False,
    physical_width_cm: float | None = None,
    physical_height_cm: float | None = None,
    wall_width_cm: float | None = None,
    wall_span_cm: float | None = None,
    focal_wall_rect: tuple[float, float, float, float] | None = None,
    placement_quad: list[tuple[float, float]] | None = None,
    art_spotlight: str | None = None,
) -> str:
    lv = "" if layout_variant is None else str(layout_variant)
    asp = (art_spotlight or "").strip().lower()
    pw = "" if physical_width_cm is None else f"{physical_width_cm:.4f}"
    ph = "" if physical_height_cm is None else f"{physical_height_cm:.4f}"
    ww = "" if wall_width_cm is None else f"{wall_width_cm:.4f}"
    wsp = "" if wall_span_cm is None else f"{wall_span_cm:.4f}"
    fr = ""
    if focal_wall_rect:
        fr = ",".join(f"{x:.5f}" for x in focal_wall_rect)
    pq = ""
    if placement_quad:
        pq = ";".join(f"{x:.5f},{y:.5f}" for x, y in placement_quad)
    ff = (frame_finish or "").strip().lower()
    fp = (frame_profile or "").strip().lower()
    raw = (
        f"{idcompany_item_pictures}|{scene_id}|{pipeline_version}|"
        f"{frame_style or ''}|{ff}|{fp}|{lighting or ''}|{placement or ''}|"
        f"{lv}|{int(cutout)}|{pw}|{ph}|{ww}|{wsp}|{fr}|{pq}|{asp}"
    ).encode("utf-8")
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
    frame_finish: str | None = None,
    frame_profile: str | None = None,
    layout_variant: int | None = None,
    cutout: bool = False,
    physical_width_cm: float | None = None,
    physical_height_cm: float | None = None,
    wall_width_cm: float | None = None,
    wall_span_cm: float | None = None,
    focal_wall_rect: tuple[float, float, float, float] | None = None,
    placement_quad: list[tuple[float, float]] | None = None,
    art_spotlight: str | None = None,
) -> dict[str, Any]:
    """
    MVP: no pixel compositing. Returns pass-through URL + cache key for future compositor / CDN.
    """
    cache_key = build_render_cache_key(
        idcompany_item_pictures=idcompany_item_pictures,
        scene_id=scene_id,
        pipeline_version=pipeline_version,
        frame_style=frame_style,
        frame_finish=frame_finish,
        frame_profile=frame_profile,
        lighting=lighting,
        placement=placement,
        layout_variant=layout_variant,
        cutout=cutout,
        physical_width_cm=physical_width_cm,
        physical_height_cm=physical_height_cm,
        wall_width_cm=wall_width_cm,
        wall_span_cm=wall_span_cm,
        focal_wall_rect=focal_wall_rect,
        placement_quad=placement_quad,
        art_spotlight=art_spotlight,
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


def composited_render_result(
    *,
    preview_api_url: str,
    cache_key: str,
    scene_id: str,
    pipeline_version: str,
    frame_style: str | None,
    lighting: str | None,
    placement: str | None,
) -> dict[str, Any]:
    """
    Server compositor wrote PNG to cache; preview_api_url is GET .../render/{cache_key}/preview.
    """
    return {
        "output_mode": "composited",
        "pipeline_version": pipeline_version,
        "cache_key": cache_key,
        "preview_url": preview_api_url,
        "scene_id": scene_id,
        "frame_style": frame_style,
        "lighting": lighting,
        "placement": placement,
        "compositor_status": "ok",
    }
