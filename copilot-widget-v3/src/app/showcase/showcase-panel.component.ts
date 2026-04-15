import { HttpErrorResponse } from '@angular/common/http';
import { Component, HostListener, OnInit } from '@angular/core';
import { DomSanitizer, SafeStyle, SafeUrl } from '@angular/platform-browser';
import { ActivatedRoute, Router } from '@angular/router';
import { forkJoin } from 'rxjs';
import { environment } from '../../environments/environment';
import { AuthService, SessionInfo } from '../auth.service';
import { loadPanelTheme, savePanelTheme, PanelTheme } from '../panel-theme.storage';
import {
  ShowcaseBatchRenderResponse,
  ShowcaseItemPicturesResponse,
  ShowcaseOptionsResponse,
  ShowcaseRenderResponse,
  ShowcaseSceneInfo,
  ShowcaseStudioAnalyzeResponse,
  ShowcaseSuggestionRender,
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
  /** Same storage key as AI Insights (`v3_panel_theme`). */
  showcaseTheme: PanelTheme = 'light';

  picturesRes: ShowcaseItemPicturesResponse | null = null;
  scenes: ShowcaseSceneInfo[] = [];
  scenePipelineVersion: string | null = null;
  selectedPictureId: number | null = null;
  selectedSceneId: string | null = null;

  options: ShowcaseOptionsResponse | null = null;
  renderRes: ShowcaseRenderResponse | null = null;
  studioRes: ShowcaseStudioAnalyzeResponse | null = null;
  batchRes: ShowcaseBatchRenderResponse | null = null;

  /** Stable SafeUrl per batch preview URL (avoid new bypass every CD cycle). */
  private batchSrcMemo = new Map<string, SafeUrl | string>();

  /** Full-screen carousel for batch scene previews. */
  batchCarouselOpen = false;
  batchCarouselIndex = 0;

  /** Frame × lighting suggestion renders (fired after Analyze artwork). */
  suggestionRenders: ShowcaseSuggestionRender[] = [];
  loadingSuggestions = false;
  suggestionCarouselOpen = false;
  suggestionCarouselIndex = 0;
  private suggestionSrcMemo = new Map<string, SafeUrl | string>();

  /** Phase 1: null = use manifest scene layout_index */
  layoutVariant: number | null = null;
  cutoutEnabled = false;
  physicalWidthCm: number | null = null;
  physicalHeightCm: number | null = null;
  wallWidthCm: number | null = null;
  /** Real cm width of the focal wall region; pairs with art width for scale (API wall_span_cm). */
  wallSpanCm: number | null = null;
  /**
   * Server compositor only: warm accent on mat+art (simulates track / accent lamps).
   * Values: off | top | bottom | left | right | lr | tb | quad
   */
  artSpotlight: string = 'off';

  /**
   * When non-empty, overrides presentation `options.lighting` for main preview and batch renders
   * (server compositor colour grade / overlays).
   */
  lightingPreset = '';

  /** Server compositor wood / modern frame finish; empty = use presentation `options.frame_style`. */
  frameFinish = '';
  /** thick | thin — moulding width when `frameFinish` is set. */
  frameProfile: 'thick' | 'thin' = 'thin';

  loadingPictures = false;
  loadingScenes = false;
  loadingOptions = false;
  loadingRender = false;
  /** True after render returns until the preview image fires `load` (only when URL changed). */
  previewDecodePending = false;
  loadingStudio = false;
  loadingBatch = false;
  error: string | null = null;
  /** Set when the preview <img> fires `error` (blocked URL, 403, mixed content, etc.). */
  previewImageFailed = false;

  /**
   * `bypassSecurityTrustUrl` returns a new object every call; binding it from a getter caused
   * `[src]` to update every change-detection cycle → infinite reload of the preview image.
   */
  private previewSrcMemo: { url: string; safe: SafeUrl | string } | null = null;
  /** Server pictures-fetch debug (sql_row_count, skips, hints); from ?debug=1 or SHOWCASE_DEBUG_LOG. */
  picturesFetchDebug: Record<string, unknown> | null = null;

  private static readonly DEBUG_TRACE_STORAGE_KEY = 'v3_showcase_show_debug';
  private static readonly COMPOSITE_PREVIEW_STORAGE_KEY = 'v3_showcase_composite_preview';

  /** User toggle: show debug panel and send debug=true on showcase API calls. */
  showDebugTrace = false;

  /**
   * When true, main preview uses POST /showcase/render PNG (focal wall / perspective from manifest).
   * Persisted in sessionStorage; initialized from environment default then optional user override.
   */
  showCompositedInPreview = false;

  /** When true, calls API with debug flag (env default OR user checkbox). */
  get effectiveDebugQuery(): boolean {
    return !!environment.showcasePicturesDebug || this.showDebugTrace;
  }

  /** Combined debug payloads when checkbox is on (pictures / options / render). */
  get showcaseDebugDump(): Record<string, unknown> | null {
    if (!this.showDebugTrace) {
      return null;
    }
    const out: Record<string, unknown> = {};
    if (this.picturesFetchDebug && Object.keys(this.picturesFetchDebug).length) {
      out.pictures = this.picturesFetchDebug;
    }
    const od = this.options?.debug as Record<string, unknown> | undefined;
    if (od && Object.keys(od).length) {
      out.options = od;
    }
    const rd = this.renderRes?.debug as Record<string, unknown> | undefined;
    if (rd && Object.keys(rd).length) {
      out.render = rd;
    }
    return Object.keys(out).length ? out : null;
  }

  constructor(
    private auth: AuthService,
    private showcaseApi: ShowcaseApiService,
    private route: ActivatedRoute,
    private router: Router,
    private sanitizer: DomSanitizer
  ) {}

  ngOnInit(): void {
    this.session = this.auth.getSession();
    if (!this.session?.access_token || !this.session.idcompany) {
      this.router.navigate(['/login']);
      return;
    }
    this.showcaseTheme = loadPanelTheme();
    try {
      this.showDebugTrace = sessionStorage.getItem(ShowcasePanelComponent.DEBUG_TRACE_STORAGE_KEY) === '1';
    } catch {
      this.showDebugTrace = false;
    }
    this.showCompositedInPreview = !!environment.showcaseClientCompositedPreview;
    try {
      const c = sessionStorage.getItem(ShowcasePanelComponent.COMPOSITE_PREVIEW_STORAGE_KEY);
      if (c === '1') {
        this.showCompositedInPreview = true;
      } else if (c === '0') {
        this.showCompositedInPreview = false;
      }
    } catch {
      /* keep env default */
    }
    this.route.queryParamMap.subscribe((qm) => {
      const raw = qm.get('itemId');
      const n = raw != null ? Number(raw) : NaN;
      this.itemId = Number.isFinite(n) && n >= 1 ? Math.floor(n) : null;
      this.options = null;
      this.renderRes = null;
      this.studioRes = null;
      this.batchRes = null;
      this.batchSrcMemo.clear();
      this.closeBatchCarousel();
      this.suggestionRenders = [];
      this.suggestionSrcMemo.clear();
      this.closeSuggestionCarousel();
      this.lightingPreset = '';
      this.frameFinish = '';
      this.frameProfile = 'thin';
      if (this.itemId != null) {
        this.loadPictures();
      } else {
        this.picturesRes = null;
        this.error = null;
      }
    });
    this.loadScenes();
  }

  toggleShowcaseTheme(): void {
    this.showcaseTheme = this.showcaseTheme === 'light' ? 'dark' : 'light';
    savePanelTheme(this.showcaseTheme);
  }

  onShowDebugTraceChange(checked: boolean): void {
    this.showDebugTrace = checked;
    try {
      sessionStorage.setItem(ShowcasePanelComponent.DEBUG_TRACE_STORAGE_KEY, checked ? '1' : '0');
    } catch {
      /* ignore */
    }
    if (this.itemId != null && this.session?.idcompany) {
      this.loadPictures();
    }
  }

  onCompositedPreviewChange(checked: boolean): void {
    this.showCompositedInPreview = checked;
    this.previewImageFailed = false;
    try {
      sessionStorage.setItem(ShowcasePanelComponent.COMPOSITE_PREVIEW_STORAGE_KEY, checked ? '1' : '0');
    } catch {
      /* ignore */
    }
  }

  get selectedPictureUrl(): string | null {
    if (!this.picturesRes?.pictures?.length || this.selectedPictureId == null) {
      return null;
    }
    const p = this.picturesRes.pictures.find((x) => x.idcompany_item_pictures === this.selectedPictureId);
    const u = p?.resolved_url;
    if (u == null || typeof u !== 'string') {
      return null;
    }
    const t = u.trim();
    return t.length > 0 ? t : null;
  }

  /** Effective lighting key sent to `/showcase/render` (override or presentation default). */
  /** Custom frame UI is disabled for analyzed 3D / pedestal artwork. */
  get frameFinishesDisabled(): boolean {
    return this.studioRes?.artwork_kind === '3d_pedestal';
  }

  get effectiveLighting(): string | undefined {
    const p = (this.lightingPreset || '').trim();
    if (p.length) {
      return p;
    }
    const o = this.options?.lighting;
    const t = o != null && typeof o === 'string' ? o.trim() : '';
    return t.length ? t : undefined;
  }

  get selectedScene(): ShowcaseSceneInfo | null {
    if (!this.selectedSceneId) {
      return null;
    }
    return this.scenes.find((s) => s.scene_id === this.selectedSceneId) ?? null;
  }

  /**
   * Maps manifest scene_id to SCSS modifier on .scene-stage (visual room, not pixel compositing).
   */
  get sceneStageThemeClass(): string {
    const id = this.selectedSceneId;
    if (!id) {
      return 'scene-stage--default';
    }
    return this.scenes.some((s) => s.scene_id === id) ? `scene-stage--${id}` : 'scene-stage--default';
  }

  /** When manifest provides preview_asset_url, use as full-bleed backdrop under the stage theme. */
  get sceneBackdropTrustStyle(): SafeStyle | null {
    const u = this.selectedScene?.preview_asset_url?.trim();
    if (!u || !(u.startsWith('https://') || u.startsWith('http://'))) {
      return null;
    }
    const safe = u.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
    return this.sanitizer.bypassSecurityTrustStyle(`background-image: url("${safe}")`);
  }

  /** Raw http(s) URL for the preview (trimmed); null if missing. */
  get previewUrl(): string | null {
    const fromRender = this.renderRes?.preview_url?.trim() ?? '';
    const fromPicture = this.selectedPictureUrl?.trim() ?? '';
    const raw = fromRender || fromPicture;
    return raw.length > 0 ? raw : null;
  }

  /**
   * Authenticated same-origin image URL (API fetches CDN/S3). Use when showcaseImageProxy is true.
   */
  get previewProxyUrl(): string | null {
    if (!environment.showcaseImageProxy) {
      return null;
    }
    if (!this.session?.idcompany || this.itemId == null || this.selectedPictureId == null) {
      return null;
    }
    const base = environment.copilotApiBaseUrl.replace(/\/$/, '');
    const params = new URLSearchParams({ idcompany: String(this.session.idcompany) });
    if (this.session.access_token) {
      params.set('access_token', this.session.access_token);
    }
    return `${base}/showcase/items/${this.itemId}/pictures/${this.selectedPictureId}/file?${params.toString()}`;
  }

  /** API returned composited metadata (PNG may still be hidden when client flag is off). */
  get isCompositedPreview(): boolean {
    return this.renderRes?.output_mode === 'composited';
  }

  /** When true, use flat server PNG layout; when false, keep CSS room + artwork (stable preview). */
  get showCompositedFlatPreview(): boolean {
    return this.isCompositedPreview && this.showCompositedInPreview;
  }

  /** Image src: composited API PNG, else picture proxy, else direct CDN URL. */
  get previewSrc(): SafeUrl | string | null {
    const raw = this.rawPreviewUrlForImg();
    if (!raw) {
      this.previewSrcMemo = null;
      return null;
    }
    if (this.previewSrcMemo?.url === raw) {
      return this.previewSrcMemo.safe;
    }
    const lower = raw.toLowerCase();
    const safe =
      lower.startsWith('https://') || lower.startsWith('http://')
        ? this.sanitizer.bypassSecurityTrustUrl(raw)
        : raw;
    this.previewSrcMemo = { url: raw, safe };
    return safe;
  }

  /** Plain URL string before sanitization (stable identity for memoization). */
  private rawPreviewUrlForImg(): string | null {
    const composited = this.renderRes?.preview_url?.trim();
    if (this.showCompositedFlatPreview && composited && !this.previewImageFailed) {
      return composited;
    }
    const proxy = this.previewProxyUrl?.trim() ?? '';
    if (proxy.length > 0) {
      return proxy;
    }
    const pic = this.selectedPictureUrl?.trim() ?? '';
    if (pic.length > 0) {
      return pic;
    }
    return null;
  }

  onPreviewImgError(): void {
    this.previewImageFailed = true;
    this.previewDecodePending = false;
  }

  onPreviewImgLoad(): void {
    this.previewImageFailed = false;
    this.previewDecodePending = false;
  }

  /** Spinner overlay: API render in flight or waiting for new preview image decode. */
  get showPreviewBusy(): boolean {
    return this.loadingRender || this.previewDecodePending;
  }

  /** Align batch preview host with SPA API base (127.0.0.1 vs localhost cookies/CORS). */
  private normalizeBatchPreviewUrl(url: string): string {
    const u = (url || '').trim();
    if (!u) return u;
    try {
      const parsed = new URL(u);
      const path = parsed.pathname || '';
      if (!path.includes('/showcase/render/') || !path.endsWith('/preview')) {
        return u;
      }
      const apiRoot = environment.copilotApiBaseUrl.replace(/\/$/, '');
      let origin: string;
      try {
        origin = new URL(apiRoot).origin;
      } catch {
        return u;
      }
      return `${origin}${path}${parsed.search}`;
    } catch {
      return u;
    }
  }

  /** Batch preview URLs are absolute API URLs; bypass Angular URL sanitizer for <img>. */
  batchPreviewSrc(url: string): SafeUrl | string {
    const raw = this.normalizeBatchPreviewUrl(url).trim();
    if (!raw) return raw;
    const hit = this.batchSrcMemo.get(raw);
    if (hit !== undefined) return hit;
    const lower = raw.toLowerCase();
    const val =
      lower.startsWith('https://') || lower.startsWith('http://')
        ? this.sanitizer.bypassSecurityTrustUrl(raw)
        : raw;
    this.batchSrcMemo.set(raw, val);
    return val;
  }

  get batchCarouselItemCount(): number {
    return this.batchRes?.items?.length ?? 0;
  }

  get batchCarouselSceneLabel(): string {
    const items = this.batchRes?.items;
    if (!items?.length || this.batchCarouselIndex < 0 || this.batchCarouselIndex >= items.length) {
      return '';
    }
    const sid = items[this.batchCarouselIndex].scene_id;
    const sc = this.scenes.find((s) => s.scene_id === sid);
    return (sc?.label || sid).trim();
  }

  get batchCarouselSceneId(): string {
    const items = this.batchRes?.items;
    if (!items?.length || this.batchCarouselIndex < 0 || this.batchCarouselIndex >= items.length) {
      return '';
    }
    return items[this.batchCarouselIndex].scene_id;
  }

  get batchCarouselImageSrc(): SafeUrl | string {
    const items = this.batchRes?.items;
    if (!items?.length || this.batchCarouselIndex < 0 || this.batchCarouselIndex >= items.length) {
      return '';
    }
    return this.batchPreviewSrc(items[this.batchCarouselIndex].preview_url);
  }

  openBatchCarousel(index: number): void {
    const n = this.batchRes?.items?.length ?? 0;
    if (n < 1) {
      return;
    }
    this.batchCarouselIndex = Math.max(0, Math.min(index, n - 1));
    this.batchCarouselOpen = true;
  }

  closeBatchCarousel(): void {
    this.batchCarouselOpen = false;
  }

  batchCarouselPrev(): void {
    const n = this.batchRes?.items?.length ?? 0;
    if (n < 1) {
      return;
    }
    this.batchCarouselIndex = (this.batchCarouselIndex - 1 + n) % n;
  }

  batchCarouselNext(): void {
    const n = this.batchRes?.items?.length ?? 0;
    if (n < 1) {
      return;
    }
    this.batchCarouselIndex = (this.batchCarouselIndex + 1) % n;
  }

  // --- Suggestion carousel ---

  get suggestionCarouselItemCount(): number {
    return this.suggestionRenders.length;
  }

  get suggestionCarouselLabel(): string {
    const s = this.suggestionRenders[this.suggestionCarouselIndex];
    if (!s) {
      return '';
    }
    return `${s.frame_style} · ${s.lighting}`;
  }

  get suggestionCarouselImageSrc(): SafeUrl | string {
    const s = this.suggestionRenders[this.suggestionCarouselIndex];
    if (!s) {
      return '';
    }
    return this.suggestionPreviewSrc(s.preview_url);
  }

  suggestionPreviewSrc(url: string): SafeUrl | string {
    if (!url) {
      return '';
    }
    const cached = this.suggestionSrcMemo.get(url);
    if (cached !== undefined) {
      return cached;
    }
    const safe = this.sanitizer.bypassSecurityTrustUrl(url);
    this.suggestionSrcMemo.set(url, safe);
    return safe;
  }

  openSuggestionCarousel(index: number): void {
    const n = this.suggestionRenders.length;
    if (n < 1) {
      return;
    }
    this.suggestionCarouselIndex = Math.max(0, Math.min(index, n - 1));
    this.suggestionCarouselOpen = true;
  }

  closeSuggestionCarousel(): void {
    this.suggestionCarouselOpen = false;
  }

  suggestionCarouselPrev(): void {
    const n = this.suggestionRenders.length;
    if (n < 1) {
      return;
    }
    this.suggestionCarouselIndex = (this.suggestionCarouselIndex - 1 + n) % n;
  }

  suggestionCarouselNext(): void {
    const n = this.suggestionRenders.length;
    if (n < 1) {
      return;
    }
    this.suggestionCarouselIndex = (this.suggestionCarouselIndex + 1) % n;
  }

  @HostListener('document:keydown', ['$event'])
  onBatchCarouselKeydown(ev: KeyboardEvent): void {
    if (this.suggestionCarouselOpen) {
      if (ev.key === 'Escape') {
        this.closeSuggestionCarousel();
        ev.preventDefault();
        return;
      }
      if (ev.key === 'ArrowLeft') {
        this.suggestionCarouselPrev();
        ev.preventDefault();
      } else if (ev.key === 'ArrowRight') {
        this.suggestionCarouselNext();
        ev.preventDefault();
      }
      return;
    }
    if (!this.batchCarouselOpen) {
      return;
    }
    if (ev.key === 'Escape') {
      this.closeBatchCarousel();
      ev.preventDefault();
      return;
    }
    if (ev.key === 'ArrowLeft') {
      this.batchCarouselPrev();
      ev.preventDefault();
    } else if (ev.key === 'ArrowRight') {
      this.batchCarouselNext();
      ev.preventDefault();
    }
  }

  onPictureChange(id: number): void {
    this.previewImageFailed = false;
    this.selectedPictureId = id;
    this.loadOptionsAndRender();
  }

  onSceneChange(id: string): void {
    this.previewImageFailed = false;
    this.selectedSceneId = id;
    this.runRender();
  }

  onStudioControlsChange(): void {
    this.runRender();
  }

  runStudioAnalyze(): void {
    if (this.itemId == null || !this.session?.idcompany || this.selectedPictureId == null) {
      return;
    }
    this.loadingStudio = true;
    this.studioRes = null;
    this.showcaseApi
      .postStudioAnalyze({
        idcompany: this.session.idcompany,
        access_token: this.session.access_token,
        idcompany_item: this.itemId,
        idcompany_item_pictures: this.selectedPictureId,
        debug: this.effectiveDebugQuery,
      })
      .subscribe({
        next: (r) => {
          this.studioRes = r;
          if (r.artwork_kind === '3d_pedestal') {
            this.frameFinish = '';
            this.frameProfile = 'thin';
          }
          this.loadingStudio = false;
        },
        error: () => {
          this.loadingStudio = false;
          this.studioRes = null;
        },
      });
  }

  runBatchAllScenes(): void {
    if (
      this.itemId == null ||
      !this.session?.idcompany ||
      this.selectedPictureId == null ||
      !this.scenes.length
    ) {
      return;
    }
    this.loadingBatch = true;
    this.batchRes = null;
    this.batchSrcMemo.clear();
    this.closeBatchCarousel();
    const extras = this.buildRenderExtras();
    this.showcaseApi
      .postBatchRender({
        idcompany: this.session.idcompany,
        access_token: this.session.access_token,
        idcompany_item: this.itemId,
        idcompany_item_pictures: this.selectedPictureId,
        scene_ids: this.scenes.map((s) => s.scene_id),
        frame_style: this.options?.frame_style,
        lighting: this.effectiveLighting,
        placement: this.options?.placement,
        ...extras,
        debug: this.effectiveDebugQuery,
      })
      .subscribe({
        next: (r) => {
          this.batchRes = r;
          this.loadingBatch = false;
        },
        error: () => {
          this.loadingBatch = false;
          this.batchRes = null;
          this.batchSrcMemo.clear();
          this.closeBatchCarousel();
        },
      });
  }

  private buildRenderExtras(): {
    layout_variant?: number | null;
    cutout?: boolean;
    physical_width_cm?: number | null;
    physical_height_cm?: number | null;
    wall_width_cm?: number | null;
    wall_span_cm?: number | null;
    art_spotlight?: string | null;
    frame_finish?: string | null;
    frame_profile?: string | null;
  } {
    const out: {
      layout_variant?: number | null;
      cutout?: boolean;
      physical_width_cm?: number | null;
      physical_height_cm?: number | null;
      wall_width_cm?: number | null;
      wall_span_cm?: number | null;
      art_spotlight?: string | null;
      frame_finish?: string | null;
      frame_profile?: string | null;
    } = {};
    if (this.layoutVariant !== null && this.layoutVariant !== undefined) {
      out.layout_variant = this.layoutVariant;
    }
    if (this.cutoutEnabled) {
      out.cutout = true;
    }
    if (this.physicalWidthCm != null && this.physicalWidthCm > 0) {
      out.physical_width_cm = this.physicalWidthCm;
    }
    if (this.physicalHeightCm != null && this.physicalHeightCm > 0) {
      out.physical_height_cm = this.physicalHeightCm;
    }
    if (this.wallWidthCm != null && this.wallWidthCm > 0) {
      out.wall_width_cm = this.wallWidthCm;
    }
    if (this.wallSpanCm != null && this.wallSpanCm > 0) {
      out.wall_span_cm = this.wallSpanCm;
    }
    if (this.artSpotlight && this.artSpotlight !== 'off') {
      out.art_spotlight = this.artSpotlight;
    }
    const ff = (this.frameFinish || '').trim();
    if (!this.frameFinishesDisabled && ff.length) {
      out.frame_finish = ff;
      out.frame_profile = this.frameProfile;
    }
    return out;
  }

  private loadPictures(): void {
    if (this.itemId == null || !this.session?.idcompany) {
      return;
    }
    this.loadingPictures = true;
    this.error = null;
    this.previewImageFailed = false;
    this.picturesFetchDebug = null;
    this.showcaseApi
      .listPictures(this.itemId, {
        idcompany: this.session.idcompany,
        access_token: this.session.access_token,
        debug: this.effectiveDebugQuery,
      })
      .subscribe({
        next: (res) => {
          this.picturesRes = res;
          this.picturesFetchDebug = (res.debug as Record<string, unknown>) ?? null;
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
          const detail = err.error?.detail as
            | { error?: string; message?: string; debug?: Record<string, unknown> }
            | string
            | undefined;
          const d = typeof detail === 'object' && detail !== null ? detail : null;
          if (d?.debug) {
            this.picturesFetchDebug = d.debug;
          }
          if (err.status === 404 && d?.error === 'showcase_disabled') {
            this.error = 'Artwork showcase is not enabled on the server.';
          } else {
            const msg = d && typeof d.message === 'string' ? d.message : undefined;
            this.error = msg || err.message || 'Could not load pictures.';
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
        debug: this.effectiveDebugQuery,
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

  runSuggestionRenders(): void {
    if (
      this.itemId == null ||
      !this.session?.idcompany ||
      this.selectedPictureId == null ||
      !this.selectedSceneId ||
      !this.studioRes
    ) {
      return;
    }
    const frames = this.studioRes.frame_suggestions ?? [];
    const lights = this.studioRes.lighting_suggestions ?? [];
    if (!frames.length || !lights.length) {
      return;
    }
    const pairs: { frame_style: string; lighting: string }[] = [];
    for (const f of frames) {
      for (const l of lights) {
        pairs.push({ frame_style: f, lighting: l });
      }
    }
    this.loadingSuggestions = true;
    this.suggestionRenders = [];
    this.suggestionSrcMemo.clear();
    this.closeSuggestionCarousel();
    const extras = this.buildRenderExtras();
    const requests = pairs.map((p) =>
      this.showcaseApi.postRender({
        idcompany: this.session!.idcompany,
        access_token: this.session!.access_token,
        idcompany_item: this.itemId!,
        idcompany_item_pictures: this.selectedPictureId!,
        scene_id: this.selectedSceneId!,
        frame_style: p.frame_style,
        lighting: p.lighting,
        placement: this.options?.placement,
        ...extras,
        debug: this.effectiveDebugQuery,
      })
    );
    forkJoin(requests).subscribe({
      next: (results) => {
        this.suggestionRenders = results.map((r, i) => ({
          frame_style: pairs[i].frame_style,
          lighting: pairs[i].lighting,
          preview_url: this.normalizeBatchPreviewUrl(r.preview_url ?? ''),
          output_mode: r.output_mode ?? '',
        }));
        this.loadingSuggestions = false;
      },
      error: () => {
        this.loadingSuggestions = false;
        this.suggestionRenders = [];
        this.suggestionSrcMemo.clear();
        this.closeSuggestionCarousel();
      },
    });
  }

  private runRender(): void {
    if (
      this.itemId == null ||
      !this.session?.idcompany ||
      this.selectedPictureId == null ||
      !this.selectedSceneId
    ) {
      this.renderRes = null;
      this.loadingRender = false;
      this.previewDecodePending = false;
      return;
    }
    const urlBefore = this.rawPreviewUrlForImg();
    this.loadingRender = true;
    this.previewDecodePending = false;
    const extras = this.buildRenderExtras();
    this.showcaseApi
      .postRender({
        idcompany: this.session.idcompany,
        access_token: this.session.access_token,
        idcompany_item: this.itemId,
        idcompany_item_pictures: this.selectedPictureId,
        scene_id: this.selectedSceneId,
        frame_style: this.options?.frame_style,
        lighting: this.effectiveLighting,
        placement: this.options?.placement,
        ...extras,
        debug: this.effectiveDebugQuery,
      })
      .subscribe({
        next: (r) => {
          this.previewImageFailed = false;
          this.renderRes = r;
          this.loadingRender = false;
          const urlAfter = this.rawPreviewUrlForImg();
          this.previewDecodePending = Boolean(urlAfter && urlAfter !== urlBefore);
        },
        error: () => {
          this.loadingRender = false;
          this.previewDecodePending = false;
          this.renderRes = null;
        },
      });
  }
}
