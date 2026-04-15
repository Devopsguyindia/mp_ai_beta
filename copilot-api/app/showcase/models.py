from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from .compositor_geometry import (
    parse_focal_rect_from_json,
    parse_quad_from_json,
    valid_focal_rect,
    valid_placement_quad,
)


class ItemPictureRow(BaseModel):
    """Picture row; DB reads only idcompany_item_pictures + idcompany_item + picture + server_path (+ resolved_url)."""

    idcompany_item_pictures: int
    idcompany_item: int
    picture: str
    server_path: str | None = None
    resolved_url: str
    # Not loaded from DB; kept for API compatibility (always defaults).
    is_primary: int = 0
    rank: int = 0
    seq_no: int = 0
    thumbnail_url: str | None = None


class ItemPicturesResponse(BaseModel):
    idcompany: int
    idcompany_item: int
    item_title: str | None = None
    artist_display: str | None = None
    edition_label: str | None = None
    item_edition_type: int | None = None
    category_label: str | None = None
    medium_label: str | None = None
    pipeline_version: str | None = Field(
        default=None,
        description="Scene library / render cache grouping from manifest.",
    )
    pictures: list[ItemPictureRow]
    debug: dict[str, Any] | None = Field(
        default=None,
        description="Populated when ?debug=1 or SHOWCASE_DEBUG_LOG=1 (server logs either way when env set).",
    )


class SceneInfo(BaseModel):
    scene_id: str
    label: str
    description: str | None = None
    preview_asset_url: str | None = None
    qa_status: str | None = None
    tags: list[str] = Field(default_factory=list)
    room_category: str | None = Field(default=None, description="e.g. gallery, living, office, hotel, corridor")
    interior_style: str | None = Field(default=None, description="e.g. warm, modern, neutral — used for style matching")
    placement_hint: str | None = Field(default=None, description="Optional hint: wall_eye_level, pedestal_center")
    layout_index: int = Field(default=0, description="Default layout variant index for this scene")
    focal_wall_rect: tuple[float, float, float, float] | None = Field(
        default=None,
        description="Optional [left, top, right, bottom] in normalized [0,1] canvas coords for art placement region.",
    )
    placement_quad: list[tuple[float, float]] | None = Field(
        default=None,
        description="Optional 4 corners [x,y] each in [0,1], order top-left, top-right, bottom-right, bottom-left.",
    )
    eye_level_fraction: float = Field(
        default=0.48,
        ge=0.0,
        le=1.0,
        description="Vertical centre of artwork as fraction of focal rect height (0=top,1=bottom). 0.48 = eye level.",
    )
    wall_span_cm: float | None = Field(
        default=None,
        gt=0,
        description="Real-world width (cm) of the focal wall region; pairs with physical_width_cm for accurate scale.",
    )

    @field_validator("focal_wall_rect", mode="before")
    @classmethod
    def _validate_focal_wall_rect(cls, v: object) -> tuple[float, float, float, float] | None:
        if v is None:
            return None
        t = (
            tuple(float(x) for x in v)
            if isinstance(v, (list, tuple)) and len(v) == 4
            else parse_focal_rect_from_json(v)
        )
        if t is None or not valid_focal_rect(t):
            raise ValueError("focal_wall_rect must be [left,top,right,bottom] with 0<=l<r<=1, 0<=t<b<=1")
        return t

    @field_validator("placement_quad", mode="before")
    @classmethod
    def _validate_placement_quad(cls, v: object) -> list[tuple[float, float]] | None:
        if v is None:
            return None
        q = parse_quad_from_json(v)
        if q is None or not valid_placement_quad(q):
            raise ValueError("placement_quad must be 4 non-degenerate [x,y] pairs in [0,1]")
        return q


class ScenesResponse(BaseModel):
    pipeline_version: str
    scenes: list[SceneInfo]


class ShowcaseOptionsRequest(BaseModel):
    idcompany: int = Field(..., ge=1)
    access_token: str | None = None
    idcompany_item: int = Field(..., ge=1)
    idcompany_item_pictures: int | None = Field(
        default=None,
        description="When set, narrows presentation to one image.",
    )
    debug: bool = Field(default=False, description="Include pictures fetch debug block in response.")


