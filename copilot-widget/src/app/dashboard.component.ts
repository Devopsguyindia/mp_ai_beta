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

  private historyKey(): string {
    if (!this.session) {
      return 'copilotPromptHistory';
    }
    return `copilotPromptHistory_${this.session.idcompany}_${this.session.userid || this.session.username || 'user'}`;
  }

  private loadHistory(): void {
    try {
      const raw = localStorage.getItem(this.historyKey());
      this.history = raw ? (JSON.parse(raw) as string[]) : [];
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
}

