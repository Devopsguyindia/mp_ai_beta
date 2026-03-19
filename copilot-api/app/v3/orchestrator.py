from __future__ import annotations

import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from ..sql_runner import run_select_query
from .agents.chart_agent import build_chart_spec
from .agents.insight_agent import build_insights
from .agents.memory_agent import fetch_memory_context
from .agents.planner_agent import plan_question
from .agents.schema_agent import retrieve_schema_context
from .agents.sql_agent import generate_sql
from .agents.validator_agent import validate_with_retry
from .memory.log_store import append_memory_event
from .models import AgentTrace, V3AskRequest, V3AskResponse, V3DebugInfo
from .rollout import evaluate_rollout_gates


def _to_sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value).replace("'", "''")
    return f"'{s}'"


def _render_sql_preview(sql: str, params: dict[str, Any]) -> str:
    rendered = sql
    for key, value in params.items():
        pattern = re.compile(rf"%\({re.escape(key)}\)s")
        rendered = pattern.sub(_to_sql_literal(value), rendered)
    return rendered


def run_v3_ask(*, req: V3AskRequest, resolved_idcompany: int) -> V3AskResponse:
    start = time.time()
    request_id = str(uuid.uuid4())
    server_ts_utc = datetime.now(timezone.utc).isoformat()

    planner = plan_question(question=req.question, requested_copilot=req.copilot)
    memory = fetch_memory_context(idcompany=resolved_idcompany, question=req.question, limit=6)
    schema = retrieve_schema_context(question=req.question, copilot=planner.copilot)
    sql_out = generate_sql(
        question=req.question,
        copilot=planner.copilot,
        schema_context=schema.context_chunks,
        memory_questions=memory.recent_questions,
    )
    validated = validate_with_retry(
        question=req.question,
        copilot=planner.copilot,
        sql_output=sql_out,
        schema_context=schema.context_chunks,
        idcompany_param="idcompany",
        max_retries=int(os.getenv("V3_VALIDATOR_MAX_RETRIES", "1")),
    )
    if not validated.ok:
        raise ValueError(f"v3_validation_failed: {validated.guardrails.model_dump()}")

    params = {**validated.params, "idcompany": resolved_idcompany}
    max_rows = int(os.getenv("MYSQL_MAX_ROWS", "200"))
    timeout_ms = int(os.getenv("MYSQL_QUERY_TIMEOUT_MS", "8000"))
    result = run_select_query(sql=validated.sql, params=params, max_rows=max_rows, timeout_ms=timeout_ms)

    insights = build_insights(
        rows=result.rows,
        question=req.question,
        sql=validated.sql,
        intent=sql_out.intent,
        copilot=planner.copilot,
    )
    chart_enabled = req.include_chart and os.getenv("V3_CHART_AGENT_ENABLED", "0") in {"1", "true", "TRUE", "yes", "YES"}
    chart_spec = build_chart_spec(rows=result.rows, question=req.question, enabled=chart_enabled)

    append_memory_event(
        {
            "request_id": request_id,
            "ts_utc": server_ts_utc,
            "idcompany": resolved_idcompany,
            "question": req.question,
            "copilot": planner.copilot,
            "intent": sql_out.intent,
            "sql": validated.sql,
            "rows_returned": len(result.rows),
        }
    )

    elapsed_ms = int((time.time() - start) * 1000)
    rollout = evaluate_rollout_gates(confidence=planner.confidence, rows_returned=len(result.rows))
    if not rollout.ok:
        raise ValueError(";".join(rollout.warnings) or "v3_rollout_gate_failed")
    trace = AgentTrace(
        planner=planner.model_dump(),
        memory=memory.model_dump(),
        schema=schema.model_dump(),
        sql=sql_out.model_dump(),
        validator=validated.model_dump(),
        execution={"rows_returned": len(result.rows)},
        insight={"count": len(insights)},
        chart=chart_spec.model_dump() if chart_spec else {"enabled": chart_enabled, "created": False},
    )
    debug = None
    if req.debug:
        debug = V3DebugInfo(
            request_id=request_id,
            server_ts_utc=server_ts_utc,
            resolved_idcompany=resolved_idcompany,
            selected_copilot=planner.copilot,
            routed_intent=planner.intent_hint,
            generation_path=sql_out.generation_path,
            generation_error=validated.generation_error,
            guardrails=validated.guardrails,
            retry_attempted=validated.retry_attempted,
            retry_success=validated.retry_success,
            rendered_sql_preview=_render_sql_preview(validated.sql, params),
            elapsed_ms=elapsed_ms,
            rows_returned=len(result.rows),
            trace=trace,
        )

    assumptions = [
        "Read-only execution with tenant filtering is enforced.",
    ]
    assumptions.extend(rollout.warnings)
    answer = "Here are the results from Masterpiece data."
    data = result.rows if result.rows else [{"message": "I am sorry, no data matched to your question."}]
    return V3AskResponse(
        answer=answer,
        data=data,
        insights=insights,
        chart_spec=chart_spec,
        confidence=planner.confidence,
        assumptions=assumptions,
        debug=debug,
    )
