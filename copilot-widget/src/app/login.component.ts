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
          this.error = err?.error?.detail?.message || 'Login failed. Please check credentials.';
          this.loading = false;
        }
      });
  }
}