class ShowcaseOptionsResponse(BaseModel):
    idcompany: int
    idcompany_item: int
    category_label: str | None = None
    medium_label: str | None = None
    recommended_scene_ids: list[str] = Field(default_factory=list)
    frame_style: str | None = None
    lighting: str | None = None
    placement: str | None = None
    suitable_picture_ids: list[int] = Field(default_factory=list)
    presentation_source: str | None = None
    notes: str | None = None
    debug: dict[str, Any] | None = None


class ShowcaseRenderRequest(BaseModel):
    idcompany: int = Field(..., ge=1)
    access_token: str | None = None
    idcompany_item: int = Field(..., ge=1)
    idcompany_item_pictures: int = Field(..., ge=1)
    scene_id: str = Field(..., min_length=1, max_length=120)
    frame_style: str | None = Field(default=None, max_length=120)
    frame_finish: str | None = Field(
        default=None,
        max_length=64,
        description="Wood/modern finish preset for wall art; ignored on pedestal / 3D scenes.",
    )
    frame_profile: str | None = Field(
        default=None,
        max_length=16,
        description="thick | thin — moulding width for frame_finish.",
    )
    lighting: str | None = Field(default=None, max_length=120)
    placement: str | None = Field(default=None, max_length=120)
    layout_variant: int | None = Field(
        default=None,
        description="Explicit layout 0–7; omit to use scene layout_index from manifest.",
    )
    cutout: bool = Field(default=False, description="Background removal when SHOWCASE_CUTOUT_ENABLED + rembg available")
    physical_width_cm: float | None = Field(default=None, gt=0, description="Artwork width for wall scale")
    physical_height_cm: float | None = Field(default=None, gt=0, description="Optional height for aspect-aware scale")
    wall_width_cm: float | None = Field(default=None, gt=0, description="View wall width; default from env")
    wall_span_cm: float | None = Field(
        default=None,
        gt=0,
        description="Real-world width (cm) of the focal wall region; pairs with physical_width_cm for accurate scale.",
    )
    focal_wall_rect: tuple[float, float, float, float] | None = Field(
        default=None,
        description="Override scene focal rect [l,t,r,b] normalized; omit to use manifest.",
    )
    placement_quad: list[tuple[float, float]] | None = Field(
        default=None,
        description="Override perspective quad (4 corners normalized); omit to use manifest.",
    )
    art_spotlight: str | None = Field(
        default=None,
        max_length=32,
        description="Directed highlight on artwork+mat: off, top, bottom, left, right, lr, tb, quad.",
    )
    debug: bool = Field(default=False, description="Include pictures fetch debug block in response.")

    @field_validator("layout_variant")
    @classmethod
    def _layout_variant_clamp(cls, v: int | None) -> int | None:
        if v is None:
            return None
        return max(0, min(7, v))

    @field_validator("focal_wall_rect", mode="before")
    @classmethod
    def _v_render_focal(cls, v: object) -> tuple[float, float, float, float] | None:
        if v is None:
            return None
        t = (
            tuple(float(x) for x in v)
            if isinstance(v, (list, tuple)) and len(v) == 4
            else parse_focal_rect_from_json(v)
        )
        if t is None or not valid_focal_rect(t):
            raise ValueError("focal_wall_rect must be [left,top,right,bottom] with valid range")
        return t

    @field_validator("placement_quad", mode="before")
    @classmethod
    def _v_render_quad(cls, v: object) -> list[tuple[float, float]] | None:
        if v is None:
            return None
        q = parse_quad_from_json(v)
        if q is None or not valid_placement_quad(q):
            raise ValueError("placement_quad must be 4 valid [x,y] pairs in [0,1]")
        return q


