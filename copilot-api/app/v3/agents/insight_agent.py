from __future__ import annotations

from ..models import InsightItem


def build_insights(*, rows: list[dict], question: str) -> list[InsightItem]:
    insights: list[InsightItem] = []
    row_count = len(rows)
    insights.append(
        InsightItem(
            title="Rows Returned",
            detail=f"The query returned {row_count} row{'s' if row_count != 1 else ''}.",
        )
    )

    if rows:
        first_row = rows[0]
        numeric_fields = [k for k, v in first_row.items() if isinstance(v, (int, float))]
        if numeric_fields:
            field = numeric_fields[0]
            values = [float(r.get(field)) for r in rows if isinstance(r.get(field), (int, float))]
            if values:
                insights.append(
                    InsightItem(
                        title=f"{field} summary",
                        detail=f"Min={min(values):.2f}, Max={max(values):.2f}, Avg={sum(values)/len(values):.2f}",
                    )
                )
    insights.append(
        InsightItem(
            title="Business Note",
            detail=f"Interpretation generated for: {question}",
        )
    )
    return insights
