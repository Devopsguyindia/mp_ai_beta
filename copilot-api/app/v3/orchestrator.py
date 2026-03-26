from __future__ import annotations

import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import mysql.connector

from ..llm_nl2sql import generate_query_with_llm
from ..sql_guardrails import validate_select_sql
from ..sql_runner import run_select_query
from .agents.chart_agent import build_chart_spec
from .agents.insight_agent import build_insights
from .agents.memory_agent import fetch_memory_context
from .agents.planner_agent import plan_question
from .agents.schema_agent import retrieve_schema_context
from .agents.sql_agent import generate_sql
from .agents.validator_agent import validate_with_retry
from .memory.log_store import append_memory_event
from .models import AgentTrace, SQLGenerationOutput, V3AskRequest, V3AskResponse, V3DebugInfo, ValidationOutput
from .rollout import evaluate_rollout_gates
from .sql_schema_check import apply_registry_column_synonyms, validate_sql_columns_against_registry


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


def _schema_column_check_enabled() -> bool:
    return os.getenv("V3_SCHEMA_COLUMN_CHECK", "1") in {"1", "true", "TRUE", "yes", "YES"}


def _is_unknown_column_db_error(e: BaseException) -> bool:
    if isinstance(e, mysql.connector.Error):
        if getattr(e, "errno", None) == 1054:
            return True
    msg = str(e).lower()
    return "unknown column" in msg and ("1054" in str(e) or "42s22" in msg.lower())


def run_v3_ask(*, req: V3AskRequest, resolved_idcompany: int) -> V3AskResponse:
    start = time.time()
    request_id = str(uuid.uuid4())
    server_ts_utc = datetime.now(timezone.utc).isoformat()

    planner = plan_question(question=req.question, requested_copilot=req.copilot)
    memory = fetch_memory_context(idcompany=resolved_idcompany, question=req.question, limit=6)
    schema = retrieve_schema_context(question=req.question, copilot=planner.copilot)
    schema_text = "\n".join(schema.context_chunks)

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

    schema_repair_attempted = False
    if _schema_column_check_enabled():
        col_ok, viol = validate_sql_columns_against_registry(validated.sql)
        if not col_ok:
            schema_repair_attempted = True
            repaired, repair_err = generate_query_with_llm(
                req.question,
                copilot=planner.copilot,
                schema_from_context=schema_text or None,
                error_context={"schema_column_violations": viol, "previous_sql": validated.sql},
            )
            if repaired is None:
                raise ValueError(f"v3_schema_column_invalid: {viol}")
            sql_out = SQLGenerationOutput(
                intent=repaired.intent,
                sql=repaired.sql,
                params=dict(repaired.params or {}),
                requested_limit=repaired.requested_limit,
                applied_limit=repaired.applied_limit,
                window_label=repaired.window_label,
                generation_path="llm_schema_repair",
                generation_error=repair_err,
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
                raise ValueError(f"v3_validation_failed_after_schema_repair: {validated.guardrails.model_dump()}")
            ok2, viol2 = validate_sql_columns_against_registry(validated.sql)
            if not ok2:
                raise ValueError(f"v3_schema_column_invalid_after_repair: {viol2}")

    params = {**validated.params, "idcompany": resolved_idcompany}
    max_rows = int(os.getenv("MYSQL_MAX_ROWS", "200"))
    timeout_ms = int(os.getenv("MYSQL_QUERY_TIMEOUT_MS", "8000"))
    max_db_retries = int(os.getenv("V3_MAX_DB_RETRIES", "1"))

    result = None
    db_retry_count = 0
    executed_sql = ""
    for attempt in range(max_db_retries + 1):
        executed_sql = apply_registry_column_synonyms(validated.sql)
        try:
            result = run_select_query(
                sql=executed_sql, params=params, max_rows=max_rows, timeout_ms=timeout_ms
            )
            break
        except Exception as e:
            if not _is_unknown_column_db_error(e) or attempt >= max_db_retries:
                raise
            db_retry_count += 1
            repaired, repair_err = generate_query_with_llm(
                req.question,
                copilot=planner.copilot,
                schema_from_context=schema_text or None,
                error_context={"previous_sql": validated.sql, "db_error": str(e)},
            )
            if repaired is None:
                raise
            guard = validate_select_sql(sql=repaired.sql, required_idcompany_param="idcompany")
            if not guard.ok:
                raise ValueError(
                    f"v3_db_repair_guardrail_failed: {guard.model_dump()}; original_db_error={e!s}"
                )
            if _schema_column_check_enabled():
                ok_col, viol_col = validate_sql_columns_against_registry(repaired.sql)
                if not ok_col:
                    raise ValueError(
                        f"v3_schema_column_invalid_after_db_repair: {viol_col}; original_db_error={e!s}"
                    )
            sql_out = SQLGenerationOutput(
                intent=repaired.intent,
                sql=repaired.sql,
                params=dict(repaired.params or {}),
                requested_limit=repaired.requested_limit,
                applied_limit=repaired.applied_limit,
                window_label=repaired.window_label,
                generation_path="llm_db_repair",
                generation_error=repair_err,
            )
            validated = ValidationOutput(
                ok=True,
                sql=repaired.sql,
                params=dict(repaired.params or {}),
                guardrails=guard,
                retry_attempted=True,
                retry_success=True,
                generation_error=repair_err,
            )
            params = {**validated.params, "idcompany": resolved_idcompany}

    if result is None:
        raise RuntimeError("v3_ask: no query result")

    row_limit_notice: str | None = None
    if result.truncated:
        row_limit_notice = (
            f"Only the first {max_rows} rows are shown (Copilot default row limit). "
            "More rows matched your question but were not returned—narrow the date range or add filters "
            "so charts and totals are not misleading."
        )

    insights, follow_up_prompts = build_insights(
        rows=result.rows,
        question=req.question,
        sql=executed_sql,
        intent=sql_out.intent,
        copilot=planner.copilot,
    )
    chart_enabled = req.include_chart and os.getenv("V3_CHART_AGENT_ENABLED", "1") in {"1", "true", "TRUE", "yes", "YES"}
    chart_spec = build_chart_spec(rows=result.rows, question=req.question, enabled=chart_enabled)

    append_memory_event(
        {
            "request_id": request_id,
            "ts_utc": server_ts_utc,
            "idcompany": resolved_idcompany,
            "question": req.question,
            "copilot": planner.copilot,
            "intent": sql_out.intent,
            "sql": executed_sql,
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
        execution={
            "rows_returned": len(result.rows),
            "schema_column_repair_attempted": schema_repair_attempted,
            "db_retry_attempts": db_retry_count,
        },
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
            rendered_sql_preview=_render_sql_preview(executed_sql, params),
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
        follow_up_prompts=follow_up_prompts,
        chart_spec=chart_spec,
        confidence=planner.confidence,
        assumptions=assumptions,
        row_limit_notice=row_limit_notice,
        debug=debug,
    )
