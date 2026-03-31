import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { finalize } from 'rxjs/operators';
import { AuthService, SessionInfo } from './auth.service';
import {
  ChatResponse,
  CopilotApiService,
  ReportSuggestionsResponse
} from './copilot-api.service';
import { environment } from '../environments/environment';

export interface ChartDataSets {
  data: number[];
  label?: string;
}

@Component({
  selector: 'app-dashboard',
  templateUrl: './dashboard.component.html',
  styleUrls: ['./dashboard.component.scss']
})
export class DashboardComponent implements OnInit {
  session: SessionInfo | null = null;
  question = '';
  debug = true;
  displayChart = true;

  loading = false;
  error: any = null;
  response: ChatResponse | null = null;
  /** null = no result yet; true = MySQL OK; false = connection / DB error */
  erpConnectionOk: boolean | null = null;
  erpConnectionError: string | null = null;
  history: string[] = [];
  readonly useV3Ask = !!(environment as any).v3AskEnabled;
  readonly reportSuggestionsFeatureEnabled =
    (environment as { reportSuggestionsEnabled?: boolean }).reportSuggestionsEnabled !== false;

  reportScope: 'gallery' | 'me' = 'gallery';
  reportSuggestionsLoading = false;
  reportSuggestionsError: string | null = null;
  reportSuggestions: ReportSuggestionsResponse | null = null;
  /** Disables the matching Re-run button while the proxy request is in flight. */
  rerunBusyHash: string | null = null;

  /** Placeholder row indices for the query-output skeleton loader (Option A). */
  readonly queryLoaderSkeletonRows = [0, 1, 2, 3];

  /** Static fallbacks when the API does not return follow_up_prompts (mix: sales x2, inventory, artist, vendor). */
  readonly suggestedPrompts: string[] = [
    'Top customers by purchase total in the last 90 days',
    'Monthly revenue trend from line sales for the last 12 months',
    'Inventory quantity on hand summary by stock location',
    'Top selling artists by line total in the last 90 days',
    'Top vendors by outstanding payables'
  ];

  /** Prompts to display: follow-up suggestions from response when available, else static list. */
  get displayedPrompts(): string[] {
    const fp = this.response?.follow_up_prompts;
    if (Array.isArray(fp) && fp.length > 0) {
      return fp;
    }
    return this.suggestedPrompts;
  }

  /** True when displaying LLM-generated follow-up prompts (vs static suggested prompts). */
  get hasFollowUpPrompts(): boolean {
    return Array.isArray(this.response?.follow_up_prompts) && this.response.follow_up_prompts.length > 0;
  }

  constructor(
    private auth: AuthService,
    private api: CopilotApiService,
    private router: Router
  ) {}

  ngOnInit(): void {
    this.session = this.auth.getSession();
    if (!this.session || !this.session.idcompany) {
      this.router.navigate(['/login']);
      return;
    }
    this.loadHistory();
    if (this.reportSuggestionsFeatureEnabled) {
      this.loadReportSuggestions();
    }
  }

  private sessionUserIdNumber(): number | undefined {
    const u = this.session?.userid;
    if (u == null || u === '') {
      return undefined;
    }
    const n = Number(u);
    return Number.isFinite(n) ? n : undefined;
  }

  setReportScope(scope: 'gallery' | 'me'): void {
    this.reportScope = scope;
    this.loadReportSuggestions();
  }

