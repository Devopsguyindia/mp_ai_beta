import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../environments/environment';

export interface ChatRequest {
  idcompany: number;
  question: string;
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
  input_question?: string | null;
  matched_intent?: string | null;
  router_model?: string | null;
  sql_model?: string | null;
  generated_sql?: string | null;
  parameters?: Record<string, any> | null;
  guardrails?: GuardrailResult | null;
  elapsed_ms?: number | null;
  rows_returned?: number | null;
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

