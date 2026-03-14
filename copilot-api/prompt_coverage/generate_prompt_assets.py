from __future__ import annotations

import csv
import json
from pathlib import Path


BASE = Path(__file__).resolve().parent


INTENTS_BY_COPILOT = {
    "sales": [
        "sales_recent_sold_items",
        "sales_top_customers_revenue",
        "sales_top_artists_totalsales",
        "sales_revenue_trend",
        "sales_returns_summary",
        "sales_discount_anomalies",
        "sales_margin_anomalies",
        "sales_quote_conversion",
        "sales_location_performance",
        "sales_layaway_outstanding",
    ],
    "inventory": [
        "inventory_total_stock",
        "inventory_aging_items",
        "inventory_top_unsold_by_value",
        "inventory_turnover",
        "inventory_location_mismatch",
        "inventory_stock_movement",
        "inventory_low_stock_alert",
        "inventory_missing_data",
        "inventory_edition_mix",
        "inventory_recent_additions",
    ],
    "customer": [
        "customer_top_by_ltv",
        "customer_inactive_high_value",
        "customer_new_acquisitions",
        "customer_repeat_rate",
        "customer_overdue_balances",
        "customer_conversion_funnel",
        "customer_interest_by_artist",
        "customer_followup_candidates",
        "customer_segment_performance",
        "customer_contact_data_quality",
    ],
    "artist": [
        "artist_sales_performance",
        "artist_sell_through_rate",
        "artist_inventory_aging",
        "artist_price_band_performance",
        "artist_top_collectors",
        "artist_discount_risk",
        "artist_commission_due",
        "artist_exhibition_performance",
        "artist_time_to_sell",
        "artist_returns_profile",
    ],
    "vendor": [
        "vendor_outstanding_payables",
        "vendor_spend_trend",
        "vendor_turnaround_comparison",
        "vendor_rework_rate",
        "vendor_shipment_cost_trend",
        "vendor_overdue_invoices",
        "vendor_duplicate_invoices",
        "vendor_service_overlap",
        "vendor_quality_anomalies",
        "vendor_commitments_upcoming",
    ],
}


def build_intent_catalog() -> dict:
    return {"version": "v2", "copilots": INTENTS_BY_COPILOT}


def build_contracts() -> dict:
    return {
        "version": "v2",
        "contracts": [
            {"contract_id": "sales_header_aggregate", "required_filters": ["idcompany"], "preferred_relations": ["company_sale"], "result_type": "kpi_or_trend", "enforce_limit": False},
            {"contract_id": "sales_lineitem_detail", "required_filters": ["idcompany"], "preferred_relations": ["company_sale_data"], "result_type": "table", "enforce_limit": True, "default_limit": 10, "max_limit": 200},
            {"contract_id": "sales_layaway_due", "required_filters": ["idcompany"], "preferred_relations": ["company_sale_payment", "company_sale"], "result_type": "kpi_or_table", "enforce_limit": True, "default_limit": 100, "max_limit": 200},
            {"contract_id": "inventory_item_detail", "required_filters": ["idcompany"], "preferred_relations": ["company_item_data", "company_item"], "result_type": "table", "enforce_limit": True, "default_limit": 25, "max_limit": 200},
            {"contract_id": "inventory_aggregate", "required_filters": ["idcompany"], "preferred_relations": ["company_item_data", "company_item"], "result_type": "kpi_or_trend", "enforce_limit": False},
            {"contract_id": "contact_aggregate", "required_filters": ["idcompany"], "preferred_relations": ["company_contact_data1", "company_contact"], "result_type": "kpi_or_trend", "enforce_limit": False},
            {"contract_id": "contact_detail", "required_filters": ["idcompany"], "preferred_relations": ["company_contact_data1"], "result_type": "table", "enforce_limit": True, "default_limit": 25, "max_limit": 200},
            {"contract_id": "artist_aggregate", "required_filters": ["idcompany"], "preferred_relations": ["company_sale_data", "company_item_data", "company_artist"], "result_type": "kpi_or_trend", "enforce_limit": False},
            {"contract_id": "artist_detail", "required_filters": ["idcompany"], "preferred_relations": ["company_sale_data", "company_item_data"], "result_type": "table", "enforce_limit": True, "default_limit": 25, "max_limit": 200},
            {"contract_id": "vendor_aggregate", "required_filters": ["idcompany"], "preferred_relations": ["company_vendor", "company_contact_data1", "company_sale_data"], "result_type": "kpi_or_trend", "enforce_limit": False},
            {"contract_id": "vendor_detail", "required_filters": ["idcompany"], "preferred_relations": ["company_vendor", "company_contact_data1", "company_sale_payment"], "result_type": "table", "enforce_limit": True, "default_limit": 25, "max_limit": 200},
        ],
    }


