import { Component, OnDestroy, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { environment } from '../environments/environment';
import { AuthService, CopilotAuthPostMessage } from './auth.service';

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss']
})
export class AppComponent implements OnInit, OnDestroy {
  title = 'copilot-widget';

  private messageListener: ((event: MessageEvent) => void) | null = null;

  constructor(private auth: AuthService, private router: Router) {}

  ngOnInit(): void {
    const allow = environment.parentOriginsAllowlist || [];
    if (allow.length === 0) {
      return;
    }
    const normalized = allow.map((o) => o.trim().replace(/\/$/, ''));
    this.messageListener = (event: MessageEvent) => {
      const origin = String(event.origin || '').replace(/\/$/, '');
      if (!normalized.includes(origin)) {
        return;
      }
      const data = event.data;
      if (!data || typeof data !== 'object') {
        return;
      }
      const p = data as Partial<CopilotAuthPostMessage>;
      if (p.type !== 'copilot-auth') {
        return;
      }
      if (!p.access_token || p.idcompany == null) {
        return;
      }
      const payload: CopilotAuthPostMessage = {
        type: 'copilot-auth',
        access_token: String(p.access_token),
        idcompany: typeof p.idcompany === 'number' ? p.idcompany : Number(p.idcompany),
        user_id: p.user_id,
        redirect_to: p.redirect_to
      };
      const ok = this.auth.applyEmbeddedSession(payload);
      if (!ok) {
        return;
      }
      if (this.router.url.includes('login')) {
        const raw = (payload.redirect_to || '').trim();
        const to = raw ? (raw.startsWith('/') ? raw : '/' + raw) : '/dashboard';
        this.router.navigateByUrl(to);
      }
    };
    window.addEventListener('message', this.messageListener);
  }

  ngOnDestroy(): void {
    if (this.messageListener) {
      window.removeEventListener('message', this.messageListener);
      this.messageListener = null;
    }
  }
}
