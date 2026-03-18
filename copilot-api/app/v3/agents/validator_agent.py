from __future__ import annotations

from ..models import SQLGenerationOutput, ValidationOutput
from ..prompts.loader import load_prompt
from ...llm_nl2sql import generate_query_with_llm
from ...sql_guardrails import validate_select_sql


def validate_with_retry(
    *,
    question: str,
    copilot: str,
    sql_output: SQLGenerationOutput,
    schema_context: list[str] | None = None,
    idcompany_param: str = "idcompany",
    max_retries: int = 1,
) -> ValidationOutput:
    _ = load_prompt("validator")
    sql = sql_output.sql
    params = dict(sql_output.params or {})
    guard = validate_select_sql(sql=sql, required_idcompany_param=idcompany_param)
    retry_attempted = False
    retry_success = False
    generation_error = sql_output.generation_error

    if guard.ok or max_retries <= 0:
        return ValidationOutput(
            ok=guard.ok,
            sql=sql,
            params=params,
            guardrails=guard,
            retry_attempted=retry_attempted,
            retry_success=retry_success,
            generation_error=generation_error,
        )

    retry_attempted = True
    schema_from_context = "\n".join(schema_context) if schema_context else None
    repaired_query, repair_err = generate_query_with_llm(
        question,
        copilot=copilot,  # type: ignore[arg-type]
        schema_from_context=schema_from_context,
        error_context={"previous_sql": sql, "db_error": "guardrail_validation_failed"},
    )
    if repaired_query is not None:
        repaired_sql = repaired_query.sql
        repaired_params = dict(repaired_query.params or {})
        repaired_guard = validate_select_sql(sql=repaired_sql, required_idcompany_param=idcompany_param)
        if repaired_guard.ok:
            retry_success = True
            return ValidationOutput(
                ok=True,
                sql=repaired_sql,
                params=repaired_params,
                guardrails=repaired_guard,
                retry_attempted=retry_attempted,
                retry_success=retry_success,
                generation_error=repair_err,
            )
        return ValidationOutput(
            ok=False,
            sql=repaired_sql,
            params=repaired_params,
            guardrails=repaired_guard,
            retry_attempted=retry_attempted,
            retry_success=retry_success,
            generation_error=repair_err,
        )

    return ValidationOutput(
        ok=False,
        sql=sql,
        params=params,
        guardrails=guard,
        retry_attempted=retry_attempted,
        retry_success=retry_success,
        generation_error=repair_err or generation_error,
    )
