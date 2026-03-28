from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

# Default column names when schema registry has no match (backward compatibility)
_DEFAULT_CUSTOMER_NAME_COL = "CustomerName"
_DEFAULT_ARTIST_NAME_COL = "ArtistName"
_DEFAULT_VENDOR_NAME_COL = "VendorName"
_DEFAULT_LINE_TOTAL_COL = "LineTotal"
_DEFAULT_PRICE_NOW_COL = "PriceNow"
_DEFAULT_ITEM_TITLE_COL = "item_title"
_DEFAULT_SALE_RETURNED_COL = "SaleReturned"

# User-facing date format (matches schema_registry global_critical_notes)
_DATE_FMT_US = "%m/%d/%Y"


def _date_expr(col_sql: str) -> str:
    """MySQL expression for SELECT output: calendar date only, US format (no time)."""
    return f"DATE_FORMAT(DATE({col_sql}), '{_DATE_FMT_US}')"


def _month_bucket_us_expr(col_sql: str) -> str:
    """First day of month as MM/DD/YYYY for monthly aggregates."""
    return (
        f"DATE_FORMAT(DATE(CONCAT(DATE_FORMAT({col_sql}, '%Y-%m'), '-01')), '{_DATE_FMT_US}')"
    )


# Concept -> substrings that must appear in column name (case-insensitive)
_CONCEPT_PATTERNS: dict[str, list[str]] = {
    "customer_name": ["customer", "name"],
    "artist_name": ["artist", "name"],
    "vendor_name": ["vendor", "name"],
    "line_total": ["line", "total"],
    "price_now": ["price", "now"],
    "item_title": ["item", "title"],
    "sale_returned": ["sale", "returned"],
}


def _resolve_column_from_registry(table: str, concept: str) -> str | None:
    """Resolve column name for table+concept from schema registry. Returns None if not found."""
    try:
        from .v3.rag.schema_index import load_schema_registry
        registry = load_schema_registry()
        tables = registry.get("tables", [])
        table_entry = next(
            (t for t in tables if isinstance(t, dict) and str(t.get("table", "")) == table),
            None,
        )
        if not table_entry:
            return None
        columns = table_entry.get("columns", [])
        concept_lower = concept.lower()
        patterns = _CONCEPT_PATTERNS.get(concept_lower)
        if patterns:
            for col in columns:
                name = str(col.get("name", ""))
                name_lower = name.lower()
                if all(p in name_lower for p in patterns):
                    return name
        return None
    except Exception:
        return None


def _customer_name_col(table: str = "company_sale_data") -> str:
    return _resolve_column_from_registry(table, "customer_name") or _DEFAULT_CUSTOMER_NAME_COL


def _artist_name_col(table: str = "company_sale_data") -> str:
    return _resolve_column_from_registry(table, "artist_name") or _DEFAULT_ARTIST_NAME_COL


def _vendor_name_col(table: str = "company_sale_data") -> str:
    return _resolve_column_from_registry(table, "vendor_name") or _DEFAULT_VENDOR_NAME_COL


def _line_total_col(table: str = "company_sale_data") -> str:
    return _resolve_column_from_registry(table, "line_total") or _DEFAULT_LINE_TOTAL_COL


def _price_now_col(table: str = "company_sale_data") -> str:
    return _resolve_column_from_registry(table, "price_now") or _DEFAULT_PRICE_NOW_COL


def _item_title_col(table: str = "company_sale_data") -> str:
    return _resolve_column_from_registry(table, "item_title") or _DEFAULT_ITEM_TITLE_COL


def _sale_returned_col(table: str = "company_sale_data") -> str:
    return _resolve_column_from_registry(table, "sale_returned") or _DEFAULT_SALE_RETURNED_COL


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
COPILOT_TYPES = {"sales", "inventory", "customer", "artist", "vendor"}


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


def _edition_name_from_question(q: str) -> str | None:
    """
    Map natural-language edition wording to company_sale_data.EditionName (see schema / ERP labels).
    """
    if re.search(r"\bnon[- ]?stock\b", q):
        return "Non Stock"
    if "limited" in q and "edition" in q:
        return "Limited"
    if "open" in q and "edition" in q:
        return "Open"
    if "unique" in q and "edition" in q:
        return "Unique"
    return None


_ALLOWED_EDITION_NAMES = frozenset({"Unique", "Open", "Limited", "Non Stock"})


def _sql_literal_edition_name(name: str) -> str:
    """Safe single-quoted literal for EditionName IN (only allowlisted values)."""
    if name not in _ALLOWED_EDITION_NAMES:
        return "'Unique'"
    return "'" + name.replace("'", "''") + "'"


