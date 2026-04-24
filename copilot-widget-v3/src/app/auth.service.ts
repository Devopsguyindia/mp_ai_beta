import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../environments/environment';

export interface SessionInfo {
  access_token: string;
  token_payload: Record<string, any>;
  idcompany: number | null;
  /** Server-issued UUID; used for auth audit logout correlation. */
  auth_session_id?: string | null;
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

/** Parent iframe postMessage contract (see docs/ERP_MODULE_INSIGHTS_INTEGRATION_GUIDE.md). */
export interface CopilotAuthPostMessage {
  type: 'copilot-auth';
  access_token: string;
  idcompany: number;
  user_id?: string | null;
  /** After session is applied, navigate here if the user is on /login (e.g. /module-insights/contact or /showcase/inventory?itemId=…). */
  redirect_to?: string | null;
}

const SESSION_KEY = 'copilotSession';

function decodeJwtPayloadUnverified(token: string): Record<string, unknown> {
  try {
    const parts = token.split('.');
    if (parts.length < 2) {
      return {};
    }
    let payload = parts[1];
    payload += '='.repeat((4 - (payload.length % 4)) % 4);
    const decoded = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
    const data = JSON.parse(decoded) as unknown;
    return typeof data === 'object' && data !== null && !Array.isArray(data)
      ? (data as Record<string, unknown>)
      : {};
  } catch {
    return {};
  }
}

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

  /**
   * V3 / Showcase: show client debug UI and send debug=true only for login ``jesse``
   * (case-insensitive), matching server ``is_jesse_debug_viewer``.
   */
  canShowClientDebug(session: SessionInfo | null): boolean {
    if (!session) {
      return false;
    }
    const ids: string[] = [];
    const uid = session.userid?.trim();
    if (uid) {
      ids.push(uid.toLowerCase());
    }
    const p = session.token_payload || {};
    for (const key of ['userid', 'user_id', 'sub', 'username', 'firstname', 'fullname'] as const) {
      const v = p[key];
      if (v != null && String(v).trim()) {
        ids.push(String(v).trim().toLowerCase());
      }
    }
    return ids.includes('jesse');
  }

  logout(): void {
    localStorage.removeItem(SESSION_KEY);
  }

  /**
   * Apply session from ERP parent iframe postMessage (same storage shape as login).
   * Returns true if session was saved; false if payload invalid.
   */
  applyEmbeddedSession(payload: CopilotAuthPostMessage): boolean {
    const token = (payload.access_token || '').trim();
    const idcompany = Number(payload.idcompany);
    if (!token || !Number.isFinite(idcompany) || idcompany < 1) {
      return false;
    }
    const token_payload = decodeJwtPayloadUnverified(token) as Record<string, any>;
    const uid =
      payload.user_id != null && String(payload.user_id).trim() !== ''
        ? String(payload.user_id).trim()
        : (token_payload['userid'] ?? token_payload['user_id'] ?? token_payload['sub'] ?? null);
    const session: SessionInfo = {
      access_token: token,
      token_payload,
      idcompany,
      userid: uid != null ? String(uid) : null,
      username: token_payload['username'] != null ? String(token_payload['username']) : null,
      firstname: token_payload['firstname'] != null ? String(token_payload['firstname']) : null,
      lastname: token_payload['lastname'] != null ? String(token_payload['lastname']) : null,
      company_name: token_payload['company_name'] != null ? String(token_payload['company_name']) : null,
      role_name: token_payload['role_name'] != null ? String(token_payload['role_name']) : null,
      role_id: token_payload['role'] != null ? String(token_payload['role']) : null,
      idcompany_location: token_payload['idcompany_location'] != null ? String(token_payload['idcompany_location']) : null,
      location_name: token_payload['location_name'] != null ? String(token_payload['location_name']) : null,
    };
    this.saveSession(session);
    return true;
  }
}

