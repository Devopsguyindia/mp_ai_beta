import { Component, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { AuthService, SessionInfo } from './auth.service';
import { ChatResponse, CopilotApiService } from './copilot-api.service';

@Component({
  selector: 'app-dashboard',
  templateUrl: './dashboard.component.html',
  styleUrls: ['./dashboard.component.scss']
})
export class DashboardComponent implements OnInit {
  session: SessionInfo | null = null;
  question = '';
  debug = true;

  loading = false;
  error: any = null;
  response: ChatResponse | null = null;
  history: string[] = [];

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

    this.api
      .chat({
        idcompany: Number(this.session.idcompany),
        access_token: this.session.access_token,
        question: this.question.trim(),
        debug: this.debug
      })
      .subscribe({
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
}

