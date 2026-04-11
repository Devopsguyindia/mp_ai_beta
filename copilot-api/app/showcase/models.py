from __future__ import annotations

from pydantic import BaseModel, Field


class ItemPictureRow(BaseModel):
    idcompany_item_pictures: int
    idcompany_item: int
    picture: str
    server_path: str | None = None
    resolved_url: str
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


class SceneInfo(BaseModel):
    scene_id: str
    label: str
    description: str | None = None
    preview_asset_url: str | None = None
    qa_status: str | None = None
    tags: list[str] = Field(default_factory=list)


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


class ShowcaseRenderRequest(BaseModel):
    idcompany: int = Field(..., ge=1)
    access_token: str | None = None
    idcompany_item: int = Field(..., ge=1)
    idcompany_item_pictures: int = Field(..., ge=1)
    scene_id: str = Field(..., min_length=1, max_length=120)
    frame_style: str | None = Field(default=None, max_length=120)
    lighting: str | None = Field(default=None, max_length=120)
    placement: str | None = Field(default=None, max_length=120)


class ShowcaseRenderResponse(BaseModel):
    output_mode: str
    pipeline_version: str
    cache_key: str
    preview_url: str
    scene_id: str
    frame_style: str | None = None
    lighting: str | None = None
    placement: str | None = None
    compositor_status: str


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
