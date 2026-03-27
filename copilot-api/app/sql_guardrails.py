from __future__ import annotations

import re

import sqlglot
from pydantic import BaseModel


class GuardrailViolation(BaseModel):
    code: str
    message: str


class GuardrailResult(BaseModel):
    ok: bool
    normalized_sql: str | None = None
    violations: list[GuardrailViolation] = []


def _contains_idcompany_param(sql: str, required_param: str) -> bool:
    # We enforce a param placeholder rather than a raw literal to avoid leakage via string interpolation.
    # mysql-connector uses "%(name)s" placeholders; allow a few common variants.
    needle_variants = [
        f"%({required_param})s",
        f":{required_param}",
        f"@{required_param}",
    ]
    s = sql.lower()
    return any(v.lower() in s for v in needle_variants)


def _prepare_sql_for_parsing(sql: str) -> str:
    """
    sqlglot doesn't parse DB-driver placeholders like %(name)s.
    Replace them with a safe literal only for AST parsing.
    """
    return re.sub(r"%\([a-zA-Z_][a-zA-Z0-9_]*\)s", "1", sql)


def restore_idcompany_placeholder_after_sqlglot(original_sql: str, transformed_sql: str) -> str:
    """
    After sqlglot parse/emit, driver placeholders were stubbed as literal 1 for parsing.
    If the original used %(idcompany)s, put it back so MySQL executes the tenant bind, not company 1.
    """
    if not re.search(r"%\(\s*idcompany\s*\)s", original_sql, re.I):
        return transformed_sql
    out = transformed_sql
    # Prefer quoted identifier if sqlglot emitted it.
    if re.search(r"(?<![\w])`idcompany`\s*=\s*1\b", out, re.I):
        out = re.sub(
            r"(?<![\w])`idcompany`\s*=\s*1\b",
            "`idcompany` = %(idcompany)s",
            out,
            count=1,
            flags=re.IGNORECASE,
        )
    elif re.search(r"(?<![\w])idcompany\s*=\s*1\b", out, re.I):
        out = re.sub(
            r"(?<![\w])idcompany\s*=\s*1\b",
            "idcompany = %(idcompany)s",
            out,
            count=1,
            flags=re.IGNORECASE,
        )
    return out


def validate_select_sql(*, sql: str, required_idcompany_param: str = "idcompany") -> GuardrailResult:
    violations: list[GuardrailViolation] = []
    raw = sql.strip().rstrip(";")
    parseable_sql = _prepare_sql_for_parsing(raw)

    # 1) Parse and ensure single statement
    try:
        parsed = sqlglot.parse(parseable_sql, read="mysql")
    except Exception as e:
        return GuardrailResult(
            ok=False,
            violations=[GuardrailViolation(code="sql_parse_error", message=str(e))],
        )

    if len(parsed) != 1:
        violations.append(
            GuardrailViolation(code="multi_statement", message="Only a single SELECT statement is allowed.")
        )
        return GuardrailResult(ok=False, violations=violations)

    expr = parsed[0]
    if expr.key.upper() != "SELECT":
        violations.append(
            GuardrailViolation(code="not_select", message="Only SELECT queries are allowed.")
        )

    # 2) Block common risky tokens even if parser allowed them.
    lowered = raw.lower()
    blocked_tokens = [
        " insert ",
        " update ",
        " delete ",
        " drop ",
        " alter ",
        " truncate ",
        " create ",
        " replace ",
        " grant ",
        " revoke ",
        " into outfile",
        " load_file",
        " information_schema",
        " mysql.",
    ]
    if any(tok in lowered for tok in blocked_tokens):
        violations.append(
            GuardrailViolation(code="blocked_token", message="Query contains blocked keywords or schemas.")
        )

    # 3) Enforce tenant param presence (idcompany)
    if not _contains_idcompany_param(raw, required_idcompany_param):
        violations.append(
            GuardrailViolation(
                code="missing_idcompany_filter",
                message=f"Query must include tenant filter using parameter '{required_idcompany_param}'.",
            )
        )

    ok = len(violations) == 0
    normalized_sql = None
    try:
        normalized_sql = expr.sql(dialect="mysql")
        normalized_sql = restore_idcompany_placeholder_after_sqlglot(raw, normalized_sql)
    except Exception:
        normalized_sql = raw

    return GuardrailResult(ok=ok, normalized_sql=normalized_sql, violations=violations)

