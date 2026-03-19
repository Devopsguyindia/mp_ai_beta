from __future__ import annotations

from decimal import Decimal

from ..models import ChartSpec


def _is_numeric(val) -> bool:
    """Accept int, float, Decimal (MySQL returns Decimal for numeric columns)."""
    return isinstance(val, (int, float, Decimal))


def build_chart_spec(*, rows: list[dict], question: str, enabled: bool) -> ChartSpec | None:
    if not enabled or not rows:
        return None
    first = rows[0]
    keys = list(first.keys())
    if len(keys) < 2:
        return None

    x_field = keys[0]
    y_field = None
    for k in keys[1:]:
        if _is_numeric(first.get(k)):
            y_field = k
            break
    if not y_field:
        return None

    q = question.lower()
    chart_type = "line" if any(t in q for t in ["trend", "over time", "month", "daily", "weekly"]) else "bar"
    return ChartSpec(type=chart_type, x_field=x_field, y_field=y_field, title=f"{y_field} by {x_field}")
