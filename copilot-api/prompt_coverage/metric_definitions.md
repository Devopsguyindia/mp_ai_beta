# Metric Definitions

Canonical definitions for Revenue, TotalSales, Margin, Markup, and Returns. Use these consistently in agents and UI. The source of truth for agents is `schema_registry.json`; this file documents metrics for humans.

---

## Revenue (Gross)

- **Formula:** `SUM(company_sale.total)`
- **Table:** `company_sale`
- **Filters:** `is_sale=1` and `COALESCE(isreturned,0)=0`
- **Tax:** Inclusive
- **Description:** Gross sale amount including tax. Exclude returned sales.

---

## Total Sales (Net)

- **Formula:** `SUM(company_sale_data.LineTotal)`
- **Table:** `company_sale_data`
- **Filters:** `is_sale=1` and `COALESCE(SaleReturned,0)=0`
- **Tax:** Exclusive
- **Description:** Net sale amount before tax. Prefer for line-level analytics. Exclude returned lines.

---

## Margin (Line-Level)

- **Formula:** `(LineTotal - ItemCost) / LineTotal * 100` when `LineTotal > 0`
- **Table:** `company_sale_data`
- **Columns:** `LineTotal`, `ItemCost`
- **Description:** Profit margin as a percentage. Use `ItemCost` from `company_sale_data`.

---

## Markup (Line-Level)

- **Formula:** `(LineTotal - ItemCost) / ItemCost * 100` when `ItemCost > 0`
- **Table:** `company_sale_data`
- **Columns:** `LineTotal`, `ItemCost`
- **Description:** Profit markup as a percentage.

---

## Returns

- **Return sale flag:** `company_sale.isreturned=1` or `company_sale_data.SaleReturned=1`
- **Return line flag:** `company_sale_data.is_returned=1`
- **Exclusion rule:** When computing Revenue or TotalSales, exclude returned sales unless the question is specifically about returns.

---

## Quick Reference for SQL

| Metric       | Exclude returns? | Use table(s)     |
|-------------|-------------------|------------------|
| Revenue     | Yes               | company_sale     |
| TotalSales  | Yes               | company_sale_data|
| Margin      | N/A (line-level)  | company_sale_data|
| Markup      | N/A (line-level)  | company_sale_data|
| Returns     | N/A               | company_sale, company_sale_data |