def build_templates() -> list[dict]:
    # 3 templates x 10 intents x 5 copilots = 150 templates.
    return [
        # Sales
        {"intent_id": "sales_recent_sold_items", "template": "recent {limit} sold items"},
        {"intent_id": "sales_recent_sold_items", "template": "show last {limit} sold artworks"},
        {"intent_id": "sales_recent_sold_items", "template": "latest {limit} sold item lines"},
        {"intent_id": "sales_top_customers_revenue", "template": "top {limit} customers by revenue in {window}"},
        {"intent_id": "sales_top_customers_revenue", "template": "who are the top {limit} buyers by revenue for {window}"},
        {"intent_id": "sales_top_customers_revenue", "template": "highest revenue customers {window} top {limit}"},
        {"intent_id": "sales_top_artists_totalsales", "template": "top {limit} artists by total sales in {window}"},
        {"intent_id": "sales_top_artists_totalsales", "template": "best selling artists for {window} top {limit}"},
        {"intent_id": "sales_top_artists_totalsales", "template": "rank artists by total sales for {window}, top {limit}"},
        {"intent_id": "sales_revenue_trend", "template": "revenue trend for {window} by {bucket}"},
        {"intent_id": "sales_revenue_trend", "template": "show revenue over time for {window} grouped by {bucket}"},
        {"intent_id": "sales_revenue_trend", "template": "plot revenue timeline in {window} by {bucket}"},
        {"intent_id": "sales_returns_summary", "template": "returns summary for {window}"},
        {"intent_id": "sales_returns_summary", "template": "how many returns happened in {window}"},
        {"intent_id": "sales_returns_summary", "template": "return amount and count for {window}"},
        {"intent_id": "sales_discount_anomalies", "template": "show {limit} highest discount sale lines in {window}"},
        {"intent_id": "sales_discount_anomalies", "template": "discount anomalies for {window}, top {limit}"},
        {"intent_id": "sales_discount_anomalies", "template": "which sold items had unusually high discounts in {window}"},
        {"intent_id": "sales_margin_anomalies", "template": "show {limit} negative margin sold items in {window}"},
        {"intent_id": "sales_margin_anomalies", "template": "items sold below cost in {window}, top {limit}"},
        {"intent_id": "sales_margin_anomalies", "template": "margin anomaly sale lines for {window}"},
        {"intent_id": "sales_quote_conversion", "template": "quote to sale conversion for {window}"},
        {"intent_id": "sales_quote_conversion", "template": "conversion rate from quote to sale in {window}"},
        {"intent_id": "sales_quote_conversion", "template": "how many quotes converted in {window}"},
        {"intent_id": "sales_location_performance", "template": "top {limit} locations by revenue in {window}"},
        {"intent_id": "sales_location_performance", "template": "location wise sales performance for {window}"},
        {"intent_id": "sales_location_performance", "template": "compare sales by location in {window}"},
        {"intent_id": "sales_layaway_outstanding", "template": "layaway outstanding due summary for {window}"},
        {"intent_id": "sales_layaway_outstanding", "template": "overdue layaway amount for {window}"},
        {"intent_id": "sales_layaway_outstanding", "template": "show {limit} layaway sales with highest overdue in {window}"},
        # Inventory
        {"intent_id": "inventory_total_stock", "template": "inventory count and qoh summary for {window}"},
        {"intent_id": "inventory_total_stock", "template": "how many items are in stock in {window}"},
        {"intent_id": "inventory_total_stock", "template": "total inventory quantity on hand for {window}"},
        {"intent_id": "inventory_aging_items", "template": "show {limit} oldest unsold items"},
        {"intent_id": "inventory_aging_items", "template": "inventory aging report top {limit}"},
        {"intent_id": "inventory_aging_items", "template": "items older than {age_days} days top {limit}"},
        {"intent_id": "inventory_top_unsold_by_value", "template": "top {limit} unsold items by asking price"},
        {"intent_id": "inventory_top_unsold_by_value", "template": "highest value unsold inventory top {limit}"},
        {"intent_id": "inventory_top_unsold_by_value", "template": "show top {limit} unsold stock by total asking value"},
        {"intent_id": "inventory_turnover", "template": "inventory turnover for {window}"},
        {"intent_id": "inventory_turnover", "template": "stock turnover ratio in {window}"},
        {"intent_id": "inventory_turnover", "template": "how fast inventory moved in {window}"},
        {"intent_id": "inventory_location_mismatch", "template": "stock location mismatch anomalies top {limit}"},
        {"intent_id": "inventory_location_mismatch", "template": "find items where qoh and movement logs mismatch"},
        {"intent_id": "inventory_location_mismatch", "template": "location discrepancy report for inventory top {limit}"},
        {"intent_id": "inventory_stock_movement", "template": "recent {limit} stock movements"},
        {"intent_id": "inventory_stock_movement", "template": "show inventory transfers in {window} top {limit}"},
        {"intent_id": "inventory_stock_movement", "template": "item movement history for {window} top {limit}"},
        {"intent_id": "inventory_low_stock_alert", "template": "low stock alerts top {limit}"},
        {"intent_id": "inventory_low_stock_alert", "template": "items below reorder quantity top {limit}"},
        {"intent_id": "inventory_low_stock_alert", "template": "which inventory items are low in stock"},
        {"intent_id": "inventory_missing_data", "template": "items missing critical fields top {limit}"},
        {"intent_id": "inventory_missing_data", "template": "inventory data quality issues in {window}"},
        {"intent_id": "inventory_missing_data", "template": "show items with missing price artist or title top {limit}"},
        {"intent_id": "inventory_edition_mix", "template": "edition mix unique open limited nonstock in {window}"},
        {"intent_id": "inventory_edition_mix", "template": "count items by edition type for {window}"},
        {"intent_id": "inventory_edition_mix", "template": "edition type distribution over {window}"},
        {"intent_id": "inventory_recent_additions", "template": "recent {limit} inventory additions"},
        {"intent_id": "inventory_recent_additions", "template": "latest added items in {window} top {limit}"},
        {"intent_id": "inventory_recent_additions", "template": "newly received inventory list top {limit}"},
        # Customer
        {"intent_id": "customer_top_by_ltv", "template": "top {limit} customers by lifetime value"},
        {"intent_id": "customer_top_by_ltv", "template": "highest value collectors top {limit}"},
        {"intent_id": "customer_top_by_ltv", "template": "rank customers by lifetime spend top {limit}"},
        {"intent_id": "customer_inactive_high_value", "template": "high value customers inactive for {window}"},
        {"intent_id": "customer_inactive_high_value", "template": "top inactive customers with prior high spend in {window}"},
        {"intent_id": "customer_inactive_high_value", "template": "which high value customers have gone inactive for {window}"},
        {"intent_id": "customer_new_acquisitions", "template": "new customers acquired in {window}"},
        {"intent_id": "customer_new_acquisitions", "template": "new collectors added in {window}"},
        {"intent_id": "customer_new_acquisitions", "template": "customer acquisition summary for {window}"},
        {"intent_id": "customer_repeat_rate", "template": "repeat purchase rate for {window}"},
        {"intent_id": "customer_repeat_rate", "template": "how many repeat buyers in {window}"},
        {"intent_id": "customer_repeat_rate", "template": "customer repeat frequency trend in {window}"},
        {"intent_id": "customer_overdue_balances", "template": "customers with overdue balances top {limit}"},
        {"intent_id": "customer_overdue_balances", "template": "top {limit} customers with pending receivables"},
        {"intent_id": "customer_overdue_balances", "template": "overdue dues by customer in {window}"},
        {"intent_id": "customer_conversion_funnel", "template": "customer conversion funnel in {window}"},
        {"intent_id": "customer_conversion_funnel", "template": "inquiry to quote to sale conversion by customer for {window}"},
        {"intent_id": "customer_conversion_funnel", "template": "customer conversion rate summary in {window}"},
        {"intent_id": "customer_interest_by_artist", "template": "customers interested in artist for {window} top {limit}"},
        {"intent_id": "customer_interest_by_artist", "template": "show customer interest by artist in {window}"},
        {"intent_id": "customer_interest_by_artist", "template": "which customers track artist demand in {window}"},
        {"intent_id": "customer_followup_candidates", "template": "follow-up candidates among customers top {limit}"},
        {"intent_id": "customer_followup_candidates", "template": "which customers need follow-up in {window}"},
        {"intent_id": "customer_followup_candidates", "template": "customer next-action shortlist top {limit}"},
        {"intent_id": "customer_segment_performance", "template": "customer segment performance in {window}"},
        {"intent_id": "customer_segment_performance", "template": "compare customer segments by revenue in {window}"},
        {"intent_id": "customer_segment_performance", "template": "segment wise customer sales trend in {window}"},
        {"intent_id": "customer_contact_data_quality", "template": "customer contact data quality issues top {limit}"},
        {"intent_id": "customer_contact_data_quality", "template": "customers with missing email or phone top {limit}"},
        {"intent_id": "customer_contact_data_quality", "template": "customer profile completeness report in {window}"},
        # Artist
        {"intent_id": "artist_sales_performance", "template": "artist sales performance in {window} top {limit}"},
        {"intent_id": "artist_sales_performance", "template": "top {limit} artists by revenue in {window}"},
        {"intent_id": "artist_sales_performance", "template": "artist wise sales summary in {window}"},
        {"intent_id": "artist_sell_through_rate", "template": "artist sell through rate in {window}"},
        {"intent_id": "artist_sell_through_rate", "template": "which artists have best sell through in {window}"},
        {"intent_id": "artist_sell_through_rate", "template": "sell through comparison by artist for {window}"},
        {"intent_id": "artist_inventory_aging", "template": "artist inventory aging top {limit}"},
        {"intent_id": "artist_inventory_aging", "template": "which artist items are aging in stock for {window}"},
        {"intent_id": "artist_inventory_aging", "template": "stale inventory by artist top {limit}"},
        {"intent_id": "artist_price_band_performance", "template": "artist performance by price band in {window}"},
        {"intent_id": "artist_price_band_performance", "template": "price band wise artist sales in {window}"},
        {"intent_id": "artist_price_band_performance", "template": "which artist price ranges perform best in {window}"},
        {"intent_id": "artist_top_collectors", "template": "top collectors per artist in {window} top {limit}"},
        {"intent_id": "artist_top_collectors", "template": "who buys each artist most in {window}"},
        {"intent_id": "artist_top_collectors", "template": "artist collector concentration report for {window}"},
        {"intent_id": "artist_discount_risk", "template": "artist discount risk anomalies in {window} top {limit}"},
        {"intent_id": "artist_discount_risk", "template": "which artists have high discount sales in {window}"},
        {"intent_id": "artist_discount_risk", "template": "discount outliers by artist for {window}"},
        {"intent_id": "artist_commission_due", "template": "artist commission due summary in {window}"},
        {"intent_id": "artist_commission_due", "template": "which artists have pending commission in {window}"},
        {"intent_id": "artist_commission_due", "template": "artist settlement due list top {limit}"},
        {"intent_id": "artist_exhibition_performance", "template": "artist exhibition performance in {window}"},
        {"intent_id": "artist_exhibition_performance", "template": "compare artist outcomes by exhibition in {window}"},
        {"intent_id": "artist_exhibition_performance", "template": "exhibition sales by artist for {window}"},
        {"intent_id": "artist_time_to_sell", "template": "artist time to sell in {window}"},
        {"intent_id": "artist_time_to_sell", "template": "average days to sell by artist for {window}"},
        {"intent_id": "artist_time_to_sell", "template": "which artists sell fastest in {window}"},
        {"intent_id": "artist_returns_profile", "template": "artist returns profile in {window}"},
        {"intent_id": "artist_returns_profile", "template": "return rate by artist for {window}"},
        {"intent_id": "artist_returns_profile", "template": "artists with most returns in {window} top {limit}"},
        # Vendor
        {"intent_id": "vendor_outstanding_payables", "template": "vendor outstanding payables top {limit}"},
        {"intent_id": "vendor_outstanding_payables", "template": "which vendors are due for payment in {window}"},
        {"intent_id": "vendor_outstanding_payables", "template": "vendor dues summary for {window}"},
        {"intent_id": "vendor_spend_trend", "template": "vendor spend trend in {window}"},
        {"intent_id": "vendor_spend_trend", "template": "how vendor spend changed over {window}"},
        {"intent_id": "vendor_spend_trend", "template": "vendor cost timeline for {window}"},
        {"intent_id": "vendor_turnaround_comparison", "template": "vendor turnaround comparison in {window}"},
        {"intent_id": "vendor_turnaround_comparison", "template": "which vendors deliver fastest in {window}"},
        {"intent_id": "vendor_turnaround_comparison", "template": "compare vendor lead times for {window}"},
        {"intent_id": "vendor_rework_rate", "template": "vendor rework rate in {window}"},
        {"intent_id": "vendor_rework_rate", "template": "which vendors have high rework in {window}"},
        {"intent_id": "vendor_rework_rate", "template": "rework anomalies by vendor top {limit}"},
        {"intent_id": "vendor_shipment_cost_trend", "template": "vendor shipment cost trend in {window}"},
        {"intent_id": "vendor_shipment_cost_trend", "template": "shipping spend by vendor for {window}"},
        {"intent_id": "vendor_shipment_cost_trend", "template": "carrier vendor cost comparison in {window}"},
        {"intent_id": "vendor_overdue_invoices", "template": "overdue vendor invoices top {limit}"},
        {"intent_id": "vendor_overdue_invoices", "template": "vendors with overdue invoices in {window}"},
        {"intent_id": "vendor_overdue_invoices", "template": "pending vendor invoice dues for {window}"},
        {"intent_id": "vendor_duplicate_invoices", "template": "possible duplicate vendor invoices top {limit}"},
        {"intent_id": "vendor_duplicate_invoices", "template": "duplicate invoice risk by vendor in {window}"},
        {"intent_id": "vendor_duplicate_invoices", "template": "find repeated vendor invoices for {window}"},
        {"intent_id": "vendor_service_overlap", "template": "vendor service overlap opportunities in {window}"},
        {"intent_id": "vendor_service_overlap", "template": "which vendors provide overlapping services in {window}"},
        {"intent_id": "vendor_service_overlap", "template": "consolidation opportunities across vendors top {limit}"},
        {"intent_id": "vendor_quality_anomalies", "template": "vendor quality anomalies in {window} top {limit}"},
        {"intent_id": "vendor_quality_anomalies", "template": "which vendors have quality issues in {window}"},
        {"intent_id": "vendor_quality_anomalies", "template": "vendor quality risk report for {window}"},
        {"intent_id": "vendor_commitments_upcoming", "template": "upcoming vendor commitments in {window}"},
        {"intent_id": "vendor_commitments_upcoming", "template": "vendor due tasks and schedules in {window}"},
        {"intent_id": "vendor_commitments_upcoming", "template": "next vendor obligations top {limit}"},
    ]