  loadReportSuggestions(): void {
    if (!this.reportSuggestionsFeatureEnabled || !this.session?.idcompany) {
      return;
    }
    if (this.reportScope === 'me' && this.sessionUserIdNumber() === undefined) {
      this.reportSuggestionsError = 'Your session has no user id; switch to Gallery scope.';
      this.reportSuggestions = null;
      return;
    }

    this.reportSuggestionsLoading = true;
    this.reportSuggestionsError = null;

    const uid = this.sessionUserIdNumber();
    this.api
      .reportSuggestions({
        idcompany: Number(this.session.idcompany),
        access_token: this.session.access_token,
        user_id: this.reportScope === 'me' && uid !== undefined ? uid : undefined,
        top_n: 5,
        recent_n: 8,
        smart_default_limit: 12,
        // Full JSON required for Re-run in ERP (proxy GET with same params).
        truncate_filter_data: false,
        filter_data_max_chars: 50000
      })
      .subscribe({
        next: (res) => {
          this.reportSuggestions = res;
          this.reportSuggestionsLoading = false;
          if (!res.ok && res.warnings?.length) {
            this.reportSuggestionsError = res.warnings.join(' ');
          }
        },
        error: (err: HttpErrorResponse) => {
          this.reportSuggestionsLoading = false;
          this.reportSuggestions = null;
          const d = err?.error?.detail;
          let msg: string;
          if (err.status === 0) {
            msg =
              'Cannot reach the report API (network/CORS or server not running). ' +
              `Check that the backend is up at ${environment.copilotApiBaseUrl} and the page origin is allowed by CORS.`;
          } else if (d?.error === 'report_suggestions_disabled') {
            msg = 'Report suggestions are disabled on the server.';
          } else if (Array.isArray(d)) {
            msg = d
              .map((v: { loc?: string[]; msg?: string }) =>
                [v.loc?.join('.'), v.msg].filter(Boolean).join(': ')
              )
              .join('; ');
          } else if (typeof d === 'string') {
            msg = d;
          } else {
            msg = err?.error?.message || err?.message || 'Could not load report insights.';
          }
          this.reportSuggestionsError = msg || JSON.stringify(err?.error || err);
        }
      });
  }

  reportInsightsEmpty(): boolean {
    const r = this.reportSuggestions;
    if (!r) {
      return true;
    }
    return (
      !r.top_reports?.length &&
      !r.recent_runs?.length &&
      !r.smart_defaults?.length &&
      !r.predict_hints?.length
    );
  }

  /**
   * @param rollEndDates Smart defaults only: set end-date fields to today (MM/DD/YYYY), keep start dates.
   */
  rerunReport(
    filterData: string | null | undefined,
    filterHash: string,
    rollEndDates = false
  ): void {
    let fd = filterData?.trim();
    if (!fd || !this.session?.access_token) {
      return;
    }
    this.rerunBusyHash = filterHash;
    this.api
      .rerunReport({
        access_token: this.session.access_token,
        filter_data: fd,
        roll_end_dates: rollEndDates
      })
      .subscribe({
        next: (resp) => {
          const blob = resp.body;
          this.rerunBusyHash = null;
          if (!blob || blob.size === 0) {
            this.reportSuggestionsError = 'Re-run returned an empty response.';
            return;
          }
          const url = URL.createObjectURL(blob);
          window.open(url, '_blank', 'noopener,noreferrer');
          setTimeout(() => URL.revokeObjectURL(url), 120000);
        },
        error: (err: HttpErrorResponse) => {
          this.rerunBusyHash = null;
          const body = err.error;
          if (body instanceof Blob) {
            body.text().then((t) => {
              try {
                const j = JSON.parse(t) as { detail?: { message?: string } | string };
                const d = j.detail;
                this.reportSuggestionsError =
                  typeof d === 'string' ? d : d?.message || t.slice(0, 600) || err.message;
              } catch {
                this.reportSuggestionsError = t.slice(0, 600) || err.message;
              }
            });
          } else {
            this.reportSuggestionsError = err.message || 'Re-run failed.';
          }
        }
      });
  }

  private historyScopeStable(): string {
    if (!this.session) {
      return 'anonymous';
    }
    return [
      this.session.idcompany ?? 'no_company',
      this.session.userid || this.session.token_payload?.userid || 'no_userid',
      this.session.username || 'no_username'
    ].join('_');
  }

  private historyKey(): string {
    return `copilotPromptHistory_${this.historyScopeStable()}`;
  }

