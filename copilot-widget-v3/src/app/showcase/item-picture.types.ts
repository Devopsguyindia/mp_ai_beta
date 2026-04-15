/** Types for Artwork showcase API (`/showcase/*`). Kept separate from V3 / insights. */

export interface ShowcasePictureRow {
  idcompany_item_pictures: number;
  idcompany_item: number;
  picture: string;
  server_path?: string | null;
  resolved_url: string;
  is_primary: number;
  rank: number;
  seq_no: number;
  thumbnail_url?: string | null;
}

export interface ShowcaseItemPicturesResponse {
  idcompany: number;
  idcompany_item: number;
  item_title?: string | null;
  artist_display?: string | null;
  edition_label?: string | null;
  item_edition_type?: number | null;
  category_label?: string | null;
  medium_label?: string | null;
  pipeline_version?: string | null;
  pictures: ShowcasePictureRow[];
  /** Present when ?debug=1 or server SHOWCASE_DEBUG_LOG=1 */
  debug?: Record<string, unknown> | null;
}

export interface ShowcaseSceneInfo {
  scene_id: string;
  label: string;
  description?: string | null;
  preview_asset_url?: string | null;
  qa_status?: string | null;
  tags?: string[];
  room_category?: string | null;
  interior_style?: string | null;
  placement_hint?: string | null;
  layout_index?: number;
  /** Normalized [left, top, right, bottom] on compositor canvas; art is placed inside this ROI. */
  focal_wall_rect?: [number, number, number, number] | null;
  /** Optional 4 corners [x,y] in [0,1], order TL, TR, BR, BL for perspective warp. */
  placement_quad?: [number, number][] | null;
}

export interface ShowcaseScenesResponse {
  pipeline_version: string;
  scenes: ShowcaseSceneInfo[];
}

export interface ShowcaseOptionsResponse {
  idcompany: number;
  idcompany_item: number;
  category_label?: string | null;
  medium_label?: string | null;
  recommended_scene_ids: string[];
  frame_style?: string | null;
  lighting?: string | null;
  placement?: string | null;
  suitable_picture_ids: number[];
  presentation_source?: string | null;
  notes?: string | null;
  debug?: Record<string, unknown> | null;
}

export interface ShowcaseStyleMatch {
  scene_id: string;
  label: string;
  score: number;
}

export interface ShowcaseStudioAnalyzeResponse {
  idcompany: number;
  idcompany_item: number;
  artwork_kind: string;
  detected_placement: string;
  frame_suggestions: string[];
  lighting_suggestions: string[];
  style_matches: ShowcaseStyleMatch[];
  scene_ranking: string[];
  notes?: string | null;
  debug?: Record<string, unknown> | null;
}

export interface ShowcaseBatchRenderItem {
  scene_id: string;
  cache_key: string;
  preview_url: string;
  output_mode: string;
  compositor_status: string;
}

export interface ShowcaseBatchRenderResponse {
  pipeline_version: string;
  items: ShowcaseBatchRenderItem[];
  debug?: Record<string, unknown> | null;
}

export interface ShowcaseRenderResponse {
  /** pass_through | composited */
  output_mode: string;
  pipeline_version: string;
  cache_key: string;
  preview_url: string;
  scene_id: string;
  frame_style?: string | null;
  lighting?: string | null;
  placement?: string | null;
  compositor_status: string;
  debug?: Record<string, unknown> | null;
}

export interface ShowcaseShareResponse {
  enabled: boolean;
  message: string;
  share_url?: string | null;
}

export interface ShowcaseSuggestionRender {
  frame_style: string;
  lighting: string;
  preview_url: string;
  output_mode: string;
}
