import { Component } from '@angular/core';
import { Router } from '@angular/router';
import { AuthService } from './auth.service';

@Component({
  selector: 'app-login',
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.scss']
})
export class LoginComponent {
  txt_company = '';
  txt_username = '';
  txt_password = '';

  loading = false;
  error = '';

  constructor(private auth: AuthService, private router: Router) {}

  private resolveLoginError(err: any): string {
    const detail = err?.error?.detail;
    const upstreamBody = detail?.upstream_body;
    if (typeof upstreamBody === 'string' && upstreamBody.trim()) {
      try {
        const parsed = JSON.parse(upstreamBody.trim());
        if (parsed?.message) {
          return String(parsed.message);
        }
      } catch {
        // ignore parse issues and continue fallbacks
      }
    }
    return detail?.message || err?.error?.message || 'Login failed. Please check credentials.';
  }

  submit(): void {
    if (!this.txt_company || !this.txt_username || !this.txt_password) {
      this.error = 'Please enter company, username, and password.';
      return;
    }

    this.loading = true;
    this.error = '';
    this.auth
      .login({
        txt_company: this.txt_company,
        txt_username: this.txt_username,
        txt_password: this.txt_password
      })
      .subscribe({
        next: (res) => {
          this.auth.saveSession(res.session);
          this.loading = false;
          this.router.navigate(['/dashboard']);
        },
        error: (err) => {
          this.error = this.resolveLoginError(err);
          this.loading = false;
        }
      });
  }
}

