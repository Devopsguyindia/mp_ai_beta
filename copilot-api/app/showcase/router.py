from __future__ import annotations

import base64
import json
import os

from fastapi import APIRouter, HTTPException, Query

from .manifest_loader import load_scene_manifest
from .models import (
    ItemPictureRow,
    ItemPicturesResponse,
    ScenesResponse,
    ShowcaseOptionsRequest,
    ShowcaseOptionsResponse,
    ShowcaseRenderRequest,
    ShowcaseRenderResponse,
    ShowcaseShareRequest,
    ShowcaseShareResponse,
)
from .pictures_repo import fetch_item_pictures
from .presentation import build_options_payload
from .render_service import stub_render_result


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


router = APIRouter(prefix="/showcase", tags=["showcase"])


@router.get("/items/{idcompany_item}/pictures", response_model=ItemPicturesResponse)
def get_item_pictures(
    idcompany_item: int,
    idcompany: int = Query(..., ge=1),
    access_token: str | None = None,
) -> ItemPicturesResponse:
    if not _showcase_globally_enabled():
        raise HTTPException(status_code=404, detail={"error": "showcase_disabled"})
    resolved = _resolve_idcompany(req_idcompany=idcompany, access_token=access_token)
    allow = (os.getenv("SHOWCASE_ASSET_HOST_ALLOWLIST") or "").strip() or None
    pipeline_version, _ = load_scene_manifest()
    err, ctx, rows = fetch_item_pictures(
        idcompany=resolved,
        idcompany_item=idcompany_item,
        max_rows=int(os.getenv("SHOWCASE_PICTURES_MAX_ROWS", "50")),
        timeout_ms=int(os.getenv("MYSQL_QUERY_TIMEOUT_MS", "8000")),
        asset_allowlist=allow,
    )
    if err:
        raise HTTPException(
            status_code=503,
            detail={"error": "showcase_pictures_unavailable", "message": "Could not load item pictures."},
        )
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
    )


@router.get("/scenes", response_model=ScenesResponse)
def get_scenes(
    idcompany: int = Query(..., ge=1),
    access_token: str | None = None,
) -> ScenesResponse:
    if not _showcase_globally_enabled():
        raise HTTPException(status_code=404, detail={"error": "showcase_disabled"})
    _resolve_idcompany(req_idcompany=idcompany, access_token=access_token)
    pipeline_version, scenes = load_scene_manifest()
    return ScenesResponse(pipeline_version=pipeline_version, scenes=scenes)


@router.post("/options", response_model=ShowcaseOptionsResponse)
def post_showcase_options(req: ShowcaseOptionsRequest) -> ShowcaseOptionsResponse:
    if not _showcase_globally_enabled():
        raise HTTPException(status_code=404, detail={"error": "showcase_disabled"})
    resolved = _resolve_idcompany(req_idcompany=req.idcompany, access_token=req.access_token)
    allow = (os.getenv("SHOWCASE_ASSET_HOST_ALLOWLIST") or "").strip() or None
    err, ctx, rows = fetch_item_pictures(
        idcompany=resolved,
        idcompany_item=req.idcompany_item,
        max_rows=int(os.getenv("SHOWCASE_PICTURES_MAX_ROWS", "50")),
        timeout_ms=int(os.getenv("MYSQL_QUERY_TIMEOUT_MS", "8000")),
        asset_allowlist=allow,
    )
    if err:
        raise HTTPException(
            status_code=503,
            detail={"error": "showcase_pictures_unavailable", "message": "Could not load item pictures."},
        )
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
    )


@router.post("/render", response_model=ShowcaseRenderResponse)
def post_showcase_render(req: ShowcaseRenderRequest) -> ShowcaseRenderResponse:
    if not _showcase_globally_enabled():
        raise HTTPException(status_code=404, detail={"error": "showcase_disabled"})
    resolved = _resolve_idcompany(req_idcompany=req.idcompany, access_token=req.access_token)
    allow = (os.getenv("SHOWCASE_ASSET_HOST_ALLOWLIST") or "").strip() or None
    err, _ctx, rows = fetch_item_pictures(
        idcompany=resolved,
        idcompany_item=req.idcompany_item,
        max_rows=int(os.getenv("SHOWCASE_PICTURES_MAX_ROWS", "50")),
        timeout_ms=int(os.getenv("MYSQL_QUERY_TIMEOUT_MS", "8000")),
        asset_allowlist=allow,
    )
    if err:
        raise HTTPException(
            status_code=503,
            detail={"error": "showcase_pictures_unavailable", "message": "Could not load item pictures."},
        )
    match = next((r for r in rows if int(r["idcompany_item_pictures"]) == req.idcompany_item_pictures), None)
    if not match:
        raise HTTPException(
            status_code=400,
            detail={"error": "unknown_picture", "message": "Picture id is not attached to this item."},
        )
    pipeline_version, scenes = load_scene_manifest()
    scene_ids = {s.scene_id for s in scenes}
    if req.scene_id not in scene_ids:
        raise HTTPException(
            status_code=400,
            detail={"error": "unknown_scene", "message": "scene_id is not in the current library manifest."},
        )
    raw = stub_render_result(
        resolved_artwork_url=str(match["resolved_url"]),
        idcompany_item_pictures=req.idcompany_item_pictures,
        scene_id=req.scene_id,
        pipeline_version=pipeline_version,
        frame_style=req.frame_style,
        lighting=req.lighting,
        placement=req.placement,
    )
    return ShowcaseRenderResponse.model_validate(raw)


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
