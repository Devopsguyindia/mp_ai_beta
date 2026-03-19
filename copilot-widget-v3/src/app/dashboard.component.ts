import { Component, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { AuthService, SessionInfo } from './auth.service';
import { ChatResponse, CopilotApiService } from './copilot-api.service';
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
  displayChart = false;

  loading = false;
  error: any = null;
  response: ChatResponse | null = null;
  history: string[] = [];
  readonly useV3Ask = !!(environment as any).v3AskEnabled;

  suggestedPrompts: string[] = [
    'recent 10 sold items',
    'inventory count and qoh summary for this month',
    'top 10 customers by ltv',
    'artist sales performance for last 90 days',
    'vendor outstanding payables top 20'
  ];

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
      },
      error: (err) => {
        this.error = err;
        this.loading = false;
      }
    });
  }

  logout(): void {
    this.auth.logout();
    this.router.navigate(['/login']);
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

