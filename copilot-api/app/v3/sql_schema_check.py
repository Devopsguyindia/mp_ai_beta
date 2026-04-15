from __future__ import annotations

import re

import sqlglot
from sqlglot import exp

from ..sql_guardrails import (
    restore_idcompany_placeholder_after_sqlglot,
    rewrite_redundant_qualified_open_paren,
    rewrite_regexp_like_for_mysql_compat,
)

from .rag.schema_index import load_schema_registry

# LLM-invented or ERP-mismatched names -> exact column names in the DB view (must match registry).
# company_item_data has ArtName; company_sale_data uses ArtistName — do not map ArtName globally.
COLUMN_SYNONYMS_BY_TABLE: dict[str, dict[str, str]] = {
    "company_sale_data": {
        "itemname": "item_title",
        "artname": "ArtistName",
    },
    # company_item_data uses title (not item_title); ArtName is valid here — do not map artname.
    "company_item_data": {
        "itemname": "title",
    },
}


def _synonym_target_lower(physical: str, col_lower: str) -> str | None:
    """If col_lower is a known synonym, return the canonical lowercase name in registry; else None."""
    raw = COLUMN_SYNONYMS_BY_TABLE.get(physical, {}).get(col_lower)
    return raw.lower() if raw else None


def _build_table_to_columns() -> dict[str, set[str]]:
    """Lowercase table name -> set of lowercase column names from schema_registry."""
    registry = load_schema_registry()
    out: dict[str, set[str]] = {}
    for t in registry.get("tables") or []:
        if not isinstance(t, dict):
            continue
        name = str(t.get("table", "")).strip()
        if not name:
            continue
        cols: set[str] = set()
        for c in t.get("columns") or []:
            if isinstance(c, dict) and c.get("name"):
                cols.add(str(c["name"]).strip().lower())
        out[name.lower()] = cols
    return out


def _prepare_sql_for_parse(sql: str) -> str:
    return re.sub(r"%\([a-zA-Z_][a-zA-Z0-9_]*\)s", "1", sql.strip())


def _table_alias_lower(table: exp.Table) -> str | None:
    al = table.args.get("alias")
    if al is None:
        return None
    if isinstance(al, str):
        return al.lower()
    if isinstance(al, exp.TableAlias):
        inner = al.this
        if isinstance(inner, exp.Identifier):
            return inner.name.lower()
        return str(inner).lower() if inner is not None else None
    if isinstance(al, exp.Identifier):
        return al.name.lower()
    return str(al).lower() if al else None


def _collect_select_output_aliases(select: exp.Select) -> set[str]:
    """
    Names introduced by the SELECT list (AS aliases and bare column labels).
    ORDER BY / GROUP BY may reference these; they are not physical table columns.
    Also merges output names from subqueries in FROM (recursive).
    """
    out: set[str] = set()
    for proj in select.expressions:
        if isinstance(proj, exp.Alias):
            al = proj.args.get("alias")
            if isinstance(al, exp.Identifier):
                out.add(al.name.lower())
            elif isinstance(al, str) and al.strip():
                out.add(al.lower())
        # Do not treat bare Column refs in SELECT (e.g. SELECT ItemName) as aliases — those are
        # physical columns; including them would block synonym rewrite and ORDER BY fixes.
    from_clause = select.find(exp.From)
    if from_clause:
        for sub in from_clause.find_all(exp.Subquery):
            inner = sub.this
            if isinstance(inner, exp.Select):
                out |= _collect_select_output_aliases(inner)
    return out


def _collect_from_tables(select: exp.Select) -> list[tuple[str, str | None]]:
    """(table_name_lower, alias_lower_or_none) from top-level FROM/JOIN."""
    rows: list[tuple[str, str | None]] = []
    from_clause = select.find(exp.From)
    if not from_clause:
        return rows
    for table in from_clause.find_all(exp.Table):
        name = table.name
        if not name:
            continue
        alias_lower = _table_alias_lower(table)
        rows.append((name.lower(), alias_lower))
    return rows


