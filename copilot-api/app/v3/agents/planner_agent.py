from __future__ import annotations

from ..models import PlannerOutput
from ..prompts.loader import load_prompt


def plan_question(*, question: str, requested_copilot: str | None = None) -> PlannerOutput:
    _ = load_prompt("planner")
    q = question.lower()
    if requested_copilot in {"sales", "inventory", "customer", "artist", "vendor"}:
        copilot = requested_copilot
        confidence = 0.95
    elif any(t in q for t in ["inventory", "stock", "qoh", "item", "edition", "limited", "open", "unique"]):
        copilot = "inventory"
        confidence = 0.78
    elif any(t in q for t in ["customer", "buyer", "collector", "ltv"]):
        copilot = "customer"
        confidence = 0.8
    elif any(t in q for t in ["artist", "commission"]):
        copilot = "artist"
        confidence = 0.8
    elif any(t in q for t in ["vendor", "supplier", "payable", "invoice"]):
        copilot = "vendor"
        confidence = 0.8
    else:
        copilot = "sales"
        confidence = 0.6

    is_trend = any(t in q for t in ["trend", "over time", "month", "weekly", "daily", "timeline"])
    is_count = any(t in q for t in ["count", "how many", "total"])
    output_type = "trend" if is_trend else ("kpi" if is_count else "table")
    needs_chart = is_trend or ("compare" in q and output_type != "table")
    intent_hint = f"{copilot}_{'trend' if is_trend else ('count' if is_count else 'detail')}"

    return PlannerOutput(
        copilot=copilot,  # type: ignore[arg-type]
        intent_hint=intent_hint,
        output_type=output_type,  # type: ignore[arg-type]
        needs_chart=needs_chart,
        confidence=confidence,
    )
