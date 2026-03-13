from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QuerySpec:
    intent: str
    sql: str
    params: dict[str, Any]
    requested_limit: int | None = None
    applied_limit: int | None = None
    window_label: str | None = None


MAX_LIMIT = 200
DEFAULT_LIMIT = 10


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _extract_limit(q: str) -> tuple[int, int | None]:
    patterns = [
        r"\b(?:top|last|latest|recent|show)\s+(\d{1,3})\b",
        r"\b(\d{1,3})\s+(?:sold items|items|customers|artists|locations|rows)\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, q)
        if m:
            requested = int(m.group(1))
            return max(1, min(requested, MAX_LIMIT)), requested
    return DEFAULT_LIMIT, None


def _extract_window_expr(q: str) -> tuple[str, str]:
    if "last 7 days" in q:
        return "DATE_SUB(NOW(), INTERVAL 7 DAY)", "last_7_days"
    if "last 30 days" in q:
        return "DATE_SUB(NOW(), INTERVAL 30 DAY)", "last_30_days"
    if "last 90 days" in q:
        return "DATE_SUB(NOW(), INTERVAL 90 DAY)", "last_90_days"
    if "this month" in q:
        return "DATE_FORMAT(CURRENT_DATE(), '%Y-%m-01')", "this_month"
    if "ytd" in q or "year to date" in q or "this year" in q:
        return "MAKEDATE(YEAR(CURRENT_DATE()), 1)", "ytd"
    return "DATE_SUB(NOW(), INTERVAL 30 DAY)", "last_30_days_default"


def _score(q: str, words: list[str]) -> int:
    return sum(1 for w in words if w in q)


def _detect_intent(q: str) -> str:
    candidates = {
        "recent_sold_items": _score(q, ["sold", "item", "recent", "latest", "last"]),
        "top_customers_by_revenue": _score(q, ["top", "customer", "customers", "revenue", "buyer", "buyers"]),
        "top_artists_by_total_sales": _score(q, ["top", "artist", "artists", "sales", "selling"]),
        "layaway_outstanding_summary": _score(q, ["layaway", "outstanding", "overdue", "due"]),
        "inventory_count": _score(q, ["inventory", "count", "how many", "stock", "qoh"]),
        "sales_count_and_revenue": _score(q, ["sales", "revenue", "count"]),
    }

    # Prefer strong signals for specific intents.
    if "layaway" in q:
        return "layaway_outstanding_summary"
    if ("sold" in q and "item" in q) or ("latest sold" in q):
        return "recent_sold_items"

    intent = max(candidates, key=lambda k: candidates[k])
    if candidates[intent] <= 0:
        return "sales_count_and_revenue"
    return intent


def generate_query(question: str) -> QuerySpec:
    q = _normalize(question)
    limit, requested_limit = _extract_limit(q)
    window_expr, window_label = _extract_window_expr(q)
    intent = _detect_intent(q)

    if intent == "recent_sold_items":
        return QuerySpec(
            intent=intent,
            sql=f"""
            SELECT
              d.sale_date,
              d.transaction_number,
              d.idcompany_item,
              d.item_title,
              d.ArtistName,
              d.CustomerName,
              d.qty,
              d.PriceNow,
              d.LineTotal
            FROM company_sale_data d
            WHERE d.idcompany = %(idcompany)s
              AND d.is_sale = 1
              AND COALESCE(d.SaleReturned, 0) = 0
            ORDER BY d.sale_date DESC, d.idcompany_sale_line_items DESC
            LIMIT {limit}
            """.strip(),
            params={},
            requested_limit=requested_limit,
            applied_limit=limit,
            window_label=window_label,
        )

    if intent == "top_customers_by_revenue":
        return QuerySpec(
            intent=intent,
            sql=f"""
            SELECT
              s.idcompany_customer AS idcompany_contact,
              c.full_name AS customer_name,
              ROUND(SUM(s.total), 2) AS revenue_gross
            FROM company_sale s
            LEFT JOIN company_contact_data1 c
              ON c.idcompany_contact = s.idcompany_customer
             AND c.idcompany = s.idcompany
            WHERE s.idcompany = %(idcompany)s
              AND s.is_sale = 1
              AND COALESCE(s.isreturned,0) = 0
              AND s.sale_date >= {window_expr}
            GROUP BY s.idcompany_customer, c.full_name
            ORDER BY revenue_gross DESC
            LIMIT {limit}
            """.strip(),
            params={},
            requested_limit=requested_limit,
            applied_limit=limit,
            window_label=window_label,
        )

    if intent == "top_artists_by_total_sales":
        return QuerySpec(
            intent=intent,
            sql=f"""
            SELECT
              d.idcompany_artist,
              d.ArtistName,
              ROUND(SUM(d.LineTotal), 2) AS total_sales_net
            FROM company_sale_data d
            WHERE d.idcompany = %(idcompany)s
              AND d.is_sale = 1
              AND COALESCE(d.SaleReturned, 0) = 0
              AND d.sale_date >= {window_expr}
            GROUP BY d.idcompany_artist, d.ArtistName
            ORDER BY total_sales_net DESC
            LIMIT {limit}
            """.strip(),
            params={},
            requested_limit=requested_limit,
            applied_limit=limit,
            window_label=window_label,
        )

    if intent == "inventory_count":
        return QuerySpec(
            intent=intent,
            sql="""
            SELECT
              COUNT(*) AS inventory_items,
              ROUND(SUM(COALESCE(qoh, 0)), 2) AS total_qoh
            FROM company_item
            WHERE idcompany = %(idcompany)s
              AND COALESCE(is_delete, 0) = 0
            """.strip(),
            params={},
            requested_limit=requested_limit,
            applied_limit=limit,
            window_label=window_label,
        )

    if intent == "layaway_outstanding_summary":
        return QuerySpec(
            intent=intent,
            sql="""
            SELECT
              COUNT(DISTINCT p.idcompany_sale) AS layaway_sales,
              ROUND(SUM(CASE
                WHEN p.date_paid IS NULL THEN (p.amount_due - COALESCE(p.amount_paid, 0))
                ELSE 0
              END), 2) AS outstanding_amount,
              ROUND(SUM(CASE
                WHEN p.date_paid IS NULL AND p.date_due < NOW() THEN (p.amount_due - COALESCE(p.amount_paid, 0))
                ELSE 0
              END), 2) AS overdue_amount
            FROM company_sale_payment p
            JOIN company_sale s
              ON s.idcompany_sale = p.idcompany_sale
            WHERE p.idcompany = %(idcompany)s
              AND s.idcompany = %(idcompany)s
              AND s.is_sale = 1
              AND COALESCE(p.is_layaway, 0) = 1
              AND p.pay_type = 'Layaway'
            """.strip(),
            params={},
            requested_limit=requested_limit,
            applied_limit=limit,
            window_label=window_label,
        )

    # Default/fallback
    return QuerySpec(
        intent="sales_count_and_revenue",
        sql=f"""
        SELECT
          COUNT(*) AS sales_count,
          ROUND(SUM(total), 2) AS revenue_gross
        FROM company_sale
        WHERE idcompany = %(idcompany)s
          AND is_sale = 1
          AND COALESCE(isreturned,0) = 0
          AND sale_date >= {window_expr}
        """.strip(),
        params={},
        requested_limit=requested_limit,
        applied_limit=limit,
        window_label=window_label,
    )