def validate_sql_columns_against_registry(sql: str) -> tuple[bool, list[str]]:
    """
    Check that column references use names present on the referenced registry tables.
    Uses sqlglot AST + schema_registry.json.

    Returns (ok, violation_messages). On parse failure, returns (True, []) so guardrails handle parse.
    """
    sql = rewrite_redundant_qualified_open_paren(sql)
    violations: list[str] = []
    tables = _build_table_to_columns()
    if not tables:
        return True, []

    parseable = _prepare_sql_for_parse(sql)
    try:
        parsed = sqlglot.parse_one(parseable, read="mysql")
    except Exception:
        return True, []

    if not isinstance(parsed, exp.Select):
        return True, []

    from_rows = _collect_from_tables(parsed)
    if not from_rows:
        return True, []

    alias_to_physical: dict[str, str] = {}
    physical_in_query: set[str] = set()
    for physical, alias in from_rows:
        if physical in tables:
            physical_in_query.add(physical)
        if alias:
            alias_to_physical[alias] = physical
        alias_to_physical[physical] = physical

    union_cols: set[str] = set()
    for phys in physical_in_query:
        union_cols |= tables.get(phys, set())

    select_aliases = _collect_select_output_aliases(parsed)

    for col in parsed.find_all(exp.Column):
        if col.table and str(col.table).strip() == "*":
            continue
        col_name = col.name
        if not col_name:
            continue
        cn = col_name.lower()

        table_ref: str | None = None
        if col.table:
            if isinstance(col.table, str):
                table_ref = col.table.lower() if col.table.strip() else None
            elif isinstance(col.table, exp.Identifier):
                table_ref = col.table.name.lower()
            else:
                table_ref = str(col.table).lower() if str(col.table).strip() else None

        if table_ref:
            physical = alias_to_physical.get(table_ref, table_ref)
            allowed = tables.get(physical)
            if allowed is None:
                continue
            target = _synonym_target_lower(physical, cn) or cn
            if target not in allowed:
                violations.append(
                    f"Column '{col_name}' is not valid for table '{physical}' (registry mismatch)."
                )
        else:
            if cn in select_aliases:
                continue
            if cn in union_cols:
                continue
            allowed_unqual = False
            for phys in physical_in_query:
                tset = tables.get(phys, set())
                target = _synonym_target_lower(phys, cn) or cn
                if target in tset:
                    allowed_unqual = True
                    break
            if not allowed_unqual and cn not in union_cols:
                violations.append(
                    f"Unqualified column '{col_name}' is not among columns of tables in this query: "
                    f"{sorted(physical_in_query)}."
                )

    return (len(violations) == 0, violations)


def apply_registry_column_synonyms(sql: str) -> str:
    """
    Rewrite Column nodes that match COLUMN_SYNONYMS_BY_TABLE to exact registry/DB names.
    Safe to run before execute so MySQL sees real column names (e.g. item_title not ItemName).
    """
    sql = rewrite_redundant_qualified_open_paren(sql)
    tables = _build_table_to_columns()
    if not tables:
        return sql
    parseable = _prepare_sql_for_parse(sql)
    try:
        parsed = sqlglot.parse_one(parseable, read="mysql")
    except Exception:
        return sql

    for col in list(parsed.find_all(exp.Column)):
        if col.table and str(col.table).strip() == "*":
            continue
        sel = col.find_ancestor(exp.Select)
        if not isinstance(sel, exp.Select):
            continue
        name = col.name
        if not name:
            continue
        cn = str(name).lower()
        aliases = _collect_select_output_aliases(sel)
        if cn in aliases:
            continue
        from_rows = _collect_from_tables(sel)
        alias_to_physical: dict[str, str] = {}
        physical_in_query: set[str] = set()
        for physical, alias in from_rows:
            if physical in tables:
                physical_in_query.add(physical)
            if alias:
                alias_to_physical[alias] = physical
            alias_to_physical[physical] = physical

        table_ref: str | None = None
        if col.table:
            if isinstance(col.table, str):
                table_ref = col.table.lower() if col.table.strip() else None
            elif isinstance(col.table, exp.Identifier):
                table_ref = col.table.name.lower()
            else:
                table_ref = str(col.table).lower() if str(col.table).strip() else None

        physical: str | None = None
        if table_ref:
            physical = alias_to_physical.get(table_ref, table_ref)
            if physical not in physical_in_query:
                physical = None
        if physical is None and len(physical_in_query) == 1:
            physical = next(iter(physical_in_query))
        if physical is None:
            continue

        replace_as = COLUMN_SYNONYMS_BY_TABLE.get(physical, {}).get(cn)
        if not replace_as:
            continue
        allowed = tables.get(physical, set())
        if replace_as.lower() not in allowed:
            continue
        col.set("this", exp.Identifier(this=replace_as, quoted=False))

    try:
        out = parsed.sql(dialect="mysql")
    except Exception:
        return sql
    restored = restore_idcompany_placeholder_after_sqlglot(sql, out)
    restored = rewrite_redundant_qualified_open_paren(restored)
    # sqlglot MySQL emit uses REGEXP_LIKE (8.0.4+); rewrite for older MySQL / MariaDB.
    return rewrite_regexp_like_for_mysql_compat(restored)
