from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

from .nl2sql_engine import QuerySpec
from .v3.rag.schema_index import build_schema_from_registry


SCHEMA_CONTEXT = """
Primary entities:
- company (tenant), always scope with idcompany.
- company_sale (sale header): is_sale/is_quote/isapproval/isreturned, sale_date, total.
- company_sale_data (line-level sales view): sale_date, transaction_number, item_title,
  ArtistName, CustomerName, qty, PriceNow, LineTotal, idcompany_sale_line_items,
  item_edition_type, item_edition, EditionName.
- company_item / company_item_data (inventory): qoh, artprice, art_cost, edition_type.
- company_sale_payment (layaway/payment dues): date_due, date_paid, amount_due, amount_paid, is_layaway.

Business definitions:
- Revenue (gross, tax-inclusive): SUM(company_sale.total)
- TotalSales (net, tax-exclusive): SUM(company_sale_data.LineTotal)

Mandatory constraints:
- SELECT-only query.
- Must include tenant filter: idcompany = %(idcompany)s
- Never include INSERT/UPDATE/DELETE/ALTER/DROP/TRUNCATE.
""".strip()

COPILOT_TYPES = {"sales", "inventory", "customer", "artist", "vendor"}

COPILOT_CONTEXT: dict[str, str] = {
    "sales": """
Sales focus:
- Prefer company_sale and company_sale_data.
- Revenue = SUM(company_sale.total), tax inclusive.
- TotalSales = SUM(company_sale_data.LineTotal), tax exclusive.
""".strip(),
    "inventory": """
Inventory focus:
- Prefer company_item and company_item_data.
- Use qoh, artprice, art_cost, edition_type where relevant.
- For inventory detail asks, return item-level rows with sensible LIMIT.
- company_item_data: use LocationName (not stock_location), (qoh * artprice) for value (not total_asking_price). Do not use is_delete with company_item_data.
""".strip(),
    "customer": """
Customer focus:
- Prefer company_contact_data1 and company_sale/company_sale_data.
- Use only columns from the schema above for customer identity.
- Typical asks: LTV/top customers, overdue balances, inactive customers.
""".strip(),
    "artist": """
Artist focus:
- Prefer company_sale_data and company_item_data.
- Use only columns from the schema above for artist identity.
- Typical asks: artist sales performance, top collectors, returns profile.
""".strip(),
    "vendor": """
Vendor focus:
- Prefer company_vendor, company_contact_data1, and payable-like views.
- Typical asks: outstanding payables, overdue invoices, spend trend.
- Keep output strictly read-only aggregate/detail SELECTs.
""".strip(),
}


def _extract_requested_limit(question: str) -> int | None:
    q = question.lower()
    m = re.search(r"\b(?:top|last|latest|recent|show)\s+(\d{1,3})\b", q)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(\d{1,3})\s+(?:items|rows|customers|artists|locations)\b", q)
    if m:
        return int(m.group(1))
    return None


