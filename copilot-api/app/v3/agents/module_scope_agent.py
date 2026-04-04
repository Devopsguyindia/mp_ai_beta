"""
Classify whether a user question belongs to the ERP module sub-copilot (strict scope).
Used when strict_module_scope=True on V3AskRequest.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

ErpModule = Literal["contact", "inventory", "sales"]

_MODULE_TO_COPILOT: dict[str, str] = {
    "contact": "customer",
    "inventory": "inventory",
    "sales": "sales",
}

# User-facing refusal when the LLM marks the question out-of-scope (never use the model's free-form "reason").
GENERIC_MODULE_SCOPE_REFUSAL_LLM = (
    "This question is outside the {erp_module} AI Insights scope. Ask something specific to this module."
)


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def classify_module_scope_llm(
    *, question: str, erp_module: ErpModule, copilot: str
) -> tuple[bool, str]:
    """Returns (in_scope, reason). On LLM failure, returns (True, '') to avoid blocking."""
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return True, ""

    try:
        from openai import OpenAI  # type: ignore[import-untyped]

        model = os.getenv("V3_MODULE_SCOPE_MODEL", "gpt-4.1-mini")
        client = OpenAI(api_key=api_key)
        sys = (
            "You decide if a user's question belongs ONLY to the given ERP module context. "
            "The sub-copilot answers questions about that domain only; other domains must be refused.\n"
            f"erp_module={erp_module!r} maps to data domain copilot={copilot!r}.\n"
            "- contact: customers, collectors, contact info, LTV, follow-ups, artists, vendors, prospect, "
            "designer, gallery, commission, Biography, consignment percentage, interests, tasks, contact notes.\n"
            "- inventory: items, stock, QOH, editions, artists on items, vendors on items, country of origin, "
            "art cost, art price, dimension, height, width, 3d, appraisal, non discountable, discountable, "
            "maximum discount, taxable, consignment percentage, attributes, additional costs, stock location, "
            "web sale, masterpiece online, mpo, Ecommerce Enabled, shopify, ecommerce, web retail price, "
            "category, medium, scancode, art code, circa, custom category, subject, quick sale item.\n"
            "- sales: invoices, sales totals, layaway, revenue, selling performance, transaction, quote, approval, "
            "payment due, due amount, location, staff, staff commission, tax, quick sale, discount, vendor discount, "
            "price now, selling price, sales tax, total tax, total sale, profit, margine, line item, gross sale.\n"
            'Reply with JSON only: {"in_scope": true|false, "reason": "short string"}'
        )
        user = f"Question: {question[:2000]}"
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": user},
            ],
            temperature=0,
            max_tokens=200,
        )
        raw = (resp.choices[0].message.content or "").strip()
        data = _extract_json(raw)
        ok = bool(data.get("in_scope", True))
        reason = str(data.get("reason") or "").strip()
        return ok, reason
    except Exception:
        return True, ""


def classify_module_scope_heuristic(*, question: str, erp_module: ErpModule) -> tuple[bool, str]:
    """Lightweight keyword veto when LLM is off or fails."""
    q = question.lower()
    if erp_module == "contact":
        # Strong signals for non-contact domains
        if re.search(r"\b(qoh|quantity on hand|stock level|open edition count)\b", q) and not re.search(
            r"\b(customer|contact|buyer|collector|email|phone|address)\b", q
        ):
            return False, "This looks like an inventory question. Use AI Insights from the Inventory module."
        if re.search(r"\b(vendor payable|supplier invoice|accounts payable)\b", q) and not re.search(
            r"\b(customer|contact)\b", q
        ):
            return False, "This looks like a vendor/finance question. Open AI Insights from the relevant module."
    if erp_module == "inventory":
        if re.search(r"\b(layaway|invoice total|sales revenue|monthly sales)\b", q) and not re.search(
            r"\b(item|stock|inventory|edition|qoh)\b", q
        ):
            return False, "This looks like a sales question. Use AI Insights from the Sales module."
    if erp_module == "sales":
        if re.search(r"\b(missing email|missing phone|contact record)\b", q) and not re.search(
            r"\b(sale|invoice|revenue|layaway|selling)\b", q
        ):
            return False, "This looks like a contacts question. Use AI Insights from the Contact module."
    return True, ""


def classify_module_scope(
    *, question: str, erp_module: ErpModule | None, copilot: str
) -> tuple[bool, str]:
    """
    Returns (allowed_to_proceed, refusal_message_if_blocked).
    If erp_module is None, always allow.

    Order: run keyword heuristics first (fixed user-facing strings). If those pass and the
    LLM classifier is enabled, call the LLM; when the LLM rejects, return only a generic
    message—never the model's free-form "reason" text.
    """
    if not erp_module:
        return True, ""

    ok_h, msg_h = classify_module_scope_heuristic(question=question, erp_module=erp_module)
    if not ok_h:
        return False, msg_h or f"This question is outside the {erp_module} AI Insights scope."

    use_llm = os.getenv("V3_MODULE_SCOPE_LLM_ENABLED", "1").strip().lower() in {"1", "true", "yes"}
    if not use_llm:
        return True, ""

    ok_llm, _reason = classify_module_scope_llm(
        question=question, erp_module=erp_module, copilot=copilot
    )
    if not ok_llm:
        return False, GENERIC_MODULE_SCOPE_REFUSAL_LLM.format(erp_module=erp_module)
    return True, ""


def erp_module_to_copilot_hint(erp_module: ErpModule | None) -> str | None:
    if not erp_module:
        return None
    return _MODULE_TO_COPILOT.get(erp_module)