  private legacyHistoryKeys(): string[] {
    if (!this.session) {
      return ['copilotPromptHistory'];
    }
    const idcompany = this.session.idcompany ?? 'no_company';
    const userid = this.session.userid || this.session.token_payload?.userid || 'no_userid';
    const username = this.session.username || 'no_username';
    const tokenSuffix = this.session.access_token ? this.session.access_token.slice(-10) : 'no_token';
    return [
      // immediate previous key format (included access token suffix)
      `copilotPromptHistory_${idcompany}_${userid}_${username}_${tokenSuffix}`,
      // older per-user format used before token-suffixed key
      `copilotPromptHistory_${idcompany}_${userid}`,
      `copilotPromptHistory_${idcompany}_${username}`,
      // oldest generic key
      'copilotPromptHistory'
    ];
  }

  private loadHistory(): void {
    try {
      const stableKey = this.historyKey();
      const raw = localStorage.getItem(stableKey);
      if (raw) {
        const parsed = JSON.parse(raw);
        this.history = Array.isArray(parsed) ? (parsed as string[]) : [];
        return;
      }

      for (const legacyKey of this.legacyHistoryKeys()) {
        const legacyRaw = localStorage.getItem(legacyKey);
        if (!legacyRaw) {
          continue;
        }
        const parsed = JSON.parse(legacyRaw);
        if (!Array.isArray(parsed)) {
          continue;
        }
        const migrated = parsed as string[];
        this.history = migrated;
        localStorage.setItem(stableKey, JSON.stringify(migrated));
        return;
      }
      this.history = [];
    } catch {
      this.history = [];
    }
  }

  private saveHistory(prompt: string): void {
    const next = [prompt, ...this.history.filter((h) => h !== prompt)].slice(0, 10);
    this.history = next;
    localStorage.setItem(this.historyKey(), JSON.stringify(next));
  }

  trackByIndex(index: number, _item: number): number {
    return index;
  }

  usePrompt(prompt: string): void {
    this.question = prompt;
  }

  run(): void {
    if (!this.session || !this.session.idcompany || !this.question.trim()) {
      return;
    }

    this.loading = true;
    this.error = null;
    this.response = null;
    this.saveHistory(this.question.trim());

    const req = {
      idcompany: Number(this.session.idcompany),
      access_token: this.session.access_token,
      question: this.question.trim(),
      debug: this.debug
    };
    const call$ = this.useV3Ask
      ? this.api.askV3({
          ...req,
          include_chart: this.displayChart
        })
      : this.api.chat(req);
    call$.subscribe({
      next: (res) => {
        this.response = res;
        this.loading = false;
        this.applyErpConnectionFromResponse(res);
      },
      error: (err) => {
        this.error = err;
        this.loading = false;
        if (err instanceof HttpErrorResponse) {
          this.applyErpConnectionFromHttpError(err);
        }
      }
    });
  }

  logout(): void {
    const s = this.session;
    if (s?.auth_session_id) {
      this.api
        .authLogout({
          auth_session_id: s.auth_session_id,
          idcompany: s.idcompany ?? undefined,
          userid: s.userid ?? undefined,
          username: s.username ?? undefined
        })
        .pipe(
          finalize(() => {
            this.auth.logout();
            this.router.navigate(['/login']);
          })
        )
        .subscribe({ error: () => undefined });
    } else {
      this.auth.logout();
      this.router.navigate(['/login']);
    }
  }

  get erpConnectionAriaLabel(): string {
    if (this.erpConnectionOk === true) {
      return 'Masterpiece ERP database connection OK';
    }
    if (this.erpConnectionOk === false) {
      return 'Masterpiece ERP database connection failed';
    }
    return 'Masterpiece ERP connection status pending';
  }

  private applyErpConnectionFromResponse(res: ChatResponse): void {
    if (res.db_status && res.db_status.ok === false) {
      this.erpConnectionOk = false;
      this.erpConnectionError = res.db_status.detail || 'Connection failed';
      return;
    }
    if (res.db_status) {
      this.erpConnectionOk = true;
      this.erpConnectionError = null;
      return;
    }
    this.erpConnectionOk = true;
    this.erpConnectionError = null;
  }

