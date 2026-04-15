import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import {
  ShowcaseBatchRenderResponse,
  ShowcaseItemPicturesResponse,
  ShowcaseOptionsResponse,
  ShowcaseRenderResponse,
  ShowcaseScenesResponse,
  ShowcaseShareResponse,
  ShowcaseStudioAnalyzeResponse,
} from './item-picture.types';

@Injectable({ providedIn: 'root' })
export class ShowcaseApiService {
  private readonly baseUrl = environment.copilotApiBaseUrl;

  constructor(private http: HttpClient) {}

  listPictures(
    idcompany_item: number,
    params: { idcompany: number; access_token?: string; debug?: boolean }
  ): Observable<ShowcaseItemPicturesResponse> {
    const q: Record<string, string | number | boolean> = { idcompany: params.idcompany };
    if (params.access_token) {
      q.access_token = params.access_token;
    }
    if (params.debug) {
      q.debug = true;
    }
    return this.http.get<ShowcaseItemPicturesResponse>(
      `${this.baseUrl}/showcase/items/${idcompany_item}/pictures`,
      { params: q }
    );
  }

  listScenes(params: { idcompany: number; access_token?: string }): Observable<ShowcaseScenesResponse> {
    const q: Record<string, string | number> = { idcompany: params.idcompany };
    if (params.access_token) {
      q.access_token = params.access_token;
    }
    return this.http.get<ShowcaseScenesResponse>(`${this.baseUrl}/showcase/scenes`, { params: q });
  }

  postOptions(body: {
    idcompany: number;
    access_token?: string;
    idcompany_item: number;
    idcompany_item_pictures?: number | null;
    debug?: boolean;
  }): Observable<ShowcaseOptionsResponse> {
    return this.http.post<ShowcaseOptionsResponse>(`${this.baseUrl}/showcase/options`, body);
  }

  postRender(body: {
    idcompany: number;
    access_token?: string;
    idcompany_item: number;
    idcompany_item_pictures: number;
    scene_id: string;
    frame_style?: string | null;
    frame_finish?: string | null;
    frame_profile?: string | null;
    lighting?: string | null;
    placement?: string | null;
    layout_variant?: number | null;
    cutout?: boolean;
    physical_width_cm?: number | null;
    physical_height_cm?: number | null;
    wall_width_cm?: number | null;
    wall_span_cm?: number | null;
    focal_wall_rect?: [number, number, number, number] | null;
    placement_quad?: [number, number][] | null;
    /** Server compositor: directed highlight on artwork (off | top | bottom | left | right | lr | tb | quad). */
    art_spotlight?: string | null;
    debug?: boolean;
  }): Observable<ShowcaseRenderResponse> {
    return this.http.post<ShowcaseRenderResponse>(`${this.baseUrl}/showcase/render`, body);
  }

  postStudioAnalyze(body: {
    idcompany: number;
    access_token?: string;
    idcompany_item: number;
    idcompany_item_pictures?: number | null;
    debug?: boolean;
  }): Observable<ShowcaseStudioAnalyzeResponse> {
    return this.http.post<ShowcaseStudioAnalyzeResponse>(`${this.baseUrl}/showcase/studio/analyze`, body);
  }

  postBatchRender(body: {
    idcompany: number;
    access_token?: string;
    idcompany_item: number;
    idcompany_item_pictures: number;
    scene_ids: string[];
    frame_style?: string | null;
    frame_finish?: string | null;
    frame_profile?: string | null;
    lighting?: string | null;
    placement?: string | null;
    layout_variant?: number | null;
    cutout?: boolean;
    physical_width_cm?: number | null;
    physical_height_cm?: number | null;
    wall_width_cm?: number | null;
    wall_span_cm?: number | null;
    focal_wall_rect?: [number, number, number, number] | null;
    placement_quad?: [number, number][] | null;
    art_spotlight?: string | null;
    debug?: boolean;
  }): Observable<ShowcaseBatchRenderResponse> {
    return this.http.post<ShowcaseBatchRenderResponse>(`${this.baseUrl}/showcase/studio/batch-render`, body);
  }

  postShare(body: {
    idcompany: number;
    access_token?: string;
    idcompany_item: number;
    idcompany_item_pictures?: number | null;
    scene_id?: string | null;
  }): Observable<ShowcaseShareResponse> {
    return this.http.post<ShowcaseShareResponse>(`${this.baseUrl}/showcase/share`, body);
  }
}
