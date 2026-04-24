"""Qualify unqualified tenant idcompany when company_vendor joins company_contact_data1."""

from __future__ import annotations

from app.llm_nl2sql import _qualify_tenant_idcompany_for_company_vendor_joins, _sanitize_sql


def test_qualify_bare_idcompany_vendor_contact_join() -> None:
    sql = (
        "SELECT COALESCE(NULLIF(TRIM(cc.full_name), ''), 'Anonymous') AS VendorName, v.maximum_discount "
        "FROM company_vendor AS v "
        "LEFT JOIN company_contact_data1 AS cc ON v.idcompany_contact = cc.idcompany_contact "
        "WHERE idcompany = %(idcompany)s AND ((v.maximum_discount IS NULL OR v.maximum_discount = 0))"
    )
    out = _qualify_tenant_idcompany_for_company_vendor_joins(sql)
    assert "WHERE v.idcompany = %(idcompany)s AND" in out
    assert "WHERE idcompany = %(idcompany)s" not in out


def test_qualify_after_or_parentheses_scope_via_sanitize() -> None:
    """_enforce_or_parentheses_scope emits bare idcompany; final qualify step fixes it."""
    sql = (
        "SELECT v.maximum_discount FROM company_vendor v "
        "LEFT JOIN company_contact_data1 cc ON v.idcompany_contact = cc.idcompany_contact "
        "WHERE (v.maximum_discount IS NULL OR v.maximum_discount = 0)"
    )
    out = _sanitize_sql(sql, max_limit=200)
    assert "v.idcompany = %(idcompany)s" in out
    assert "WHERE idcompany = %(idcompany)s" not in out


def test_no_change_without_contact_join() -> None:
    sql = "SELECT v.maximum_discount FROM company_vendor v WHERE idcompany = %(idcompany)s"
    out = _qualify_tenant_idcompany_for_company_vendor_joins(sql)
    assert out == sql


def test_no_change_when_already_qualified() -> None:
    sql = (
        "SELECT 1 FROM company_vendor v "
        "LEFT JOIN company_contact_data1 cc ON v.idcompany_contact = cc.idcompany_contact "
        "WHERE v.idcompany = %(idcompany)s AND v.maximum_discount > 0"
    )
    out = _qualify_tenant_idcompany_for_company_vendor_joins(sql)
    assert out == sql
