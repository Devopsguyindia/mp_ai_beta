"""Rewrite alias.(alias.col typo before MySQL execute (1064)."""

from app.sql_guardrails import rewrite_redundant_qualified_open_paren, validate_select_sql


def test_rewrite_cv_duplicate_qualifier():
    sql = (
        "SELECT 1 FROM company_vendor cv "
        "WHERE idcompany = %(idcompany)s AND (cv.(cv.maximum_discount IS NULL OR cv.maximum_discount = 0))"
    )
    out = rewrite_redundant_qualified_open_paren(sql)
    assert "cv.(cv." not in out
    assert "(cv.maximum_discount IS NULL OR cv.maximum_discount = 0)" in out


def test_validate_select_sql_accepts_after_rewrite():
    sql = (
        "SELECT cv.maximum_discount FROM company_vendor cv "
        "WHERE idcompany = %(idcompany)s AND (cv.(cv.maximum_discount IS NULL OR cv.maximum_discount = 0))"
    )
    g = validate_select_sql(sql=sql, required_idcompany_param="idcompany")
    assert g.ok
    assert g.normalized_sql
    assert "cv.(cv." not in (g.normalized_sql or "")