  private applyErpConnectionFromHttpError(err: HttpErrorResponse): void {
    const msg = this.flattenHttpError(err);
    if (this.looksLikeDbConnectionFailure(msg)) {
      this.erpConnectionOk = false;
      this.erpConnectionError = msg;
    }
  }

  private flattenHttpError(err: HttpErrorResponse): string {
    const e = err.error;
    if (e && typeof e === 'object') {
      const d = (e as { detail?: unknown }).detail;
      if (typeof d === 'object' && d !== null && 'message' in (d as object)) {
        return String((d as { message: unknown }).message);
      }
      if (typeof d === 'string') {
        return d;
      }
    }
    return err.message || 'Request failed';
  }

  private looksLikeDbConnectionFailure(msg: string): boolean {
    const m = msg.toLowerCase();
    return (
      m.includes('mysql') ||
      m.includes('mysqlconnector') ||
      m.includes('1045') ||
      m.includes('1049') ||
      m.includes('2002') ||
      m.includes('2003') ||
      m.includes('lost connection') ||
      (m.includes("can't connect") || m.includes('cannot connect')) ||
      (m.includes('connection') && (m.includes('refused') || m.includes('timed out'))) ||
      (m.includes('access denied') && m.includes('mysql'))
    );
  }

  get rowsCardValue(): number {
    if (this.response?.debug?.rows_returned != null) {
      return this.response.debug.rows_returned;
    }
    return this.response?.data?.length ?? 0;
  }

  get generationCardValue(): string {
    if (this.response?.debug?.generation_path) {
      return this.response.debug.generation_path;
    }
    if (this.response && !this.debug) {
      return 'debug disabled';
    }
    return 'n/a';
  }

  get intentCardValue(): string {
    if (this.response?.debug?.matched_intent) {
      return this.response.debug.matched_intent;
    }
    if (this.response && !this.debug) {
      return 'debug disabled';
    }
    return 'n/a';
  }

  get selectedCopilotLabel(): string {
    return this.response?.debug?.selected_copilot || 'auto';
  }

  get promptHistoryCount(): number {
    return this.history.length;
  }

  private getRowValue(row: Record<string, unknown>, key: string): unknown {
    if (row.hasOwnProperty(key)) return row[key];
    const k = Object.keys(row).find((kk) => kk.toLowerCase() === key.toLowerCase());
    return k ? row[k] : undefined;
  }

  get chartLabels(): string[] {
    const spec = this.response?.chart_spec;
    const data = this.response?.data;
    if (!spec?.x_field || !data?.length) return [];
    return data.map((row) => String(this.getRowValue(row, spec.x_field!) ?? ''));
  }

  get chartData(): ChartDataSets[] {
    const spec = this.response?.chart_spec;
    const data = this.response?.data;
    if (!spec?.y_field || !data?.length) return [];
    const values = data.map((row) => {
      const v = this.getRowValue(row, spec.y_field!);
      return typeof v === 'number' ? v : parseFloat(String(v)) || 0;
    });
    return [{ data: values, label: spec.y_field }];
  }

  getBarWidth(i: number): number {
    const data = this.chartData[0]?.data;
    if (!data?.length) return 0;
    const maxVal = Math.max(...data);
    if (maxVal <= 0) return 0;
    const val = data[i] ?? 0;
    return Math.min(100, (val / maxVal) * 100);
  }

  getChartValue(i: number): number {
    const data = this.chartData[0]?.data;
    return data && i >= 0 && i < data.length ? data[i] : 0;
  }

  get chartDataLength(): number {
    return this.chartData[0]?.data?.length ?? 0;
  }

  get showChart(): boolean {
    return !!(
      this.displayChart &&
      this.response?.chart_spec?.type &&
      this.response?.data?.length &&
      this.chartLabels.length &&
      this.chartData.length
    );
  }
}

