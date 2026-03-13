from __future__ import annotations

import csv
import json
from pathlib import Path


BASE = Path(__file__).resolve().parent


def build_intent_catalog() -> dict:
    return {
        "version": "v1",
        "copilots": {
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
        },
    }


def build_contracts() -> dict:
    return {
        "version": "v1",
        "contracts": [
            {
                "contract_id": "sales_header_aggregate",
                "required_filters": ["idcompany"],
                "preferred_relations": ["company_sale"],
                "result_type": "kpi_or_trend",
                "enforce_limit": False,
            },
            {
                "contract_id": "sales_lineitem_detail",
                "required_filters": ["idcompany"],
                "preferred_relations": ["company_sale_data"],
                "result_type": "table",
                "enforce_limit": True,
                "default_limit": 10,
                "max_limit": 200,
            },
            {
                "contract_id": "sales_layaway_due",
                "required_filters": ["idcompany"],
                "preferred_relations": ["company_sale_payment", "company_sale"],
                "result_type": "kpi_or_table",
                "enforce_limit": True,
                "default_limit": 100,
                "max_limit": 200,
            },
            {
                "contract_id": "inventory_item_detail",
                "required_filters": ["idcompany"],
                "preferred_relations": ["company_item_data", "company_item"],
                "result_type": "table",
                "enforce_limit": True,
                "default_limit": 25,
                "max_limit": 200,
            },
            {
                "contract_id": "inventory_aggregate",
                "required_filters": ["idcompany"],
                "preferred_relations": ["company_item_data", "company_item"],
                "result_type": "kpi_or_trend",
                "enforce_limit": False,
            },
        ],
    }


def build_templates() -> list[dict]:
    return [
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
    ]


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
        copilot = "sales" if intent.startswith("sales_") else "inventory"
        base = t["template"]

        # Generate 5 variants per template; 60 templates * 5 = 300 prompts.
        for i in range(5):
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
                    "expected_contract_id": (
                        "sales_lineitem_detail"
                        if intent in {
                            "sales_recent_sold_items",
                            "sales_discount_anomalies",
                            "sales_margin_anomalies",
                        }
                        else "sales_layaway_due"
                        if intent == "sales_layaway_outstanding"
                        else "sales_header_aggregate"
                        if intent.startswith("sales_")
                        else "inventory_item_detail"
                        if intent
                        in {
                            "inventory_aging_items",
                            "inventory_top_unsold_by_value",
                            "inventory_location_mismatch",
                            "inventory_stock_movement",
                            "inventory_low_stock_alert",
                            "inventory_missing_data",
                            "inventory_recent_additions",
                        }
                        else "inventory_aggregate"
                    ),
                    "required_filters": ["idcompany"],
                    "safety": {
                        "select_only": True,
                        "idcompany_required": True,
                    },
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

    with (BASE / "intent_catalog.json").open("w", encoding="utf-8") as f:
        json.dump(intent_catalog, f, indent=2)

    with (BASE / "prompt_to_sql_contracts.json").open("w", encoding="utf-8") as f:
        json.dump(contracts, f, indent=2)

    with (BASE / "prompt_templates.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["intent_id", "template"])
        writer.writeheader()
        writer.writerows(templates)

    with (BASE / "prompt_dataset_v1.jsonl").open("w", encoding="utf-8") as f:
        for row in prompts:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")

    summary = {
        "version": "v1",
        "generated_prompt_count": len(prompts),
        "copilot_distribution": {
            "sales": sum(1 for r in prompts if r["copilot"] == "sales"),
            "inventory": sum(1 for r in prompts if r["copilot"] == "inventory"),
        },
        "files": [
            "intent_catalog.json",
            "prompt_templates.csv",
            "prompt_to_sql_contracts.json",
            "prompt_dataset_v1.jsonl",
        ],
    }
    with (BASE / "generation_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    write_files()

