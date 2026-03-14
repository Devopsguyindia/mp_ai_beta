import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
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
}

@Injectable({ providedIn: 'root' })
export class CopilotApiService {
  private readonly baseUrl = environment.copilotApiBaseUrl;

  constructor(private http: HttpClient) {}

  chat(req: ChatRequest): Observable<ChatResponse> {
    return this.http.post<ChatResponse>(`${this.baseUrl}/chat`, req);
  }
}

