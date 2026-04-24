from __future__ import annotations

import base64
import json
import logging
import os
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from starlette.responses import Response

from .backdrop_assets import packaged_scene_backdrop_path
from .manifest_loader import load_scene_manifest
from .models import (
    ItemPictureRow,
    ItemPicturesResponse,
    SceneInfo,
    ScenesResponse,
    ShowcaseBatchRenderItem,
    ShowcaseBatchRenderRequest,
    ShowcaseBatchRenderResponse,
    ShowcaseOptionsRequest,
    ShowcaseOptionsResponse,
    ShowcaseRenderRequest,
    ShowcaseRenderResponse,
    ShowcaseShareRequest,
    ShowcaseShareResponse,
    ShowcaseStudioAnalyzeRequest,
    ShowcaseStudioAnalyzeResponse,
)
from .compositor import CompositeParams, load_artwork_rgba_first_available, run_pixel_composite, run_pixel_composite_from_art
from .compositor_cache import get_compositor_cache
from .picture_stream import fetch_remote_image_bytes_first_available
from .pictures_repo import ItemContext, fetch_item_pictures, showcase_debug_log_enabled
from .presentation import build_options_payload
from .render_service import build_render_cache_key, composited_render_result, stub_render_result
from .studio import analyze_artwork_for_showcase
from .url_build import get_asset_base_url, resolve_artwork_fetch_url_candidates
from ..debug_access import is_jesse_debug_viewer

logger = logging.getLogger(__name__)


def _showcase_client_debug_effective(requested: bool, access_token: str | None) -> bool:
    return bool(requested) and is_jesse_debug_viewer(access_token, None)


def _expose_debug_in_error(dbg: dict | object | None, *, requested: bool, access_token: str | None) -> bool:
    if not dbg:
        return False
    return _showcase_client_debug_effective(requested, access_token) or showcase_debug_log_enabled()


def _public_api_base(request: Request) -> str:
    """Base URL embedded in absolute preview links (batch/single). Use when SPA origin differs from request.base_url (e.g. 127.0.0.1 vs localhost)."""
    raw = (os.getenv("SHOWCASE_PUBLIC_API_BASE") or "").strip()
    if raw:
        return raw.rstrip("/")
    return str(request.base_url).rstrip("/")


def _artwork_fetch_urls_from_row(row: dict) -> list[str]:
    pic_raw = row.get("picture")
    pic_s = str(pic_raw).strip() if pic_raw is not None else ""
    if not pic_s:
        return []
    sp_raw = row.get("server_path")
    sp_s: str | None = None
    if sp_raw is not None and str(sp_raw).strip():
        sp_s = str(sp_raw).strip()
    return resolve_artwork_fetch_url_candidates(
        base_url=get_asset_base_url(),
        server_path=sp_s,
        picture=pic_s,
    )


def _decode_jwt_payload_unverified(token: str) -> dict:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8")
        data = json.loads(decoded)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _resolve_idcompany(*, req_idcompany: int, access_token: str | None) -> int:
    if not access_token:
        return req_idcompany
    token_payload = _decode_jwt_payload_unverified(access_token)
    token_company = token_payload.get("company_id") or token_payload.get("idcompany")
    try:
        token_company_int = int(token_company)
    except Exception:
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_token", "message": "Could not resolve company_id from JWT token."},
        )
    if token_company_int != req_idcompany:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "company_mismatch",
                "message": "Request idcompany does not match JWT company_id.",
                "token_company_id": token_company_int,
                "request_idcompany": req_idcompany,
            },
        )
    return token_company_int


def _showcase_globally_enabled() -> bool:
    return os.getenv("SHOWCASE_ENABLED", "0") in {"1", "true", "TRUE", "yes", "YES"}


