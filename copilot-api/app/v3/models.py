from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ..sql_guardrails import GuardrailResult


CopilotType = Literal["sales", "inventory", "customer", "artist", "vendor"]


class V3AskRequest(BaseModel):
    idcompany: int = Field(..., ge=1)
    access_token: str | None = None
    question: str = Field(..., min_length=1, max_length=4000)
    copilot: CopilotType | None = None
    include_chart: bool = False
    debug: bool = False


class PlannerOutput(BaseModel):
    copilot: CopilotType
    intent_hint: str
    output_type: Literal["table", "kpi", "trend"]
    needs_chart: bool
    confidence: float


class MemoryContext(BaseModel):
    recent_questions: list[str] = []
    recent_sql: list[str] = []
    reused: bool = False


class SchemaContext(BaseModel):
    relation_candidates: list[str] = []
    context_chunks: list[str] = []


class SQLGenerationOutput(BaseModel):
    intent: str
    sql: str
    params: dict[str, Any] = {}
    requested_limit: int | None = None
    applied_limit: int | None = None
    window_label: str | None = None
    generation_path: str = "llm"
    generation_error: str | None = None


class ValidationOutput(BaseModel):
    ok: bool
    sql: str
    params: dict[str, Any] = {}
    guardrails: GuardrailResult
    retry_attempted: bool = False
    retry_success: bool = False
    generation_error: str | None = None


class InsightItem(BaseModel):
    title: str
    detail: str


class ChartSpec(BaseModel):
    type: Literal["bar", "line", "pie"] | None = None
    x_field: str | None = None
    y_field: str | None = None
    title: str | None = None


class AgentTrace(BaseModel):
    planner: dict[str, Any] | None = None
    memory: dict[str, Any] | None = None
    schema: dict[str, Any] | None = None
    sql: dict[str, Any] | None = None
    validator: dict[str, Any] | None = None
    execution: dict[str, Any] | None = None
    insight: dict[str, Any] | None = None
    chart: dict[str, Any] | None = None


class V3DebugInfo(BaseModel):
    request_id: str
    server_ts_utc: str
    resolved_idcompany: int
    selected_copilot: CopilotType
    routed_intent: str
    generation_path: str
    generation_error: str | None = None
    guardrails: GuardrailResult
    retry_attempted: bool = False
    retry_success: bool = False
    rendered_sql_preview: str | None = None
    elapsed_ms: int
    rows_returned: int
    trace: AgentTrace | None = None


class DbConnectionStatus(BaseModel):
    """Present when a MySQL query completed successfully for this request (implies connectivity OK)."""

    ok: bool = True
    detail: str = "MySQL connection succeeded; read-only query completed."
    database: str | None = Field(
        default=None,
        description="MYSQL_DATABASE name (informational only; no credentials).",
    )


class V3AskResponse(BaseModel):
    answer: str
    data: list[dict[str, Any]] = []
    insights: list[InsightItem] = []
    follow_up_prompts: list[str] = []
    chart_spec: ChartSpec | None = None
    confidence: float = 0.0
    assumptions: list[str] = []
    row_limit_notice: str | None = Field(
        default=None,
        description="When MYSQL_MAX_ROWS caps returned rows; UI should warn so trends are not misread.",
    )
    db_status: DbConnectionStatus | None = None
    debug: V3DebugInfo | None = None
