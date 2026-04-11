import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import {
  ShowcaseItemPicturesResponse,
  ShowcaseOptionsResponse,
  ShowcaseRenderResponse,
  ShowcaseScenesResponse,
  ShowcaseShareResponse,
} from './item-picture.types';

@Injectable({ providedIn: 'root' })
export class ShowcaseApiService {
  private readonly baseUrl = environment.copilotApiBaseUrl;

  constructor(private http: HttpClient) {}

  listPictures(
    idcompany_item: number,
    params: { idcompany: number; access_token?: string }
  ): Observable<ShowcaseItemPicturesResponse> {
    const q: Record<string, string | number> = { idcompany: params.idcompany };
    if (params.access_token) {
      q.access_token = params.access_token;
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
    lighting?: string | null;
    placement?: string | null;
  }): Observable<ShowcaseRenderResponse> {
    return this.http.post<ShowcaseRenderResponse>(`${this.baseUrl}/showcase/render`, body);
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
