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
}

export interface ShowcaseSceneInfo {
  scene_id: string;
  label: string;
  description?: string | null;
  preview_asset_url?: string | null;
  qa_status?: string | null;
  tags?: string[];
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
}

export interface ShowcaseRenderResponse {
  output_mode: string;
  pipeline_version: string;
  cache_key: string;
  preview_url: string;
  scene_id: string;
  frame_style?: string | null;
  lighting?: string | null;
  placement?: string | null;
  compositor_status: string;
}

export interface ShowcaseShareResponse {
  enabled: boolean;
  message: string;
  share_url?: string | null;
}