def _extract_applied_limit(sql: str) -> int | None:
    m = re.search(r"\blimit\s+(\d{1,6})\b", sql, flags=re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def _slugify_intent(intent: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", intent.strip().lower()).strip("_")
    return s or "llm_generated"


def _normalize_idcompany_placeholders(sql: str) -> str:
    s = sql
    s = re.sub(r":idcompany\b", "%(idcompany)s", s, flags=re.IGNORECASE)
    s = re.sub(r"@idcompany\b", "%(idcompany)s", s, flags=re.IGNORECASE)
    return s


def _inject_tenant_filter(sql: str) -> str:
    lower = sql.lower()
    if "idcompany" in lower:
        return sql

    condition = "idcompany = %(idcompany)s"
    order_pos = min([p for p in [
        lower.find(" group by "),
        lower.find(" order by "),
        lower.find(" limit "),
    ] if p != -1], default=-1)

    if " where " in lower:
        if order_pos == -1:
            return f"{sql} AND {condition}"
        return f"{sql[:order_pos]} AND {condition} {sql[order_pos:]}"

    if order_pos == -1:
        return f"{sql} WHERE {condition}"
    return f"{sql[:order_pos]} WHERE {condition} {sql[order_pos:]}"


def _coerce_limit(sql: str, max_limit: int) -> str:
    m = re.search(r"\blimit\s+(\d{1,6})\b", sql, flags=re.IGNORECASE)
    if not m:
        return sql
    limit = int(m.group(1))
    if limit <= max_limit:
        return sql
    return re.sub(r"\blimit\s+\d{1,6}\b", f"LIMIT {max_limit}", sql, flags=re.IGNORECASE)


def _repair_common_column_aliases(sql: str) -> str:
    """
    Best-effort correction for common LLM mistakes against known views.
    """
    out = sql
    lowered = out.lower()
    if "company_sale_data" in lowered:
        # company_sale_data doesn't expose edition_type; use EditionName.
        out = re.sub(
            r"\b(?:(\w+)\.)?edition_type\b",
            lambda m: f"{m.group(1)}.EditionName" if m.group(1) else "EditionName",
            out,
            flags=re.IGNORECASE,
        )
        # Normalize common edition label variants.
        out = re.sub(r"'open edition'", "'Open'", out, flags=re.IGNORECASE)
        out = re.sub(r"'limited edition'", "'Limited'", out, flags=re.IGNORECASE)
        out = re.sub(r"'unique edition'", "'Unique'", out, flags=re.IGNORECASE)
        out = re.sub(r"'non stock edition'", "'Non Stock'", out, flags=re.IGNORECASE)
    return out


def _enforce_or_parentheses_scope(sql: str) -> str:
    """
    If WHERE contains OR, enforce:
      WHERE idcompany = %(idcompany)s AND ( ...other conditions... )
    so tenant and shared predicates don't get dropped by SQL operator precedence.
    """
    out = sql
    m = re.search(
        r"(?is)\bwhere\b\s+(?P<where>.*?)(?=\bgroup\s+by\b|\border\s+by\b|\blimit\b|$)",
        out,
    )
    if not m:
        return out

    where_body = m.group("where").strip()
    if re.search(r"(?i)\bor\b", where_body) is None:
        return out

    # Remove idcompany condition from inner clause if present.
    inner = where_body
    inner = re.sub(
        r"(?is)\bidcompany\s*=\s*%\(\s*idcompany\s*\)s\b\s*(?:and|or)?",
        "",
        inner,
    )
    inner = re.sub(
        r"(?is)(?:and|or)\s*\bidcompany\s*=\s*%\(\s*idcompany\s*\)s\b",
        "",
        inner,
    )
    inner = inner.strip()
    inner = re.sub(r"(?is)^(and|or)\b", "", inner).strip()
    inner = re.sub(r"(?is)\b(and|or)$", "", inner).strip()
    if not inner:
        return out

    new_where = f"idcompany = %(idcompany)s AND ({inner})"
    start, end = m.span("where")
    return f"{out[:start]}{new_where}{out[end:]}"


def _enforce_shared_edition_predicate(sql: str) -> str:
    """
    Fix patterns like:
      item_edition_type='Limited' AND q1 OR q4
    to:
      item_edition_type='Limited' AND (q1 OR q4)
    """
    out = sql
    m = re.search(
        r"(?is)(?P<pred>(?:\w+\.)?(?:item_edition_type|EditionName)\s*=\s*'[^']+')\s+and\s+(?P<rest>.+\bor\b.+)",
        out,
    )
    if not m:
        return out

    pred = m.group("pred").strip()
    rest = m.group("rest").strip()

    # If already wrapped as pred AND (...), keep as-is.
    if rest.startswith("(") and rest.endswith(")"):
        return out

    replacement = f"{pred} AND ({rest})"
    start, end = m.span()
    return f"{out[:start]}{replacement}{out[end:]}"


def _repair_dangling_boolean_tokens(sql: str) -> str:
    """
    Repair malformed boolean fragments occasionally emitted by LLMs, e.g.:
      ... AND )
      ... OR )
      ... )GROUP BY ...
    Keep this narrowly scoped to avoid changing valid SQL behavior.
    """
    out = sql
    # Remove boolean operator immediately before ')'
    out = re.sub(r"(?i)\b(?:and|or)\b\s*(?=\))", "", out)
    # Remove accidental operator right after '('
    out = re.sub(r"(?i)\(\s*(?:and|or)\b\s*", "(", out)
    # Remove trailing operator before clause boundaries/end
    out = re.sub(r"(?i)\b(?:and|or)\b\s*(?=(group\s+by|order\s+by|limit)\b|$)", "", out)
    # Ensure separator after ')' before major clauses
    out = re.sub(r"(?i)\)\s*(group\s+by|order\s+by|limit)\b", r") \1", out)
    # Clean accidental empty grouping parentheses, but keep function calls like NOW()/CURDATE().
    out = re.sub(r"(?<![A-Za-z0-9_])\(\s*\)", "", out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out


def _repair_common_datetime_function_calls(sql: str) -> str:
    """
    Repair common LLM slips where MySQL date/time functions are emitted
    without parentheses (e.g., CURDATE instead of CURDATE()).
    """
    out = sql
    out = re.sub(r"(?i)\bcurdate\b(?!\s*\()", "CURDATE()", out)
    out = re.sub(r"(?i)\bnow\b(?!\s*\()", "NOW()", out)
    return out


def _sanitize_sql(sql: str, max_limit: int) -> str:
    out = sql.strip().strip("`").rstrip(";")
    out = _normalize_idcompany_placeholders(out)
    out = _repair_common_column_aliases(out)
    out = _repair_common_datetime_function_calls(out)
    out = _repair_dangling_boolean_tokens(out)
    out = _inject_tenant_filter(out)
    out = _enforce_or_parentheses_scope(out)
    out = _enforce_shared_edition_predicate(out)
    out = _coerce_limit(out, max_limit=max_limit)
    return out


def _extract_json_payload(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return json.loads(text)

    # Handle accidental markdown fences.
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def generate_query_with_llm(
    question: str,
    copilot: Literal["sales", "inventory", "customer", "artist", "vendor"] | None = None,
    error_context: dict[str, str] | None = None,
    schema_from_context: str | None = None,
) -> tuple[QuerySpec | None, str | None]:
    if os.getenv("AI_FIRST_SQL_ENABLED", "1") not in {"1", "true", "TRUE", "yes", "YES"}:
        return None, "ai_first_sql_disabled"

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None, "missing_openai_api_key"

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        model = os.getenv("OPENAI_MODEL_SQL", "gpt-4.1")
        max_limit = int(os.getenv("MYSQL_MAX_ROWS", "200"))
        selected_copilot = (copilot or "").strip().lower()
        if selected_copilot not in COPILOT_TYPES:
            selected_copilot = "sales"
        copilot_context = COPILOT_CONTEXT.get(selected_copilot, COPILOT_CONTEXT["sales"])
        schema_block = (
            (schema_from_context or "").strip()
            or build_schema_from_registry(selected_copilot)
            or SCHEMA_CONTEXT
        )
        if schema_block and not schema_block.endswith("\n"):
            schema_block += "\n"

        system_prompt = f"""
You are an expert MySQL NL2SQL generator for an art-gallery ERP.
Selected copilot: {selected_copilot}
Return ONLY valid JSON with keys:
- intent: string
- sql: string
- window_label: string (optional)

{schema_block}
{copilot_context}

Rules:
- SQL must be a single SELECT statement.
- Use MySQL syntax.
- Use placeholder %(idcompany)s for tenant filter.
- If a detail list is requested and user gives count (e.g., top 5/recent 10), apply LIMIT accordingly.
- Cap LIMIT at {max_limit}.
- Prefer views when useful:
  - company_sale_data, company_item_data, company_contact_data1
- IMPORTANT:
  - For sold-item queries from company_sale_data, do NOT use `edition_type`.
  - Use `EditionName` or `item_edition_type` in company_sale_data.
  - `edition_type` exists in company_item/company_item_data context.
- Set `intent` to a copilot-prefixed value (e.g. {selected_copilot}_something).
- Do not include comments, markdown, or explanations outside JSON.
""".strip()

        user_prompt = question
        if error_context:
            prev_sql = error_context.get("previous_sql", "")
            db_error = error_context.get("db_error", "")
            user_prompt = (
                f"{question}\n\n"
                "Previous SQL failed. Regenerate a corrected SQL query.\n"
                f"Previous SQL:\n{prev_sql}\n\n"
                f"Database error:\n{db_error}\n"
            )

        response = client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        payload = _extract_json_payload(content)

        raw_sql = str(payload.get("sql", "")).strip()
        if not raw_sql:
            return None, "llm_empty_sql"

        sql = _sanitize_sql(raw_sql, max_limit=max_limit)
        intent = _slugify_intent(str(payload.get("intent") or "llm_generated"))
        requested_limit = _extract_requested_limit(question)
        applied_limit = _extract_applied_limit(sql)
        window_label = payload.get("window_label")
        if isinstance(window_label, str):
            window = window_label
        else:
            window = None

        return (
            QuerySpec(
                intent=intent,
                sql=sql,
                params={},
                requested_limit=requested_limit,
                applied_limit=applied_limit,
                window_label=window,
            ),
            None,
        )
    except Exception as e:
        return None, f"llm_generation_failed: {e}"

