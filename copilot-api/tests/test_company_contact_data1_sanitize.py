"""Strip erroneous is_deleted filters on company_contact_data1 (view-only rule)."""

from app.llm_nl2sql import _strip_is_deleted_on_company_contact_data1


def test_strip_trailing_and_is_deleted():
    sql = (
        "SELECT COUNT(*) AS c FROM company_contact_data1 WHERE idcompany = 1 "
        "AND (is_customer = 1 AND (email IS NULL) AND is_deleted = 0)"
    )
    out = _strip_is_deleted_on_company_contact_data1(sql)
    assert "is_deleted" not in out.lower()


def test_noop_when_table_absent():
    sql = "SELECT 1 FROM company_contact WHERE idcompany = 1 AND is_deleted = 0"
    assert _strip_is_deleted_on_company_contact_data1(sql) == sql