def _fetch_pictures_common(
    *,
    idcompany: int,
    idcompany_item: int,
    allow: str | None,
    request_id: str,
    want_client_debug: bool,
) -> tuple[str | None, ItemContext, list[dict[str, object]], dict[str, object] | None]:
    want_detail = want_client_debug or showcase_debug_log_enabled()
    return fetch_item_pictures(
        idcompany=idcompany,
        idcompany_item=idcompany_item,
        max_rows=int(os.getenv("SHOWCASE_PICTURES_MAX_ROWS", "50")),
        timeout_ms=int(os.getenv("MYSQL_QUERY_TIMEOUT_MS", "8000")),
        asset_allowlist=allow,
        request_id=request_id,
        include_debug_detail=want_detail,
    )


def _composite_params_from_render(req: ShowcaseRenderRequest) -> CompositeParams:
    return CompositeParams(
        frame_style=req.frame_style,
        frame_finish=req.frame_finish,
        frame_profile=req.frame_profile,
        lighting=req.lighting,
        placement=req.placement,
        layout_variant=req.layout_variant,
        cutout=req.cutout,
        physical_width_cm=req.physical_width_cm,
        physical_height_cm=req.physical_height_cm,
        wall_width_cm=req.wall_width_cm,
        wall_span_cm=req.wall_span_cm,
        focal_wall_rect_override=req.focal_wall_rect,
        placement_quad_override=req.placement_quad,
        art_spotlight=req.art_spotlight,
    )


def _composite_params_from_batch(req: ShowcaseBatchRenderRequest) -> CompositeParams:
    return CompositeParams(
        frame_style=req.frame_style,
        frame_finish=req.frame_finish,
        frame_profile=req.frame_profile,
        lighting=req.lighting,
        placement=req.placement,
        layout_variant=req.layout_variant,
        cutout=req.cutout,
        physical_width_cm=req.physical_width_cm,
        physical_height_cm=req.physical_height_cm,
        wall_width_cm=req.wall_width_cm,
        wall_span_cm=req.wall_span_cm,
        focal_wall_rect_override=req.focal_wall_rect,
        placement_quad_override=req.placement_quad,
        art_spotlight=req.art_spotlight,
    )


def _attach_response_debug(dbg: dict | None, *, want_client_debug: bool) -> dict | None:
    if not dbg:
        return None
    if want_client_debug or showcase_debug_log_enabled():
        return dbg
    return None


router = APIRouter(prefix="/showcase", tags=["showcase"])


@router.get("/items/{idcompany_item}/pictures", response_model=ItemPicturesResponse)
def get_item_pictures(
    idcompany_item: int,
    idcompany: int = Query(..., ge=1),
    access_token: str | None = None,
    debug: bool = Query(
        default=False,
        description="Include debug block in JSON (sql, sql_params, sql_effective, sql_row_count, skips, hints). Logs when SHOWCASE_DEBUG_LOG=1 too.",
    ),
) -> ItemPicturesResponse:
    if not _showcase_globally_enabled():
        raise HTTPException(status_code=404, detail={"error": "showcase_disabled"})
    rid = str(uuid.uuid4())
    resolved = _resolve_idcompany(req_idcompany=idcompany, access_token=access_token)
    allow = (os.getenv("SHOWCASE_ASSET_HOST_ALLOWLIST") or "").strip() or None
    pipeline_version, _ = load_scene_manifest()
    eff_debug = _showcase_client_debug_effective(debug, access_token)
    err, ctx, rows, dbg = _fetch_pictures_common(
        idcompany=resolved,
        idcompany_item=idcompany_item,
        allow=allow,
        request_id=rid,
        want_client_debug=eff_debug,
    )
    if err:
        detail: dict = {
            "error": "showcase_pictures_unavailable",
            "message": "Could not load item pictures.",
            "request_id": rid,
        }
        if _expose_debug_in_error(dbg, requested=debug, access_token=access_token):
            detail["debug"] = dbg
        raise HTTPException(status_code=503, detail=detail)
    pictures = [ItemPictureRow.model_validate(r) for r in rows]
    return ItemPicturesResponse(
        idcompany=resolved,
        idcompany_item=idcompany_item,
        item_title=ctx.item_title,
        artist_display=ctx.artist_display,
        edition_label=ctx.edition_label,
        item_edition_type=ctx.item_edition_type,
        category_label=ctx.category_label,
        medium_label=ctx.medium_label,
        pipeline_version=pipeline_version,
        pictures=pictures,
        debug=_attach_response_debug(dbg, want_client_debug=eff_debug),
    )


