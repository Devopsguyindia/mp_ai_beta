import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { AuthService, SessionInfo } from './auth.service';
import {
  ChatResponse,
  CopilotApiService,
  CopilotType,
  MemoryRecentItem,
  ReportSuggestionsResponse
} from './copilot-api.service';
export type ErpModuleParam = 'contact' | 'inventory' | 'sales' | 'reports';

@Component({
  selector: 'app-module-insights-panel',
  templateUrl: './module-insights-panel.component.html',
  styleUrls: ['./module-insights-panel.component.scss']
})
export class ModuleInsightsPanelComponent implements OnInit {
  session: SessionInfo | null = null;
  erpModule: ErpModuleParam = 'contact';

  activeTab: 'chat' | 'history' | 'details' | 'reports' = 'chat';
  showDebug = true;
  displayChart = true;

  question = '';
  loading = false;
  error: string | null = null;
  response: ChatResponse | null = null;

  memoryItems: MemoryRecentItem[] = [];
  memoryLoading = false;

  reportSuggestions: ReportSuggestionsResponse | null = null;
  reportSuggestionsLoading = false;
  reportSuggestionsError: string | null = null;
  reportScope: 'gallery' | 'me' = 'gallery';
  rerunBusyHash: string | null = null;

  /** Phase 1: actions not wired */
  readonly phase2Hint = 'Available in Phase 2';

  constructor(
    private auth: AuthService,
    private api: CopilotApiService,
    private route: ActivatedRoute,
    private router: Router
  ) {}

  ngOnInit(): void {
    this.session = this.auth.getSession();
    if (!this.session?.access_token || !this.session.idcompany) {
      this.router.navigate(['/login']);
      return;
    }
    this.route.paramMap.subscribe((pm) => {
      const m = (pm.get('erpModule') || 'contact') as ErpModuleParam;
      this.erpModule = ['contact', 'inventory', 'sales', 'reports'].includes(m) ? m : 'contact';
      if (this.erpModule === 'reports') {
        this.activeTab = 'reports';
        this.loadReportSuggestions();
      } else {
        this.activeTab = 'chat';
        this.loadMemoryRecent();
      }
    });
  }

  get title(): string {
    const labels: Record<ErpModuleParam, string> = {
      contact: 'Contact AI Insights',
      inventory: 'Inventory AI Insights',
      sales: 'Sales AI Insights',
      reports: 'Reports AI Insights'
    };
    return labels[this.erpModule];
  }

  copilotForModule(): CopilotType {
    switch (this.erpModule) {
      case 'contact':
        return 'customer';
      case 'inventory':
        return 'inventory';
      case 'sales':
        return 'sales';
      default:
        return 'sales';
    }
  }

  suggestedPrompts(): string[] {
    const base = this.staticPromptsForModule();
    const fp = this.response?.follow_up_prompts;
    if (Array.isArray(fp) && fp.length) {
      const merged = [...fp.slice(0, 5), ...base];
      const seen = new Set<string>();
      const out: string[] = [];
      for (const p of merged) {
        const s = String(p).trim();
        if (!s || seen.has(s)) {
          continue;
        }
        seen.add(s);
        out.push(s);
        if (out.length >= 5) {
          break;
        }
      }
      return out;
    }
    return base.slice(0, 5);
  }

  get dataKeysList(): string[] {
    const d = this.response?.data;
    if (!d?.length) {
      return [];
    }
    return Object.keys(d[0] as Record<string, unknown>);
  }

  staticPromptsForModule(): string[] {
    switch (this.erpModule) {
      case 'contact':
        return [
          'How many customers are missing an email address?',
          'How many contacts have no phone number?',
          'Show customers with no primary contact marked.',
          'Top customers by lifetime value',
          'Count inactive customers in the last year'
        ];
      case 'inventory':
        return [
          'How many items are missing category or medium?',
          'How many items have no artist assigned?',
          'Items without a vendor',
          'Total inventory quantity on hand by category',
          'List limited edition items with low stock'
        ];
      case 'sales':
        return [
          'What are the best-selling items by revenue?',
          'Sales by category this year',
          'Top selling artists by volume',
          'Layaway balances outstanding',
          'Monthly sales trend for the last 6 months'
        ];
      default:
        return [];
    }
  }

  loadMemoryRecent(): void {
    if (!this.session?.idcompany) {
      return;
    }
    this.memoryLoading = true;
    const uid =
      this.session.userid != null ? String(this.session.userid) : this.session.token_payload?.userid;
    this.api
      .v3MemoryRecent({
        idcompany: Number(this.session.idcompany),
        access_token: this.session.access_token,
        copilot: this.copilotForModule(),
        user_id: uid != null ? String(uid) : undefined,
        limit: 10
      })
      .subscribe({
        next: (res) => {
          this.memoryItems = res.items || [];
          this.memoryLoading = false;
        },
        error: () => {
          this.memoryItems = [];
          this.memoryLoading = false;
        }
      });
  }

