import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../environments/environment';

export interface SessionInfo {
  access_token: string;
  token_payload: Record<string, any>;
  idcompany: number | null;
  company_name?: string | null;
  username?: string | null;
  firstname?: string | null;
  lastname?: string | null;
  role_name?: string | null;
  role_id?: string | null;
  userid?: string | null;
  idcompany_location?: string | null;
  location_name?: string | null;
}

export interface LoginResponse {
  status: boolean;
  message: string;
  session: SessionInfo;
}

const SESSION_KEY = 'copilotSession';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly baseUrl = environment.copilotApiBaseUrl;

  constructor(private http: HttpClient) {}

  login(payload: {
    txt_company: string;
    txt_username: string;
    txt_password: string;
  }): Observable<LoginResponse> {
    return this.http.post<LoginResponse>(`${this.baseUrl}/auth/login`, payload);
  }

  saveSession(session: SessionInfo): void {
    localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  }

  getSession(): SessionInfo | null {
    try {
      const raw = localStorage.getItem(SESSION_KEY);
      if (!raw) {
        return null;
      }
      return JSON.parse(raw) as SessionInfo;
    } catch {
      return null;
    }
  }

  isAuthenticated(): boolean {
    const s = this.getSession();
    return !!(s && s.access_token && s.idcompany);
  }

  logout(): void {
    localStorage.removeItem(SESSION_KEY);
  }
}