def _showcase_image_proxy_enabled() -> bool:
    return os.getenv("SHOWCASE_IMAGE_PROXY", "1") not in {"0", "false", "FALSE", "no", "NO"}


def _showcase_compositor_enabled() -> bool:
    return os.getenv("SHOWCASE_COMPOSITOR_ENABLED", "0") in {"1", "true", "TRUE", "yes", "YES"}


@router.get("/items/{idcompany_item}/pictures/{idcompany_item_pictures}/file")
def get_showcase_picture_file(
    idcompany_item: int,
    idcompany_item_pictures: int,
    idcompany: int = Query(..., ge=1),
    access_token: str | None = None,
) -> Response:
    """
    Stream the artwork bytes through the API so the browser is not blocked by CDN hotlink
    or S3 anonymous403 when objects are private (server-side fetch).
    """
    if not _showcase_globally_enabled():
        raise HTTPException(status_code=404, detail={"error": "showcase_disabled"})
    if not _showcase_image_proxy_enabled():
        raise HTTPException(status_code=404, detail={"error": "showcase_image_proxy_disabled"})
    rid = str(uuid.uuid4())
    company_id = _resolve_idcompany(req_idcompany=idcompany, access_token=access_token)
    allow = (os.getenv("SHOWCASE_ASSET_HOST_ALLOWLIST") or "").strip() or None
    err, _ctx, rows, _dbg = _fetch_pictures_common(
        idcompany=company_id,
        idcompany_item=idcompany_item,
        allow=allow,
        request_id=rid,
        want_client_debug=False,
    )
    if err:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "showcase_pictures_unavailable",
                "message": "Could not load item pictures.",
                "request_id": rid,
            },
        )
    match = next((r for r in rows if int(r["idcompany_item_pictures"]) == idcompany_item_pictures), None)
    if not match:
        raise HTTPException(
            status_code=400,
            detail={"error": "unknown_picture", "message": "Picture id is not attached to this item."},
        )
    fetch_urls = _artwork_fetch_urls_from_row(match)
    if not fetch_urls:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "showcase_picture_url_missing",
                "message": "Picture row has no resolvable asset URL (check MP_ASSET_CDN_BASE / picture / server_path).",
                "request_id": rid,
            },
        )
    max_mb = int(os.getenv("SHOWCASE_IMAGE_PROXY_MAX_MB", "25"))
    max_bytes = max(1, max_mb) * 1024 * 1024
    timeout_s = float(os.getenv("SHOWCASE_IMAGE_FETCH_TIMEOUT_S", "30"))
    try:
        body, content_type = fetch_remote_image_bytes_first_available(
            fetch_urls, timeout_s=timeout_s, max_bytes=max_bytes
        )
    except HTTPError as e:
        raise HTTPException(
            status_code=502,
            detail={"error": "upstream_image_http", "status": getattr(e, "code", None), "request_id": rid},
        ) from e
    except URLError as e:
        raise HTTPException(
            status_code=502,
            detail={"error": "upstream_image_failed", "message": str(e.reason)[:500], "request_id": rid},
        ) from e
    except OSError as e:
        raise HTTPException(
            status_code=502,
            detail={"error": "upstream_image_failed", "message": str(e)[:500], "request_id": rid},
        ) from e
    return Response(
        content=body,
        media_type=content_type or "application/octet-stream",
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.get("/scene-backdrops/{scene_id}.png")
def get_packaged_scene_backdrop(scene_id: str) -> FileResponse:
    """Public packaged room plate (no auth). Used by GET /scenes preview_asset_url and compositor."""
    if not _showcase_globally_enabled():
        raise HTTPException(status_code=404, detail={"error": "showcase_disabled"})
    p = packaged_scene_backdrop_path(scene_id)
    if p is None:
        raise HTTPException(status_code=404, detail={"error": "scene_backdrop_not_found"})
    return FileResponse(
        path=p,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@router.get("/scenes", response_model=ScenesResponse)
def get_scenes(
    request: Request,
    idcompany: int = Query(..., ge=1),
    access_token: str | None = None,
) -> ScenesResponse:
    if not _showcase_globally_enabled():
        raise HTTPException(status_code=404, detail={"error": "showcase_disabled"})
    _resolve_idcompany(req_idcompany=idcompany, access_token=access_token)
    pipeline_version, scenes = load_scene_manifest()
    base = _public_api_base(request)
    enriched: list[SceneInfo] = []
    for s in scenes:
        d = s.model_dump()
        existing = (d.get("preview_asset_url") or "").strip()
        if not existing and packaged_scene_backdrop_path(s.scene_id) is not None:
            d["preview_asset_url"] = f"{base}/showcase/scene-backdrops/{s.scene_id}.png"
        enriched.append(SceneInfo.model_validate(d))
    return ScenesResponse(pipeline_version=pipeline_version, scenes=enriched)


@router.post("/options", response_model=ShowcaseOptionsResponse)
def post_showcase_options(req: ShowcaseOptionsRequest) -> ShowcaseOptionsResponse:
    if not _showcase_globally_enabled():
        raise HTTPException(status_code=404, detail={"error": "showcase_disabled"})
    rid = str(uuid.uuid4())
    resolved = _resolve_idcompany(req_idcompany=req.idcompany, access_token=req.access_token)
    allow = (os.getenv("SHOWCASE_ASSET_HOST_ALLOWLIST") or "").strip() or None
    eff_debug = _showcase_client_debug_effective(req.debug, req.access_token)
    err, ctx, rows, dbg = _fetch_pictures_common(
        idcompany=resolved,
        idcompany_item=req.idcompany_item,
        allow=allow,
        request_id=rid,
        want_client_debug=eff_debug,
    )
    if err:
        detail: dict = {
            "error": "showcase_pictures_unavailable",
            "message": "Could not load item pictures.",
            "request_id": rid,
        }
        if _expose_debug_in_error(dbg, requested=req.debug, access_token=req.access_token):
            detail["debug"] = dbg
        raise HTTPException(status_code=503, detail=detail)
    picture_ids = [int(r["idcompany_item_pictures"]) for r in rows]
    if req.idcompany_item_pictures is not None and req.idcompany_item_pictures not in picture_ids:
        raise HTTPException(
            status_code=400,
            detail={"error": "unknown_picture", "message": "Picture id is not attached to this item."},
        )
    if req.idcompany_item_pictures is not None:
        picture_ids = [req.idcompany_item_pictures]

    _, scenes = load_scene_manifest()
    payload = build_options_payload(
        item_title=ctx.item_title,
        edition_label=ctx.edition_label,
        artist_display=ctx.artist_display,
        category_label=ctx.category_label,
        medium_label=ctx.medium_label,
        picture_ids=picture_ids,
        scenes=scenes,
    )
    rec = payload.get("recommended_scene_ids") or []
    rec_ids = [str(x) for x in rec if isinstance(x, str)]
    return ShowcaseOptionsResponse(
        idcompany=resolved,
        idcompany_item=req.idcompany_item,
        category_label=payload.get("category_label"),
        medium_label=payload.get("medium_label"),
        recommended_scene_ids=rec_ids,
        frame_style=str(payload.get("frame_style")) if payload.get("frame_style") else None,
        lighting=str(payload.get("lighting")) if payload.get("lighting") else None,
        placement=str(payload.get("placement")) if payload.get("placement") else None,
        suitable_picture_ids=payload.get("suitable_picture_ids") or [],
        presentation_source=str(payload.get("presentation_source")) if payload.get("presentation_source") else None,
        notes=str(payload.get("notes")) if payload.get("notes") else None,
        debug=_attach_response_debug(dbg, want_client_debug=eff_debug),
    )


@router.post("/studio/analyze", response_model=ShowcaseStudioAnalyzeResponse)
def post_showcase_studio_analyze(req: ShowcaseStudioAnalyzeRequest) -> ShowcaseStudioAnalyzeResponse:
    """Phase 1: artwork kind, placement, frame/lighting suggestions, style ↔ room matching (rules only)."""
    if not _showcase_globally_enabled():
        raise HTTPException(status_code=404, detail={"error": "showcase_disabled"})
    rid = str(uuid.uuid4())
    resolved = _resolve_idcompany(req_idcompany=req.idcompany, access_token=req.access_token)
    allow = (os.getenv("SHOWCASE_ASSET_HOST_ALLOWLIST") or "").strip() or None
    eff_debug = _showcase_client_debug_effective(req.debug, req.access_token)
    err, ctx, rows, dbg = _fetch_pictures_common(
        idcompany=resolved,
        idcompany_item=req.idcompany_item,
        allow=allow,
        request_id=rid,
        want_client_debug=eff_debug,
    )
    if err:
        detail: dict = {
            "error": "showcase_pictures_unavailable",
            "message": "Could not load item pictures.",
            "request_id": rid,
        }
        if _expose_debug_in_error(dbg, requested=req.debug, access_token=req.access_token):
            detail["debug"] = dbg
        raise HTTPException(status_code=503, detail=detail)
    picture_ids = [int(r["idcompany_item_pictures"]) for r in rows]
    if req.idcompany_item_pictures is not None and req.idcompany_item_pictures not in picture_ids:
        raise HTTPException(
            status_code=400,
            detail={"error": "unknown_picture", "message": "Picture id is not attached to this item."},
        )
    _, scenes = load_scene_manifest()
    analyzed = analyze_artwork_for_showcase(
        item_title=ctx.item_title,
        category_label=ctx.category_label,
        medium_label=ctx.medium_label,
        scenes=scenes,
    )
    return ShowcaseStudioAnalyzeResponse(
        idcompany=resolved,
        idcompany_item=req.idcompany_item,
        artwork_kind=str(analyzed["artwork_kind"]),
        detected_placement=str(analyzed["detected_placement"]),
        frame_suggestions=list(analyzed["frame_suggestions"]),
        lighting_suggestions=list(analyzed["lighting_suggestions"]),
        style_matches=list(analyzed["style_matches"]),
        scene_ranking=list(analyzed["scene_ranking"]),
        notes=str(analyzed["notes"]) if analyzed.get("notes") else None,
        debug=_attach_response_debug(dbg, want_client_debug=eff_debug),
    )


@router.post("/studio/batch-render", response_model=ShowcaseBatchRenderResponse)
def post_showcase_batch_render(req: ShowcaseBatchRenderRequest, request: Request) -> ShowcaseBatchRenderResponse:
    """Phase 1: multi-scene / batch PNG generation (one artwork fetch, multiple scene plates)."""
    if not _showcase_globally_enabled():
        raise HTTPException(status_code=404, detail={"error": "showcase_disabled"})
    if not _showcase_compositor_enabled():
        raise HTTPException(
            status_code=400,
            detail={"error": "compositor_disabled", "message": "Enable SHOWCASE_COMPOSITOR_ENABLED for batch renders."},
        )
    rid = str(uuid.uuid4())
    company_id = _resolve_idcompany(req_idcompany=req.idcompany, access_token=req.access_token)
    allow = (os.getenv("SHOWCASE_ASSET_HOST_ALLOWLIST") or "").strip() or None
    eff_debug = _showcase_client_debug_effective(req.debug, req.access_token)
    err, _ctx, rows, dbg = _fetch_pictures_common(
        idcompany=company_id,
        idcompany_item=req.idcompany_item,
        allow=allow,
        request_id=rid,
        want_client_debug=eff_debug,
    )
    if err:
        detail: dict = {
            "error": "showcase_pictures_unavailable",
            "message": "Could not load item pictures.",
            "request_id": rid,
        }
        if _expose_debug_in_error(dbg, requested=req.debug, access_token=req.access_token):
            detail["debug"] = dbg
        raise HTTPException(status_code=503, detail=detail)
    match = next((r for r in rows if int(r["idcompany_item_pictures"]) == req.idcompany_item_pictures), None)
    if not match:
        raise HTTPException(
            status_code=400,
            detail={"error": "unknown_picture", "message": "Picture id is not attached to this item."},
        )
    fetch_urls = _artwork_fetch_urls_from_row(match)
    artwork_url = str(match.get("resolved_url") or "").strip() or (fetch_urls[0] if fetch_urls else "")
    if not fetch_urls or not artwork_url:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "showcase_picture_url_missing",
                "message": "Picture row has no resolvable asset URL.",
                "request_id": rid,
            },
        )
    pipeline_version, scenes = load_scene_manifest()
    scene_map = {s.scene_id: s for s in scenes}
    for sid in req.scene_ids:
        if sid not in scene_map:
            raise HTTPException(
                status_code=400,
                detail={"error": "unknown_scene", "message": f"scene_id {sid!r} is not in the manifest."},
            )
    max_mb = int(os.getenv("SHOWCASE_IMAGE_PROXY_MAX_MB", "25"))
    max_bytes = max(1, max_mb) * 1024 * 1024
    timeout_s = float(os.getenv("SHOWCASE_IMAGE_FETCH_TIMEOUT_S", "30"))
    params = _composite_params_from_batch(req)
    try:
        art = load_artwork_rgba_first_available(
            fetch_urls,
            timeout_s=timeout_s,
            max_fetch_bytes=max_bytes,
            max_art_input_dim=2800,
            params=params,
        )
    except OSError as e:
        logger.warning("showcase batch: artwork fetch failed: %s", e)
        raise HTTPException(
            status_code=502,
            detail={"error": "compositor_failed", "message": str(e)[:500], "request_id": rid},
        ) from e
    except Exception as e:
        logger.exception("showcase batch: artwork fetch failed")
        raise HTTPException(
            status_code=502,
            detail={"error": "compositor_failed", "message": str(e)[:500], "request_id": rid},
        ) from e
    c = get_compositor_cache()
    base = _public_api_base(request)
    q = f"idcompany={company_id}"
    if req.access_token:
        q += f"&access_token={quote(req.access_token, safe='')}"
    items: list[ShowcaseBatchRenderItem] = []
    for sid in req.scene_ids:
        scene_row = scene_map[sid]
        ck = build_render_cache_key(
            idcompany_item_pictures=req.idcompany_item_pictures,
            scene_id=sid,
            pipeline_version=pipeline_version,
            frame_style=req.frame_style,
            frame_finish=req.frame_finish,
            frame_profile=req.frame_profile,
            lighting=req.lighting,
            placement=req.placement,
            layout_variant=req.layout_variant,
            cutout=req.cutout,
            physical_width_cm=req.physical_width_cm,
            physical_height_cm=req.physical_height_cm,
            wall_width_cm=req.wall_width_cm,
            wall_span_cm=req.wall_span_cm,
            focal_wall_rect=req.focal_wall_rect,
            placement_quad=req.placement_quad,
            art_spotlight=req.art_spotlight,
        )
        png = c.get(ck)
        if not png:
            try:
                png = run_pixel_composite_from_art(
                    art,
                    scene_row,
                    timeout_s=timeout_s,
                    max_fetch_bytes=max_bytes,
                    params=params,
                )
            except OSError as e:
                logger.warning("showcase batch compositor failed %s: %s", sid, e)
                raise HTTPException(
                    status_code=502,
                    detail={"error": "compositor_failed", "message": str(e)[:500], "request_id": rid},
                ) from e
            except Exception as e:
                logger.exception("showcase batch compositor error")
                raise HTTPException(
                    status_code=502,
                    detail={"error": "compositor_failed", "message": str(e)[:500], "request_id": rid},
                ) from e
            c.put(ck, png)
        preview_api_url = f"{base}/showcase/render/{ck}/preview?{q}"
        items.append(
            ShowcaseBatchRenderItem(
                scene_id=sid,
                cache_key=ck,
                preview_url=preview_api_url,
                output_mode="composited",
                compositor_status="ok",
            )
        )
    return ShowcaseBatchRenderResponse(
        pipeline_version=pipeline_version,
        items=items,
        debug=_attach_response_debug(dbg, want_client_debug=eff_debug),
    )


