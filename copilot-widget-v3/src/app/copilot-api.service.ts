import { Injectable } from '@angular/core';
import { HttpClient, HttpResponse } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../environments/environment';

export type CopilotType = 'sales' | 'inventory' | 'customer' | 'artist' | 'vendor';

export interface ChatRequest {
  idcompany: number;
  access_token?: string;
  question: string;
  copilot?: CopilotType;
  debug?: boolean;
}

export interface V3AskRequest extends ChatRequest {
  include_chart?: boolean;
}

export interface GuardrailViolation {
  code: string;
  message: string;
}

export interface GuardrailResult {
  ok: boolean;
  normalized_sql?: string | null;
  violations: GuardrailViolation[];
}

export interface DebugInfo {
  request_id?: string | null;
  server_ts_utc?: string | null;
  input_question?: string | null;
  matched_intent?: string | null;
  router_model?: string | null;
  sql_model?: string | null;
  generated_sql?: string | null;
  rendered_sql_preview?: string | null;
  parameters?: Record<string, any> | null;
  guardrails?: GuardrailResult | null;
  elapsed_ms?: number | null;
  rows_returned?: number | null;
  requested_limit?: number | null;
  applied_limit?: number | null;
  window_label?: string | null;
  generation_path?: string | null;
  generation_error?: string | null;
  retry_attempted?: boolean | null;
  retry_success?: boolean | null;
  resolved_idcompany?: number | null;
  selected_copilot?: CopilotType | null;
  contract_guardrails?: Record<string, any> | null;
}

export interface ChatResponse {
  answer: string;
  data?: Array<Record<string, any>> | null;
  debug?: DebugInfo | null;
  /** Present when the server capped rows at MYSQL_MAX_ROWS (default 200). */
  row_limit_notice?: string | null;
  /** Present when MySQL query succeeded for this request. */
  db_status?: {
    ok?: boolean;
    detail?: string;
    database?: string | null;
  } | null;
  insights?: Array<{ title: string; detail: string }> | null;
  follow_up_prompts?: string[] | null;
  chart_spec?: {
    type?: 'bar' | 'line' | 'pie' | null;
    x_field?: string | null;
    y_field?: string | null;
    title?: string | null;
  } | null;
  confidence?: number | null;
  assumptions?: string[] | null;
}

export interface ReportSuggestionsRequest {
  idcompany: number;
  access_token?: string;
  user_id?: number | null;
  top_n?: number;
  recent_n?: number;
  smart_default_limit?: number;
  truncate_filter_data?: boolean;
  filter_data_max_chars?: number;
}

export interface ReportTopItem {
  report_id: number;
  total_usage: number;
  report_name?: string | null;
  name_source?: string | null;
}

export interface ReportRecentItem {
  report_id: number;
  user_id: number;
  usage_count: number;
  last_used?: string | null;
  filter_hash: string;
  filter_data?: string | null;
  filter_data_truncated?: boolean;
  report_name?: string | null;
}

export interface ReportSmartDefaultItem {
  report_id: number;
  filter_hash: string;
  usage_sum: number;
  filter_data?: string | null;
  filter_data_truncated?: boolean;
  report_name?: string | null;
}

export interface ReportPredictHintItem {
  report_id: number;
  report_name?: string | null;
  weekday: number;
  weekday_label: string;
  run_count: number;
}

export interface ReportRerunRequest {
  access_token: string;
  filter_data: string;
  /** If true (default), server sets end-date fields to today. Set false for exact historical re-run (Recent). */
  roll_end_dates?: boolean;
}

export interface AuthLogoutRequest {
  auth_session_id: string;
  idcompany?: number;
  userid?: string | number;
  username?: string;
}

export interface ReportSuggestionsResponse {
  ok: boolean;
  idcompany: number;
  scoped_to_user_id?: number | null;
  top_reports: ReportTopItem[];
  recent_runs: ReportRecentItem[];
  smart_defaults: ReportSmartDefaultItem[];
  predict_hints: ReportPredictHintItem[];
  warnings?: string[];
}

@Injectable({ providedIn: 'root' })
export class CopilotApiService {
  private readonly baseUrl = environment.copilotApiBaseUrl;

  constructor(private http: HttpClient) {}

  chat(req: ChatRequest): Observable<ChatResponse> {
    return this.http.post<ChatResponse>(`${this.baseUrl}/chat`, req);
  }

  askV3(req: V3AskRequest): Observable<ChatResponse> {
    return this.http.post<ChatResponse>(`${this.baseUrl}/v3/ask`, req);
  }

  reportSuggestions(req: ReportSuggestionsRequest): Observable<ReportSuggestionsResponse> {
    return this.http.post<ReportSuggestionsResponse>(`${this.baseUrl}/reports/suggestions`, req);
  }

  /** Proxied GET to MP generateReport; returns file/HTML body as blob. */
  rerunReport(req: ReportRerunRequest): Observable<HttpResponse<Blob>> {
    return this.http.post(`${this.baseUrl}/reports/rerun`, req, {
      responseType: 'blob',
      observe: 'response'
    });
  }

  /** Records logout in server audit table (best-effort). */
  authLogout(req: AuthLogoutRequest): Observable<HttpResponse<string>> {
    return this.http.post(`${this.baseUrl}/auth/logout`, req, {
      observe: 'response',
      responseType: 'text'
    });
  }
}

