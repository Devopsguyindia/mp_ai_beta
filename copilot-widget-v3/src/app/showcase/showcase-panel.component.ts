import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { AuthService, SessionInfo } from '../auth.service';
import {
  ShowcaseItemPicturesResponse,
  ShowcaseOptionsResponse,
  ShowcaseRenderResponse,
  ShowcaseSceneInfo,
} from './item-picture.types';
import { ShowcaseApiService } from './showcase-api.service';

@Component({
  selector: 'app-showcase-panel',
  templateUrl: './showcase-panel.component.html',
  styleUrls: ['./showcase-panel.component.scss'],
})
export class ShowcasePanelComponent implements OnInit {
  session: SessionInfo | null = null;
  itemId: number | null = null;

  picturesRes: ShowcaseItemPicturesResponse | null = null;
  scenes: ShowcaseSceneInfo[] = [];
  scenePipelineVersion: string | null = null;
  selectedPictureId: number | null = null;
  selectedSceneId: string | null = null;

  options: ShowcaseOptionsResponse | null = null;
  renderRes: ShowcaseRenderResponse | null = null;

  loadingPictures = false;
  loadingScenes = false;
  loadingOptions = false;
  loadingRender = false;
  error: string | null = null;

  constructor(
    private auth: AuthService,
    private showcaseApi: ShowcaseApiService,
    private route: ActivatedRoute,
    private router: Router
  ) {}

  ngOnInit(): void {
    this.session = this.auth.getSession();
    if (!this.session?.access_token || !this.session.idcompany) {
      this.router.navigate(['/login']);
      return;
    }
    this.route.queryParamMap.subscribe((qm) => {
      const raw = qm.get('itemId');
      const n = raw != null ? Number(raw) : NaN;
      this.itemId = Number.isFinite(n) && n >= 1 ? Math.floor(n) : null;
      this.options = null;
      this.renderRes = null;
      if (this.itemId != null) {
        this.loadPictures();
      } else {
        this.picturesRes = null;
        this.error = null;
      }
    });
    this.loadScenes();
  }

  get selectedPictureUrl(): string | null {
    if (!this.picturesRes?.pictures?.length || this.selectedPictureId == null) {
      return null;
    }
    const p = this.picturesRes.pictures.find((x) => x.idcompany_item_pictures === this.selectedPictureId);
    return p?.resolved_url ?? null;
  }

  get selectedSceneLabel(): string | null {
    if (!this.selectedSceneId) {
      return null;
    }
    return this.scenes.find((s) => s.scene_id === this.selectedSceneId)?.label ?? this.selectedSceneId;
  }

  get previewUrl(): string | null {
    return this.renderRes?.preview_url ?? this.selectedPictureUrl;
  }

  onPictureChange(id: number): void {
    this.selectedPictureId = id;
    this.loadOptionsAndRender();
  }

  onSceneChange(id: string): void {
    this.selectedSceneId = id;
    this.runRender();
  }

  private loadPictures(): void {
    if (this.itemId == null || !this.session?.idcompany) {
      return;
    }
    this.loadingPictures = true;
    this.error = null;
    this.showcaseApi
      .listPictures(this.itemId, {
        idcompany: this.session.idcompany,
        access_token: this.session.access_token,
      })
      .subscribe({
        next: (res) => {
          this.picturesRes = res;
          this.loadingPictures = false;
          const pics = res.pictures || [];
          if (pics.length) {
            const primary = pics.find((p) => p.is_primary === 1) ?? pics[0];
            this.selectedPictureId = primary.idcompany_item_pictures;
          } else {
            this.selectedPictureId = null;
          }
          this.loadOptionsAndRender();
        },
        error: (err: HttpErrorResponse) => {
          this.loadingPictures = false;
          this.picturesRes = null;
          this.selectedPictureId = null;
          const body = err.error as { error?: string; detail?: { error?: string; message?: string } } | null;
          if (err.status === 404 && body?.detail?.error === 'showcase_disabled') {
            this.error = 'Artwork showcase is not enabled on the server.';
          } else {
            const msg = body?.detail && typeof body.detail === 'object' ? body.detail.message : undefined;
            this.error = (typeof msg === 'string' && msg) || err.message || 'Could not load pictures.';
          }
        },
      });
  }

  private loadScenes(): void {
    if (!this.session?.idcompany) {
      return;
    }
    this.loadingScenes = true;
    this.showcaseApi
      .listScenes({
        idcompany: this.session.idcompany,
        access_token: this.session.access_token,
      })
      .subscribe({
        next: (res) => {
          this.scenes = res.scenes || [];
          this.scenePipelineVersion = res.pipeline_version || null;
          this.loadingScenes = false;
          this.applyDefaultSceneFromOptions();
          if (this.scenes.length && !this.selectedSceneId) {
            this.selectedSceneId = this.scenes[0].scene_id;
          }
          if (this.picturesRes?.pictures?.length && this.selectedPictureId != null && this.selectedSceneId) {
            this.runRender();
          }
        },
        error: () => {
          this.loadingScenes = false;
          this.scenes = [];
        },
      });
  }

  private loadOptionsAndRender(): void {
    if (
      this.itemId == null ||
      !this.session?.idcompany ||
      this.selectedPictureId == null ||
      !this.picturesRes?.pictures?.length
    ) {
      this.options = null;
      this.renderRes = null;
      return;
    }
    this.loadingOptions = true;
    this.showcaseApi
      .postOptions({
        idcompany: this.session.idcompany,
        access_token: this.session.access_token,
        idcompany_item: this.itemId,
        idcompany_item_pictures: this.selectedPictureId,
      })
      .subscribe({
        next: (o) => {
          this.options = o;
          this.loadingOptions = false;
          this.applyDefaultSceneFromOptions();
          this.runRender();
        },
        error: () => {
          this.loadingOptions = false;
          this.options = null;
          this.runRender();
        },
      });
  }

  private applyDefaultSceneFromOptions(): void {
    const first = this.options?.recommended_scene_ids?.find((id) => this.scenes.some((s) => s.scene_id === id));
    if (first) {
      this.selectedSceneId = first;
      return;
    }
    if (!this.selectedSceneId && this.scenes.length) {
      this.selectedSceneId = this.scenes[0].scene_id;
    }
  }

  private runRender(): void {
    if (
      this.itemId == null ||
      !this.session?.idcompany ||
      this.selectedPictureId == null ||
      !this.selectedSceneId
    ) {
      this.renderRes = null;
      return;
    }
    this.loadingRender = true;
    this.showcaseApi
      .postRender({
        idcompany: this.session.idcompany,
        access_token: this.session.access_token,
        idcompany_item: this.itemId,
        idcompany_item_pictures: this.selectedPictureId,
        scene_id: this.selectedSceneId,
        frame_style: this.options?.frame_style,
        lighting: this.options?.lighting,
        placement: this.options?.placement,
      })
      .subscribe({
        next: (r) => {
          this.renderRes = r;
          this.loadingRender = false;
        },
        error: () => {
          this.loadingRender = false;
          this.renderRes = null;
        },
      });
  }
}
