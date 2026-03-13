from __future__ import annotations

import os
import re
import time
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .llm_nl2sql import generate_query_with_llm
from .nl2sql_engine import generate_query
from .sql_guardrails import GuardrailResult, validate_select_sql
from .sql_runner import QueryResult, run_select_query


load_dotenv()

app = FastAPI(title="Copilot API (V1, read-only)", version="0.1.0")

cors_origins_raw = os.getenv(
    "CORS_ALLOW_ORIGINS",
    "http://localhost:4200,http://127.0.0.1:4200",
)
cors_allow_origins = [o.strip() for o in cors_origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    idcompany: int = Field(..., ge=1, description="Tenant/company ID (gallery)")
    question: str = Field(..., min_length=1, max_length=4000)
    debug: bool = Field(False, description="If true, include SQL and validation details")


class DebugInfo(BaseModel):
    input_question: str | None = None
    matched_intent: str | None = None
    router_model: str | None = None
    sql_model: str | None = None
    generated_sql: str | None = None
    rendered_sql_preview: str | None = None
    parameters: dict[str, Any] | None = None
    guardrails: GuardrailResult | None = None
    elapsed_ms: int | None = None
    rows_returned: int | None = None
    requested_limit: int | None = None
    applied_limit: int | None = None
    window_label: str | None = None
    generation_path: str | None = None
    generation_error: str | None = None


class ChatResponse(BaseModel):
    answer: str
    data: list[dict[str, Any]] | None = None
    debug: DebugInfo | None = None


def _to_sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    # basic display escaping for debug preview only
    s = str(value).replace("'", "''")
    return f"'{s}'"


def _render_sql_preview(sql: str, params: dict[str, Any]) -> str:
    """
    Build a best-effort SQL preview with placeholders replaced by values.
    This is only for observability/debugging; execution remains parameterized.
    """
    rendered = sql
    for key, value in params.items():
        pattern = re.compile(rf"%\({re.escape(key)}\)s")
        rendered = pattern.sub(_to_sql_literal(value), rendered)
    return rendered


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    start = time.time()

    generation_path = "llm"
    generation_error = None
    query, generation_error = generate_query_with_llm(req.question)
    if query is None:
        generation_path = "deterministic_fallback"
        query = generate_query(req.question)

    sql = query.sql
    matched_intent = query.intent
    params = {**query.params, "idcompany": req.idcompany}

    guard = validate_select_sql(sql=sql, required_idcompany_param="idcompany")
    if not guard.ok:
        raise HTTPException(status_code=400, detail={"error": "sql_blocked", "guardrails": guard.model_dump()})

    try:
        max_rows = int(os.getenv("MYSQL_MAX_ROWS", "200"))
        timeout_ms = int(os.getenv("MYSQL_QUERY_TIMEOUT_MS", "8000"))
        result: QueryResult = run_select_query(sql=sql, params=params, max_rows=max_rows, timeout_ms=timeout_ms)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "query_failed", "message": str(e)})

    elapsed_ms = int((time.time() - start) * 1000)

    answer = "Here are the results from your ERP data (read-only)."
    debug = None
    if req.debug:
        debug = DebugInfo(
            input_question=req.question,
            matched_intent=matched_intent,
            router_model=os.getenv("OPENAI_MODEL_ROUTER"),
            sql_model=os.getenv("OPENAI_MODEL_SQL"),
            generated_sql=sql,
            rendered_sql_preview=_render_sql_preview(sql, params),
            parameters=params,
            guardrails=guard,
            elapsed_ms=elapsed_ms,
            rows_returned=len(result.rows),
            requested_limit=query.requested_limit,
            applied_limit=query.applied_limit,
            window_label=query.window_label,
            generation_path=generation_path,
            generation_error=generation_error,
        )

    return ChatResponse(answer=answer, data=result.rows, debug=debug)

