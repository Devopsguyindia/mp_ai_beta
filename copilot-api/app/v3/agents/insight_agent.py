from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

from ..models import InsightItem
from ..prompts.loader import load_prompt


def _serialize_rows_for_llm(rows: list[dict], max_rows: int = 10) -> str:
    """Truncate and serialize rows for LLM context. Converts non-JSON-serializable values to strings."""
    sample = rows[:max_rows]
    serializable: list[dict[str, Any]] = []
    for r in sample:
        row: dict[str, Any] = {}
        for k, v in r.items():
            if v is None:
                row[k] = None
            elif isinstance(v, (str, int, float, bool)):
                row[k] = v
            else:
                row[k] = str(v)
        serializable.append(row)
    return json.dumps(serializable, default=str)


def _extract_json_payload(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return json.loads(text)
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def generate_insights_with_llm(
    *,
    question: str,
    rows: list[dict],
    sql: str,
    intent: str,
    copilot: Literal["sales", "inventory", "customer", "artist", "vendor"],
) -> list[InsightItem]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return []

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        model = os.getenv("OPENAI_MODEL_INSIGHT", "") or os.getenv("OPENAI_MODEL_SQL", "gpt-4.1")
        system_prompt = load_prompt("insight")
        if not system_prompt:
            return []

        data_sample = _serialize_rows_for_llm(rows)
        user_prompt = (
            f"User question: {question}\n"
            f"Copilot: {copilot}\n"
            f"Intent: {intent}\n"
            f"SQL (for context): {sql[:500]}\n"
            f"Result rows: {len(rows)} total. Sample:\n{data_sample}"
        )

        response = client.chat.completions.create(
            model=model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        payload = _extract_json_payload(content)
        raw_insights = payload.get("insights")
        if not isinstance(raw_insights, list):
            return []

        result: list[InsightItem] = []
        for item in raw_insights[:3]:
            if isinstance(item, dict):
                title = item.get("title")
                detail = item.get("detail")
                if isinstance(title, str) and isinstance(detail, str):
                    result.append(InsightItem(title=title, detail=detail))
        return result
    except Exception:
        return []


def _fallback_insights(*, rows: list[dict], question: str) -> list[InsightItem]:
    """Rule-based fallback when LLM is disabled or fails."""
    insights: list[InsightItem] = []
    row_count = len(rows)
    insights.append(
        InsightItem(
            title="Rows Returned",
            detail=f"The query returned {row_count} row{'s' if row_count != 1 else ''}.",
        )
    )
    if rows:
        first_row = rows[0]
        numeric_fields = [k for k, v in first_row.items() if isinstance(v, (int, float))]
        if numeric_fields:
            field = numeric_fields[0]
            values = [float(r.get(field)) for r in rows if isinstance(r.get(field), (int, float))]
            if values:
                insights.append(
                    InsightItem(
                        title=f"{field} summary",
                        detail=f"Min={min(values):.2f}, Max={max(values):.2f}, Avg={sum(values)/len(values):.2f}",
                    )
                )
    return insights


def build_insights(
    *,
    rows: list[dict],
    question: str,
    sql: str | None = None,
    intent: str | None = None,
    copilot: str | None = None,
) -> list[InsightItem]:
    llm_enabled = os.getenv("V3_INSIGHT_LLM_ENABLED", "1").strip() in {"1", "true", "TRUE", "yes", "YES"}
    copilot_types: tuple[str, ...] = ("sales", "inventory", "customer", "artist", "vendor")
    valid_copilot = (copilot or "sales").strip().lower()
    if valid_copilot not in copilot_types:
        valid_copilot = "sales"

    if llm_enabled and sql and intent and os.getenv("OPENAI_API_KEY", "").strip():
        llm_insights = generate_insights_with_llm(
            question=question,
            rows=rows,
            sql=sql,
            intent=intent,
            copilot=valid_copilot,  # type: ignore[arg-type]
        )
        if llm_insights:
            return llm_insights

    return _fallback_insights(rows=rows, question=question)