@router.get("/render/{cache_key}/preview")
def get_composited_render_preview(
    cache_key: str,
    idcompany: int = Query(..., ge=1),
    access_token: str | None = None,
) -> Response:
    """PNG bytes from in-memory cache; populate cache via POST /showcase/render with compositor enabled."""
    if not _showcase_globally_enabled():
        raise HTTPException(status_code=404, detail={"error": "showcase_disabled"})
    if not _showcase_compositor_enabled():
        raise HTTPException(status_code=404, detail={"error": "compositor_disabled"})
    _resolve_idcompany(req_idcompany=idcompany, access_token=access_token)
    data = get_compositor_cache().get(cache_key)
    if not data:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "preview_not_cached",
                "message": "Run POST /showcase/render for this picture and scene first, or cache expired (single-worker only).",
            },
        )
    return Response(
        content=data,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=120"},
    )


@router.post("/render", response_model=ShowcaseRenderResponse)
def post_showcase_render(req: ShowcaseRenderRequest, request: Request) -> ShowcaseRenderResponse:
    if not _showcase_globally_enabled():
        raise HTTPException(status_code=404, detail={"error": "showcase_disabled"})
    rid = str(uuid.uuid4())
    company_id = _resolve_idcompany(req_idcompany=req.idcompany, access_token=req.access_token)
    allow = (os.getenv("SHOWCASE_ASSET_HOST_ALLOWLIST") or "").strip() or None
    eff_debug = _showcase_client_debug_effective(req.debug, req.access_token)
    err, _ctx, rows, dbg = _fetch_pictures_common(
        idcompany=company_id,
        idcompany_item=req.idcompany_item,
        allow=allow,
        request_id=rid,
        want_client_debug=eff_debug,
    )
    if err:
        detail: dict = {
            "error": "showcase_pictures_unavailable",
            "message": "Could not load item pictures.",
            "request_id": rid,
        }
        if _expose_debug_in_error(dbg, requested=req.debug, access_token=req.access_token):
            detail["debug"] = dbg
        raise HTTPException(status_code=503, detail=detail)
    match = next((r for r in rows if int(r["idcompany_item_pictures"]) == req.idcompany_item_pictures), None)
    if not match:
        raise HTTPException(
            status_code=400,
            detail={"error": "unknown_picture", "message": "Picture id is not attached to this item."},
        )
    fetch_urls = _artwork_fetch_urls_from_row(match)
    artwork_url = str(match.get("resolved_url") or "").strip() or (fetch_urls[0] if fetch_urls else "")
    if not fetch_urls or not artwork_url:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "showcase_picture_url_missing",
                "message": "Picture row has no resolvable asset URL (check MP_ASSET_CDN_BASE / picture / server_path).",
                "request_id": rid,
            },
        )
    pipeline_version, scenes = load_scene_manifest()
    scene_ids = {s.scene_id for s in scenes}
    if req.scene_id not in scene_ids:
        raise HTTPException(
            status_code=400,
            detail={"error": "unknown_scene", "message": "scene_id is not in the current library manifest."},
        )
    scene_row = next(s for s in scenes if s.scene_id == req.scene_id)
    params = _composite_params_from_render(req)

    if _showcase_compositor_enabled():
        ck = build_render_cache_key(
            idcompany_item_pictures=req.idcompany_item_pictures,
            scene_id=req.scene_id,
            pipeline_version=pipeline_version,
            frame_style=req.frame_style,
            frame_finish=req.frame_finish,
            frame_profile=req.frame_profile,
            lighting=req.lighting,
            placement=req.placement,
            layout_variant=req.layout_variant,
            cutout=req.cutout,
            physical_width_cm=req.physical_width_cm,
            physical_height_cm=req.physical_height_cm,
            wall_width_cm=req.wall_width_cm,
            wall_span_cm=req.wall_span_cm,
            focal_wall_rect=req.focal_wall_rect,
            placement_quad=req.placement_quad,
            art_spotlight=req.art_spotlight,
        )
        c = get_compositor_cache()
        png = c.get(ck)
        if not png:
            max_mb = int(os.getenv("SHOWCASE_IMAGE_PROXY_MAX_MB", "25"))
            max_bytes = max(1, max_mb) * 1024 * 1024
            timeout_s = float(os.getenv("SHOWCASE_IMAGE_FETCH_TIMEOUT_S", "30"))
            try:
                png = run_pixel_composite(
                    artwork_urls=fetch_urls,
                    scene=scene_row,
                    timeout_s=timeout_s,
                    max_fetch_bytes=max_bytes,
                    params=params,
                )
            except OSError as e:
                logger.warning("showcase compositor failed: %s", e)
                raise HTTPException(
                    status_code=502,
                    detail={
                        "error": "compositor_failed",
                        "message": str(e)[:500],
                        "request_id": rid,
                    },
                ) from e
            except Exception as e:
                logger.exception("showcase compositor error")
                raise HTTPException(
                    status_code=502,
                    detail={
                        "error": "compositor_failed",
                        "message": str(e)[:500],
                        "request_id": rid,
                    },
                ) from e
            c.put(ck, png)
        base = _public_api_base(request)
        q = f"idcompany={company_id}"
        if req.access_token:
            q += f"&access_token={quote(req.access_token, safe='')}"
        preview_api_url = f"{base}/showcase/render/{ck}/preview?{q}"
        raw = composited_render_result(
            preview_api_url=preview_api_url,
            cache_key=ck,
            scene_id=req.scene_id,
            pipeline_version=pipeline_version,
            frame_style=req.frame_style,
            lighting=req.lighting,
            placement=req.placement,
        )
    else:
        raw = stub_render_result(
            resolved_artwork_url=artwork_url,
            idcompany_item_pictures=req.idcompany_item_pictures,
            scene_id=req.scene_id,
            pipeline_version=pipeline_version,
            frame_style=req.frame_style,
            lighting=req.lighting,
            placement=req.placement,
            frame_finish=req.frame_finish,
            frame_profile=req.frame_profile,
            layout_variant=req.layout_variant,
            cutout=req.cutout,
            physical_width_cm=req.physical_width_cm,
            physical_height_cm=req.physical_height_cm,
            wall_width_cm=req.wall_width_cm,
            wall_span_cm=req.wall_span_cm,
            focal_wall_rect=req.focal_wall_rect,
            placement_quad=req.placement_quad,
            art_spotlight=req.art_spotlight,
        )
    out = ShowcaseRenderResponse.model_validate(raw)
    if dbg and (_showcase_client_debug_effective(req.debug, req.access_token) or showcase_debug_log_enabled()):
        out = out.model_copy(update={"debug": dbg})
    return out


@router.post("/share", response_model=ShowcaseShareResponse)
def post_showcase_share(req: ShowcaseShareRequest) -> ShowcaseShareResponse:
    if not _showcase_globally_enabled():
        raise HTTPException(status_code=404, detail={"error": "showcase_disabled"})
    _resolve_idcompany(req_idcompany=req.idcompany, access_token=req.access_token)
    return ShowcaseShareResponse(
        enabled=False,
        message="Customer share links and magic tokens are planned for a later release.",
        share_url=None,
    )