def _contract_for_intent(intent: str) -> str:
    if intent.startswith("sales_"):
        if intent in {"sales_recent_sold_items", "sales_discount_anomalies", "sales_margin_anomalies"}:
            return "sales_lineitem_detail"
        if intent == "sales_layaway_outstanding":
            return "sales_layaway_due"
        return "sales_header_aggregate"
    if intent.startswith("inventory_"):
        if intent in {
            "inventory_aging_items",
            "inventory_top_unsold_by_value",
            "inventory_location_mismatch",
            "inventory_stock_movement",
            "inventory_low_stock_alert",
            "inventory_missing_data",
            "inventory_recent_additions",
        }:
            return "inventory_item_detail"
        return "inventory_aggregate"
    if intent.startswith("customer_"):
        if intent in {"customer_followup_candidates", "customer_overdue_balances", "customer_contact_data_quality"}:
            return "contact_detail"
        return "contact_aggregate"
    if intent.startswith("artist_"):
        if intent in {"artist_inventory_aging", "artist_top_collectors", "artist_discount_risk", "artist_commission_due"}:
            return "artist_detail"
        return "artist_aggregate"
    if intent.startswith("vendor_"):
        if intent in {"vendor_outstanding_payables", "vendor_overdue_invoices", "vendor_duplicate_invoices", "vendor_commitments_upcoming"}:
            return "vendor_detail"
        return "vendor_aggregate"
    return "sales_header_aggregate"


