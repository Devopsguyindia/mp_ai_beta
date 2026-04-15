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


def _skip_quoted(s: str, i: int) -> int:
    """Advance past a SQL single/double/backtick-quoted segment starting at index i."""
    q = s[i]
    if q not in ("'", '"', "`"):
        return i + 1
    i += 1
    if q == "`":
        while i < len(s):
            if s[i] == "`":
                if i + 1 < len(s) and s[i + 1] == "`":
                    i += 2
                else:
                    return i + 1
            i += 1
        return len(s)
    if q == "'":
        while i < len(s):
            if s[i] == "'":
                if i + 1 < len(s) and s[i + 1] == "'":
                    i += 2
                else:
                    return i + 1
            i += 1
        return len(s)
    while i < len(s):
        if s[i] == "\\":
            i += 2
            continue
        if s[i] == '"':
            return i + 1
        i += 1
    return len(s)


def _match_paren(s: str, open_idx: int) -> int | None:
    """Return index of the closing ')' matching '(' at open_idx, or None."""
    if open_idx >= len(s) or s[open_idx] != "(":
        return None
    depth = 0
    i = open_idx
    while i < len(s):
        c = s[i]
        if c in ("'", '"', "`"):
            i = _skip_quoted(s, i)
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def _split_top_level_commas(s: str) -> list[str]:
    """Split on commas not inside parentheses or quotes."""
    parts: list[str] = []
    buf_start = 0
    depth = 0
    i = 0
    while i < len(s):
        c = s[i]
        if c in ("'", '"', "`"):
            i = _skip_quoted(s, i)
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append(s[buf_start:i].strip())
            buf_start = i + 1
        i += 1
    parts.append(s[buf_start:].strip())
    return parts


def rewrite_redundant_qualified_open_paren(sql: str) -> str:
    """
    Repair LLM typo `alias.(alias.column ...)` → `(alias.column ...)` (MySQL 1064 near '(').
    Example: WHERE cv.(cv.maximum_discount IS NULL ...) → WHERE (cv.maximum_discount IS NULL ...).
    """
    return re.sub(
        r"\b([a-zA-Z_][a-zA-Z0-9_]*)\.\(\s*\1\.",
        r"(\1.",
        sql,
    )


def rewrite_regexp_like_for_mysql_compat(sql: str) -> str:
    """
    REGEXP_LIKE(expr, pat[, match_mode]) exists in MySQL 8.0.4+.
    Older MySQL / MariaDB reject it (Error 1305). Rewrite to (expr) REGEXP (pat).
    Optional third argument (match mode) is dropped for compatibility.
    """
    if "REGEXP_LIKE" not in sql.upper():
        return sql
    out: list[str] = []
    last = 0
    for m in re.finditer(r"\bREGEXP_LIKE\s*\(", sql, re.IGNORECASE):
        start = m.start()
        open_paren = m.end() - 1
        if start > last:
            out.append(sql[last:start])
        close_paren = _match_paren(sql, open_paren)
        if close_paren is None:
            out.append(sql[start:])
            return "".join(out)
        inner = sql[open_paren + 1 : close_paren]
        args = _split_top_level_commas(inner)
        if len(args) >= 2:
            expr, pat = args[0].strip(), args[1].strip()
            out.append(f"({expr}) REGEXP ({pat})")
        else:
            out.append(sql[start : close_paren + 1])
        last = close_paren + 1
    out.append(sql[last:])
    return "".join(out)


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
    raw = rewrite_redundant_qualified_open_paren(sql.strip().rstrip(";"))
    raw = rewrite_regexp_like_for_mysql_compat(raw)
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
        normalized_sql = rewrite_redundant_qualified_open_paren(normalized_sql)
        # sqlglot may emit REGEXP_LIKE for MySQL; re-apply compat rewrite for execution on older servers.
        normalized_sql = rewrite_regexp_like_for_mysql_compat(normalized_sql)
    except Exception:
        normalized_sql = raw

    return GuardrailResult(ok=ok, normalized_sql=normalized_sql, violations=violations)

