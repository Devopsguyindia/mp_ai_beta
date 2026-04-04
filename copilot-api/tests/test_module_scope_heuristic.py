"""Heuristic module scope classifier (no network)."""

from unittest.mock import patch

from app.v3.agents.module_scope_agent import (
    GENERIC_MODULE_SCOPE_REFUSAL_LLM,
    classify_module_scope,
    classify_module_scope_heuristic,
)


def test_contact_allows_typical_question():
    ok, _ = classify_module_scope_heuristic(
        question="How many customers are missing email?",
        erp_module="contact",
    )
    assert ok is True


def test_inventory_heuristic_blocks_obvious_sales_question():
    ok, msg = classify_module_scope_heuristic(
        question="Monthly sales revenue trend for last year",
        erp_module="inventory",
    )
    assert ok is False
    assert "sales" in msg.lower()


def test_classify_module_scope_skips_when_no_erp_module():
    ok, msg = classify_module_scope(question="anything", erp_module=None, copilot="sales")
    assert ok is True
    assert msg == ""


def test_classify_module_scope_heuristic_first_when_llm_disabled(monkeypatch):
    monkeypatch.setenv("V3_MODULE_SCOPE_LLM_ENABLED", "0")
    ok, msg = classify_module_scope(
        question="Monthly sales revenue trend for last year",
        erp_module="inventory",
        copilot="inventory",
    )
    assert ok is False
    assert "Sales module" in msg


@patch("app.v3.agents.module_scope_agent.classify_module_scope_llm")
def test_llm_block_returns_generic_message_not_llm_reason(mock_llm, monkeypatch):
    """When LLM rejects, user never sees the model's free-form reason string."""
    monkeypatch.setenv("V3_MODULE_SCOPE_LLM_ENABLED", "1")
    mock_llm.return_value = (
        False,
        "The question is about contacts and customers, which belongs to the contact domain, not sales.",
    )
    ok, msg = classify_module_scope(
        question="What is total revenue last month",
        erp_module="sales",
        copilot="sales",
    )
    assert ok is False
    assert "contact domain" not in msg
    assert "belongs" not in msg
    assert msg == GENERIC_MODULE_SCOPE_REFUSAL_LLM.format(erp_module="sales")
