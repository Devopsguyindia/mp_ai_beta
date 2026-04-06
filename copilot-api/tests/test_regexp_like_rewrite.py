"""REGEXP_LIKE rewrite for MySQL < 8.0.4 compatibility."""

from app.sql_guardrails import rewrite_regexp_like_for_mysql_compat, validate_select_sql
from app.v3.sql_schema_check import apply_registry_column_synonyms


def test_rewrite_two_args():
    sql = (
        "SELECT COUNT(*) AS n FROM t WHERE idcompany = %(idcompany)s "
        "AND REGEXP_LIKE(email, '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\\\.[A-Za-z]{2,}$')"
    )
    out = rewrite_regexp_like_for_mysql_compat(sql)
    assert "REGEXP_LIKE" not in out.upper()
    assert "REGEXP" in out.upper()
    assert "(email) REGEXP" in out.replace(" ", "") or "email) REGEXP" in out.replace("\n", "")


def test_rewrite_three_args_drops_mode():
    sql = "SELECT 1 WHERE REGEXP_LIKE(a, b, 'c')"
    out = rewrite_regexp_like_for_mysql_compat(sql)
    assert "REGEXP_LIKE" not in out.upper()
    assert "(a) REGEXP (b)" in out


def test_rewrite_nested_parens():
    sql = "SELECT 1 WHERE REGEXP_LIKE(TRIM(email), '^x') AND idcompany = %(idcompany)s"
    out = rewrite_regexp_like_for_mysql_compat(sql)
    assert "REGEXP_LIKE" not in out.upper()


def test_apply_registry_synonyms_does_not_reintroduce_regexp_like():
    """sqlglot emit(dialect=mysql) uses REGEXP_LIKE; pipeline must rewrite after synonym pass."""
    sql = (
        "SELECT COUNT(*) AS c FROM company_contact_data1 WHERE idcompany = %(idcompany)s "
        "AND NOT (email_address) REGEXP ('^[a-z]+@[a-z]+\\\\.[a-z]+$')"
    )
    out = apply_registry_column_synonyms(sql)
    assert "REGEXP_LIKE" not in out.upper(), out


def test_validate_select_accepts_rewritten():
    sql = (
        "SELECT COUNT(*) AS c FROM company_contact_data1 WHERE idcompany = %(idcompany)s "
        "AND REGEXP_LIKE(email_address, '^[a-z]+@[a-z]+\\\\.[a-z]+$')"
    )
    r = validate_select_sql(sql=sql)
    assert "REGEXP_LIKE" not in (r.normalized_sql or "").upper()
    assert r.ok is True
