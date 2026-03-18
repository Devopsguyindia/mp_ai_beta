from __future__ import annotations

from ..models import SQLGenerationOutput
from ..prompts.loader import load_prompt
from ...llm_nl2sql import generate_query_with_llm
from ...nl2sql_engine import generate_query


def generate_sql(
    *,
    question: str,
    copilot: str,
    schema_context: list[str],
    memory_questions: list[str],
) -> SQLGenerationOutput:
    strict_sql_prompt = load_prompt("sql")
    scoped_question = question
    if strict_sql_prompt:
        scoped_question = f"{question}\n\nStrict SQL instructions:\n{strict_sql_prompt}"
    if memory_questions:
        scoped_question += "\n\nRecent related asks:\n- " + "\n- ".join(memory_questions[:4])

    schema_from_context = "\n".join(schema_context) if schema_context else ""
    query, generation_error = generate_query_with_llm(
        scoped_question,
        copilot=copilot,  # type: ignore[arg-type]
        schema_from_context=schema_from_context or None,
    )
    generation_path = "llm"
    if query is None:
        query = generate_query(question, copilot=copilot)  # type: ignore[arg-type]
        generation_path = "deterministic_fallback"

    return SQLGenerationOutput(
        intent=query.intent,
        sql=query.sql,
        params=query.params,
        requested_limit=query.requested_limit,
        applied_limit=query.applied_limit,
        window_label=query.window_label,
        generation_path=generation_path,
        generation_error=generation_error,
    )