def _copilot_for_intent(intent: str) -> str:
    return intent.split("_", 1)[0]


def build_prompt_dataset() -> list[dict]:
    windows = ["last 7 days", "last 30 days", "last 90 days", "this month", "ytd"]
    limits = [5, 10, 20, 25, 50]
    buckets = ["day", "week", "month"]
    ages = [60, 90, 120, 180, 365]

    templates = build_templates()
    prompt_rows: list[dict] = []
    seq = 1

    for t in templates:
        intent = t["intent_id"]
        copilot = _copilot_for_intent(intent)
        base = t["template"]
        for i in range(5):  # 150 templates * 5 = 750 prompts
            question = (
                base.replace("{window}", windows[i % len(windows)])
                .replace("{limit}", str(limits[i % len(limits)]))
                .replace("{bucket}", buckets[i % len(buckets)])
                .replace("{age_days}", str(ages[i % len(ages)]))
            )
            prompt_rows.append(
                {
                    "prompt_id": f"p{seq:04d}",
                    "copilot": copilot,
                    "intent_id": intent,
                    "question": question,
                    "priority": "high" if i < 2 else "medium",
                    "expected_contract_id": _contract_for_intent(intent),
                    "required_filters": ["idcompany"],
                    "safety": {"select_only": True, "idcompany_required": True},
                    "tags": [copilot, intent.split("_", 1)[1]],
                }
            )
            seq += 1
    return prompt_rows


def write_files() -> None:
    BASE.mkdir(parents=True, exist_ok=True)
    intent_catalog = build_intent_catalog()
    contracts = build_contracts()
    templates = build_templates()
    prompts = build_prompt_dataset()

    (BASE / "intent_catalog.json").write_text(json.dumps(intent_catalog, indent=2), encoding="utf-8")
    (BASE / "prompt_to_sql_contracts.json").write_text(json.dumps(contracts, indent=2), encoding="utf-8")

    with (BASE / "prompt_templates.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["intent_id", "template"])
        writer.writeheader()
        writer.writerows(templates)

    with (BASE / "prompt_dataset_v1.jsonl").open("w", encoding="utf-8") as f:
        for row in prompts:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")

    distribution = {}
    for c in INTENTS_BY_COPILOT.keys():
        distribution[c] = sum(1 for r in prompts if r["copilot"] == c)

    summary = {
        "version": "v2",
        "generated_prompt_count": len(prompts),
        "copilot_distribution": distribution,
        "files": [
            "intent_catalog.json",
            "prompt_templates.csv",
            "prompt_to_sql_contracts.json",
            "prompt_dataset_v1.jsonl",
        ],
    }
    (BASE / "generation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    write_files()