def _score(q: str, words: list[str]) -> int:
    return sum(1 for w in words if w in q)


def _detect_intent(q: str, copilot: Literal["sales", "inventory", "customer", "artist", "vendor"] | None = None) -> str:
    if copilot == "customer":
        customer_candidates = {
            "customer_top_by_ltv": _score(q, ["top", "customer", "customers", "ltv", "revenue", "buyer", "buyers"]),
            "customer_overdue_balances": _score(q, ["overdue", "balance", "balances", "due", "outstanding"]),
            "customer_followup_candidates": _score(q, ["inactive", "followup", "follow-up", "no purchase", "stale"]),
        }
        return max(customer_candidates, key=lambda k: customer_candidates[k])

    if copilot == "artist":
        artist_candidates = {
            "artist_sales_performance": _score(q, ["artist", "artists", "top", "sales", "performance"]),
            "artist_top_collectors": _score(q, ["artist", "collector", "collectors", "customer", "buyers"]),
            "artist_returns_profile": _score(q, ["artist", "return", "returns"]),
        }
        return max(artist_candidates, key=lambda k: artist_candidates[k])

    if copilot == "vendor":
        vendor_candidates = {
            "vendor_outstanding_payables": _score(q, ["vendor", "payable", "payables", "outstanding", "due"]),
            "vendor_overdue_invoices": _score(q, ["vendor", "overdue", "invoice", "invoices"]),
            "vendor_spend_trend": _score(q, ["vendor", "spend", "trend", "month", "monthly"]),
        }
        return max(vendor_candidates, key=lambda k: vendor_candidates[k])

    # Strong signal: artist ranking + edition type + sales (deterministic fallback when LLM unavailable).
    en = _edition_name_from_question(q)
    if en and ("artist" in q or "artists" in q) and any(
        t in q for t in ("sale", "sales", "revenue", "sold", "selling", "most", "top", "best", "many")
    ):
        return "top_artists_by_edition_sales"

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