class ShowcaseStudioAnalyzeRequest(BaseModel):
    idcompany: int = Field(..., ge=1)
    access_token: str | None = None
    idcompany_item: int = Field(..., ge=1)
    idcompany_item_pictures: int | None = Field(default=None, description="Narrow to one image; else uses all for context")
    debug: bool = Field(default=False)


class ShowcaseStudioAnalyzeResponse(BaseModel):
    idcompany: int
    idcompany_item: int
    artwork_kind: str
    detected_placement: str
    frame_suggestions: list[str]
    lighting_suggestions: list[str]
    style_matches: list[dict[str, Any]]
    scene_ranking: list[str]
    notes: str | None = None
    debug: dict[str, Any] | None = None


class ShowcaseBatchRenderItem(BaseModel):
    scene_id: str
    cache_key: str
    preview_url: str
    output_mode: str
    compositor_status: str


class ShowcaseBatchRenderRequest(BaseModel):
    idcompany: int = Field(..., ge=1)
    access_token: str | None = None
    idcompany_item: int = Field(..., ge=1)
    idcompany_item_pictures: int = Field(..., ge=1)
    scene_ids: list[str] = Field(..., min_length=1, max_length=32)
    frame_style: str | None = Field(default=None, max_length=120)
    frame_finish: str | None = Field(default=None, max_length=64)
    frame_profile: str | None = Field(default=None, max_length=16)
    lighting: str | None = Field(default=None, max_length=120)
    placement: str | None = Field(default=None, max_length=120)
    layout_variant: int | None = Field(default=None, description="0–7; omit for scene default")
    cutout: bool = False
    physical_width_cm: float | None = Field(default=None, gt=0)
    physical_height_cm: float | None = Field(default=None, gt=0)
    wall_width_cm: float | None = Field(default=None, gt=0)
    wall_span_cm: float | None = Field(default=None, gt=0)
    focal_wall_rect: tuple[float, float, float, float] | None = Field(default=None)
    placement_quad: list[tuple[float, float]] | None = Field(default=None)
    art_spotlight: str | None = Field(
        default=None,
        max_length=32,
        description="Directed highlight on artwork: off, top, bottom, left, right, lr, tb, quad.",
    )
    debug: bool = Field(default=False)

    @field_validator("layout_variant")
    @classmethod
    def _layout_variant_clamp_batch(cls, v: int | None) -> int | None:
        if v is None:
            return None
        return max(0, min(7, v))

    @field_validator("focal_wall_rect", mode="before")
    @classmethod
    def _v_batch_focal(cls, v: object) -> tuple[float, float, float, float] | None:
        if v is None:
            return None
        t = (
            tuple(float(x) for x in v)
            if isinstance(v, (list, tuple)) and len(v) == 4
            else parse_focal_rect_from_json(v)
        )
        if t is None or not valid_focal_rect(t):
            raise ValueError("invalid focal_wall_rect")
        return t

    @field_validator("placement_quad", mode="before")
    @classmethod
    def _v_batch_quad(cls, v: object) -> list[tuple[float, float]] | None:
        if v is None:
            return None
        q = parse_quad_from_json(v)
        if q is None or not valid_placement_quad(q):
            raise ValueError("invalid placement_quad")
        return q


class ShowcaseBatchRenderResponse(BaseModel):
    pipeline_version: str
    items: list[ShowcaseBatchRenderItem]
    debug: dict[str, Any] | None = None


class ShowcaseRenderResponse(BaseModel):
    output_mode: str = Field(description="pass_through (raw artwork URL) or composited (API PNG preview URL).")
    pipeline_version: str
    cache_key: str
    preview_url: str
    scene_id: str
    frame_style: str | None = None
    lighting: str | None = None
    placement: str | None = None
    compositor_status: str
    debug: dict[str, Any] | None = None


class ShowcaseShareRequest(BaseModel):
    idcompany: int = Field(..., ge=1)
    access_token: str | None = None
    idcompany_item: int = Field(..., ge=1)
    idcompany_item_pictures: int | None = None
    scene_id: str | None = None


class ShowcaseShareResponse(BaseModel):
    enabled: bool = False
    message: str
    share_url: str | None = None