  loadReportSuggestions(): void {
    if (!this.session?.idcompany) {
      return;
    }
    const uid = this.sessionUserIdNumber();
    if (this.reportScope === 'me' && uid === undefined) {
      this.reportSuggestionsError = 'Your session has no user id; switch to Gallery scope.';
      this.reportSuggestions = null;
      return;
    }
    this.reportSuggestionsLoading = true;
    this.reportSuggestionsError = null;
    this.api
      .reportSuggestions({
        idcompany: Number(this.session.idcompany),
        access_token: this.session.access_token,
        user_id: this.reportScope === 'me' && uid !== undefined ? uid : undefined,
        top_n: 5,
        recent_n: 8,
        smart_default_limit: 12,
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
          this.reportSuggestionsError = err.message || 'Could not load report insights.';
        }
      });
  }

  private sessionUserIdNumber(): number | undefined {
    const u = this.session?.userid ?? this.session?.token_payload?.userid;
    if (u == null) {
      return undefined;
    }
    const n = Number(u);
    return Number.isFinite(n) ? n : undefined;
  }

  setReportScope(scope: 'gallery' | 'me'): void {
    this.reportScope = scope;
    this.loadReportSuggestions();
  }

  submit(): void {
    if (!this.question.trim() || !this.session || this.erpModule === 'reports') {
      return;
    }
    this.loading = true;
    this.error = null;
    this.response = null;
    const uid =
      this.session.userid != null ? String(this.session.userid) : this.session.token_payload?.userid;
    this.api
      .askV3({
        idcompany: Number(this.session.idcompany),
        access_token: this.session.access_token,
        question: this.question.trim(),
        copilot: this.copilotForModule(),
        include_chart: this.displayChart,
        debug: this.showDebug,
        erp_module: this.erpModule as 'contact' | 'inventory' | 'sales',
        strict_module_scope: true,
        user_id: uid != null ? String(uid) : undefined
      })
      .subscribe({
        next: (res) => {
          this.response = res;
          this.loading = false;
          this.loadMemoryRecent();
        },
        error: (err: HttpErrorResponse) => {
          this.loading = false;
          this.error = err.error?.message || err.message || 'Request failed';
        }
      });
  }

  usePrompt(p: string): void {
    this.question = p;
    this.submit();
  }

  close(): void {
    this.router.navigate(['/dashboard']);
  }

  get intentLabel(): string {
    const d = this.response?.debug;
    return (d?.routed_intent || d?.matched_intent || 'n/a') as string;
  }

  get rowsCardValue(): number {
    if (this.response?.debug?.rows_returned != null) {
      return this.response.debug.rows_returned;
    }
    return this.response?.data?.length ?? 0;
  }

  get generationCardValue(): string {
    return this.response?.debug?.generation_path || 'n/a';
  }

  getRowValue(row: Record<string, unknown>, key: string): unknown {
    if (row.hasOwnProperty(key)) {
      return row[key];
    }
    const k = Object.keys(row).find((kk) => kk.toLowerCase() === key.toLowerCase());
    return k ? row[k] : undefined;
  }

  get chartLabels(): string[] {
    const spec = this.response?.chart_spec;
    const data = this.response?.data;
    if (!spec?.x_field || !data?.length) {
      return [];
    }
    return data.map((row) => String(this.getRowValue(row, spec.x_field!) ?? ''));
  }

  get chartValues(): number[] {
    const spec = this.response?.chart_spec;
    const data = this.response?.data;
    if (!spec?.y_field || !data?.length) {
      return [];
    }
    return data.map((row) => {
      const v = this.getRowValue(row, spec.y_field!);
      return typeof v === 'number' ? v : parseFloat(String(v)) || 0;
    });
  }

  getBarWidth(i: number): number {
    const data = this.chartValues;
    if (!data.length) {
      return 0;
    }
    const maxVal = Math.max(...data);
    if (maxVal <= 0) {
      return 0;
    }
    return Math.min(100, ((data[i] ?? 0) / maxVal) * 100);
  }

  get showBarChart(): boolean {
    return !!(
      this.displayChart &&
      this.response?.chart_spec?.type &&
      this.response.chart_spec.type !== 'pie' &&
      this.response?.data?.length &&
      this.chartLabels.length &&
      this.chartValues.length
    );
  }

  get showDonutChart(): boolean {
    return !!(
      this.displayChart &&
      this.response?.chart_spec?.type === 'pie' &&
      this.chartLabels.length &&
      this.chartValues.length
    );
  }

  get donutGradient(): string {
    const values = this.chartValues;
    const sum = values.reduce((a, b) => a + b, 0);
    if (sum <= 0) {
      return 'transparent';
    }
    const colors = ['#7c5cff', '#3d8bfd', '#22c55e', '#f59e0b', '#ec4899', '#94a3b8'];
    let start = 0;
    const parts: string[] = [];
    values.forEach((v, i) => {
      const pct = (v / sum) * 100;
      const end = start + pct;
      parts.push(`${colors[i % colors.length]} ${start}% ${end}%`);
      start = end;
    });
    return `conic-gradient(${parts.join(', ')})`;
  }

  get donutLegend(): { label: string; value: number; color: string }[] {
    const labels = this.chartLabels;
    const values = this.chartValues;
    const colors = ['#7c5cff', '#3d8bfd', '#22c55e', '#f59e0b', '#ec4899', '#94a3b8'];
    return labels.map((label, i) => ({
      label,
      value: values[i] ?? 0,
      color: colors[i % colors.length]
    }));
  }

  rerunReport(fd: string | null | undefined, hash: string, rollEndDates: boolean): void {
    if (!fd?.trim() || !this.session?.access_token) {
      return;
    }
    this.rerunBusyHash = hash;
    this.api
      .rerunReport({
        access_token: this.session.access_token,
        filter_data: fd.trim(),
        roll_end_dates: rollEndDates
      })
      .subscribe({
        next: (resp) => {
          this.rerunBusyHash = null;
          const blob = resp.body;
          if (!blob || blob.size === 0) {
            this.reportSuggestionsError = 'Re-run returned an empty response.';
            return;
          }
          const url = URL.createObjectURL(blob);
          window.open(url, '_blank', 'noopener,noreferrer');
          setTimeout(() => URL.revokeObjectURL(url), 120000);
        },
        error: () => {
          this.rerunBusyHash = null;
          this.reportSuggestionsError = 'Re-run failed.';
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
}