def generate_query(
    question: str,
    copilot: Literal["sales", "inventory", "customer", "artist", "vendor"] | None = None,
) -> QuerySpec:
    q = _normalize(question)
    if copilot not in COPILOT_TYPES:
        copilot = None
    limit, requested_limit = _extract_limit(q)
    window_expr, window_label = _extract_window_expr(q)
    intent = _detect_intent(q, copilot=copilot)
    if intent == "top_artists_by_edition_sales" and window_label == "last_30_days_default":
        # "Most …" / no explicit window: rank all-time line-level sales, not last 30 days.
        window_expr = "DATE('1970-01-01')"
        window_label = "all_time_default"

    if intent == "customer_top_by_ltv":
        return QuerySpec(
            intent=intent,
            sql=f"""
            SELECT
              s.idcompany_customer AS idcompany_contact,
              c.full_name AS customer_name,
              ROUND(SUM(s.total), 2) AS lifetime_revenue_gross
            FROM company_sale s
            LEFT JOIN company_contact_data1 c
              ON c.idcompany_contact = s.idcompany_customer
             AND c.idcompany = s.idcompany
            WHERE s.idcompany = %(idcompany)s
              AND s.is_sale = 1
              AND COALESCE(s.isreturned, 0) = 0
            GROUP BY s.idcompany_customer, c.full_name
            ORDER BY lifetime_revenue_gross DESC
            LIMIT {limit}
            """.strip(),
            params={},
            requested_limit=requested_limit,
            applied_limit=limit,
            window_label="lifetime",
        )

    if intent == "customer_overdue_balances":
        return QuerySpec(
            intent=intent,
            sql=f"""
            SELECT
              s.idcompany_customer AS idcompany_contact,
              c.full_name AS customer_name,
              ROUND(SUM(p.amount_due - COALESCE(p.amount_paid, 0)), 2) AS overdue_balance
            FROM company_sale_payment p
            JOIN company_sale s
              ON s.idcompany_sale = p.idcompany_sale
             AND s.idcompany = p.idcompany
            LEFT JOIN company_contact_data1 c
              ON c.idcompany_contact = s.idcompany_customer
             AND c.idcompany = s.idcompany
            WHERE p.idcompany = %(idcompany)s
              AND p.date_paid IS NULL
              AND p.date_due < NOW()
            GROUP BY s.idcompany_customer, c.full_name
            ORDER BY overdue_balance DESC
            LIMIT {limit}
            """.strip(),
            params={},
            requested_limit=requested_limit,
            applied_limit=limit,
            window_label=window_label,
        )

    if intent == "customer_followup_candidates":
        return QuerySpec(
            intent=intent,
            sql=f"""
            SELECT
              c.idcompany_contact,
              c.full_name AS customer_name,
              {_date_expr("MAX(s.sale_date)")} AS last_purchase_date,
              ROUND(COALESCE(SUM(s.total), 0), 2) AS lifetime_revenue_gross
            FROM company_contact_data1 c
            LEFT JOIN company_sale s
              ON s.idcompany_customer = c.idcompany_contact
             AND s.idcompany = c.idcompany
             AND s.is_sale = 1
             AND COALESCE(s.isreturned, 0) = 0
            WHERE c.idcompany = %(idcompany)s
            GROUP BY c.idcompany_contact, c.full_name
            HAVING MAX(s.sale_date) IS NULL OR MAX(s.sale_date) < DATE_SUB(NOW(), INTERVAL 90 DAY)
            ORDER BY lifetime_revenue_gross DESC
            LIMIT {limit}
            """.strip(),
            params={},
            requested_limit=requested_limit,
            applied_limit=limit,
            window_label="inactive_90_days",
        )

    if intent == "artist_sales_performance":
        an_col = _artist_name_col("company_sale_data")
        lt_col = _line_total_col("company_sale_data")
        sr_col = _sale_returned_col("company_sale_data")
        return QuerySpec(
            intent=intent,
            sql=f"""
            SELECT
              d.idcompany_artist,
              d.{an_col},
              ROUND(SUM(d.{lt_col}), 2) AS total_sales_net
            FROM company_sale_data d
            WHERE d.idcompany = %(idcompany)s
              AND d.is_sale = 1
              AND COALESCE(d.{sr_col}, 0) = 0
              AND d.sale_date >= {window_expr}
            GROUP BY d.idcompany_artist, d.{an_col}
            ORDER BY total_sales_net DESC
            LIMIT {limit}
            """.strip(),
            params={},
            requested_limit=requested_limit,
            applied_limit=limit,
            window_label=window_label,
        )

    if intent == "artist_top_collectors":
        an_col = _artist_name_col("company_sale_data")
        cn_col = _customer_name_col("company_sale_data")
        lt_col = _line_total_col("company_sale_data")
        sr_col = _sale_returned_col("company_sale_data")
        return QuerySpec(
            intent=intent,
            sql=f"""
            SELECT
              d.{an_col},
              d.{cn_col},
              ROUND(SUM(d.{lt_col}), 2) AS total_sales_net
            FROM company_sale_data d
            WHERE d.idcompany = %(idcompany)s
              AND d.is_sale = 1
              AND COALESCE(d.{sr_col}, 0) = 0
              AND d.sale_date >= {window_expr}
            GROUP BY d.{an_col}, d.{cn_col}
            ORDER BY total_sales_net DESC
            LIMIT {limit}
            """.strip(),
            params={},
            requested_limit=requested_limit,
            applied_limit=limit,
            window_label=window_label,
        )

    if intent == "artist_returns_profile":
        an_col = _artist_name_col("company_sale_data")
        lt_col = _line_total_col("company_sale_data")
        sr_col = _sale_returned_col("company_sale_data")
        return QuerySpec(
            intent=intent,
            sql=f"""
            SELECT
              d.{an_col},
              COUNT(*) AS returned_line_count,
              ROUND(SUM(d.{lt_col}), 2) AS returned_amount_net
            FROM company_sale_data d
            WHERE d.idcompany = %(idcompany)s
              AND COALESCE(d.{sr_col}, 0) = 1
              AND d.sale_date >= {window_expr}
            GROUP BY d.{an_col}
            ORDER BY returned_amount_net DESC
            LIMIT {limit}
            """.strip(),
            params={},
            requested_limit=requested_limit,
            applied_limit=limit,
            window_label=window_label,
        )

    if intent == "vendor_outstanding_payables":
        return QuerySpec(
            intent=intent,
            sql=f"""
            SELECT
              s.idcompany_customer AS idcompany_vendor,
              c.full_name AS vendor_name,
              ROUND(SUM(p.amount_due - COALESCE(p.amount_paid, 0)), 2) AS outstanding_amount
            FROM company_sale_payment p
            JOIN company_sale s
              ON s.idcompany_sale = p.idcompany_sale
             AND s.idcompany = p.idcompany
            LEFT JOIN company_contact_data1 c
              ON c.idcompany_contact = s.idcompany_customer
             AND c.idcompany = s.idcompany
            WHERE p.idcompany = %(idcompany)s
              AND p.date_paid IS NULL
            GROUP BY s.idcompany_customer, c.full_name
            ORDER BY outstanding_amount DESC
            LIMIT {limit}
            """.strip(),
            params={},
            requested_limit=requested_limit,
            applied_limit=limit,
            window_label=window_label,
        )

    if intent == "vendor_overdue_invoices":
        return QuerySpec(
            intent=intent,
            sql=f"""
            SELECT
              p.idcompany_sale,
              s.idcompany_customer AS idcompany_vendor,
              c.full_name AS vendor_name,
              {_date_expr("p.date_due")} AS date_due,
              ROUND(p.amount_due - COALESCE(p.amount_paid, 0), 2) AS overdue_amount
            FROM company_sale_payment p
            JOIN company_sale s
              ON s.idcompany_sale = p.idcompany_sale
             AND s.idcompany = p.idcompany
            LEFT JOIN company_contact_data1 c
              ON c.idcompany_contact = s.idcompany_customer
             AND c.idcompany = s.idcompany
            WHERE p.idcompany = %(idcompany)s
              AND p.date_paid IS NULL
              AND p.date_due < NOW()
            ORDER BY overdue_amount DESC, p.date_due ASC
            LIMIT {limit}
            """.strip(),
            params={},
            requested_limit=requested_limit,
            applied_limit=limit,
            window_label=window_label,
        )

    if intent == "vendor_spend_trend":
        mb = _month_bucket_us_expr("s.sale_date")
        return QuerySpec(
            intent=intent,
            sql=f"""
            SELECT
              {mb} AS month_key,
              ROUND(SUM(s.total), 2) AS spend_gross
            FROM company_sale s
            WHERE s.idcompany = %(idcompany)s
              AND s.is_sale = 1
              AND COALESCE(s.isreturned, 0) = 0
              AND s.sale_date >= {window_expr}
            GROUP BY DATE_FORMAT(s.sale_date, '%Y-%m')
            ORDER BY MIN(s.sale_date)
            LIMIT {limit}
            """.strip(),
            params={},
            requested_limit=requested_limit,
            applied_limit=limit,
            window_label=window_label,
        )

    if intent == "recent_sold_items":
        an_col = _artist_name_col("company_sale_data")
        cn_col = _customer_name_col("company_sale_data")
        it_col = _item_title_col("company_sale_data")
        pn_col = _price_now_col("company_sale_data")
        lt_col = _line_total_col("company_sale_data")
        sr_col = _sale_returned_col("company_sale_data")
        return QuerySpec(
            intent=intent,
            sql=f"""
            SELECT
              {_date_expr("d.sale_date")} AS sale_date,
              d.transaction_number,
              d.idcompany_item,
              d.{it_col},
              d.{an_col},
              d.{cn_col},
              d.qty,
              d.{pn_col},
              d.{lt_col}
            FROM company_sale_data d
            WHERE d.idcompany = %(idcompany)s
              AND d.is_sale = 1
              AND COALESCE(d.{sr_col}, 0) = 0
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

    if intent == "top_artists_by_edition_sales":
        en = _edition_name_from_question(q) or "Unique"
        en_lit = _sql_literal_edition_name(en)
        an_col = _artist_name_col("company_sale_data")
        lt_col = _line_total_col("company_sale_data")
        sr_col = _sale_returned_col("company_sale_data")
        artist_display = f"COALESCE(NULLIF(TRIM(d.{an_col}), ''), 'Anonymous')"
        return QuerySpec(
            intent=intent,
            sql=f"""
            SELECT
              {artist_display} AS ArtistName,
              COUNT(*) AS edition_sales_count,
              ROUND(SUM(d.{lt_col}), 2) AS edition_revenue_net
            FROM company_sale_data d
            WHERE d.idcompany = %(idcompany)s
              AND d.is_sale = 1
              AND COALESCE(d.{sr_col}, 0) = 0
              AND d.EditionName = {en_lit}
              AND d.sale_date >= {window_expr}
            GROUP BY {artist_display}
            ORDER BY edition_sales_count DESC, edition_revenue_net DESC
            LIMIT {limit}
            """.strip(),
            params={},
            requested_limit=requested_limit,
            applied_limit=limit,
            window_label=window_label,
        )

    if intent == "top_artists_by_total_sales":
        an_col = _artist_name_col("company_sale_data")
        lt_col = _line_total_col("company_sale_data")
        sr_col = _sale_returned_col("company_sale_data")
        artist_display = f"COALESCE(NULLIF(TRIM(d.{an_col}), ''), 'Anonymous')"
        return QuerySpec(
            intent=intent,
            sql=f"""
            SELECT
              {artist_display} AS ArtistName,
              ROUND(SUM(d.{lt_col}), 2) AS total_sales_net
            FROM company_sale_data d
            WHERE d.idcompany = %(idcompany)s
              AND d.is_sale = 1
              AND COALESCE(d.{sr_col}, 0) = 0
              AND d.sale_date >= {window_expr}
            GROUP BY {artist_display}
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

