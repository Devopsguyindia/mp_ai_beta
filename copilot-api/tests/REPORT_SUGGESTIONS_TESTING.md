# Report suggestions API — testing guide

Endpoints:

- **`POST /reports/suggestions`** — usage analytics (same path as before).
- **`POST /reports/rerun`** — server proxies **`GET`** to Masterpiece `generateReport` with query string built from `filter_data` JSON (all keys included, empty values as `key=`), and header **`Authorization`** set to the **same token** returned by sign-in (raw value by default). Set **`MP_REPORT_AUTH_BEARER=1`** if MP expects `Bearer <token>`.

Feature flags:

- `REPORT_SUGGESTIONS_ENABLED` (default `1`). Set to `0` to disable suggestions (`404` `report_suggestions_disabled`).
- `REPORT_RERUN_ENABLED` (default `1`). Set to `0` to disable re-run (`404` `report_rerun_disabled`).

Re-run upstream URL override: `MP_REPORT_GENERATE_URL` (default `https://v12-api.masterpiecemanager.com/reports/generateReport`). Timeout: `MP_REPORT_GENERATE_TIMEOUT_SEC` (default `120`). Auth: by default **`Authorization: <raw sign-in token>`**; set **`MP_REPORT_AUTH_BEARER=1`** for **`Authorization: Bearer <token>`**.

## Prerequisites

- MySQL reachable with the same env vars as the rest of copilot-api (`MYSQL_*`).
- Tables exist (see [schema_registry.json](../prompt_coverage/schema_registry.json)):
  - `report_usage`
  - `tb_report_template`
  - `tb_company_report_templates`
- Read-only DB user must be granted `SELECT` on these tables.

## Request body

| Field | Type | Notes |
|-------|------|--------|
| `idcompany` | int | Required. |
| `access_token` | string? | If set, must match JWT `company_id` / `idcompany` with `idcompany`. |
| `user_id` | int? | If set, `top_reports`, `recent_runs`, `smart_defaults`, and `predict_hints` are scoped to that user. |
| `top_n` | int | Default 5, max 50. |
| `recent_n` | int | Default 10, max 100. |
| `smart_default_limit` | int | Default 20. Caps how many distinct reports get a smart-default row. |
| `truncate_filter_data` | bool | Default true. |
| `filter_data_max_chars` | int | Default 4000. |

## Response shape

- `ok`: `true` only if **no** DB errors on any subsection; partial data may still appear with `warnings` if one query fails.
- `top_reports`: `{ report_id, total_usage, report_name?, name_source? }[]` — ranked by `SUM(usage_count)`.
- `recent_runs`: latest rows by `COALESCE(last_used, updated_at, created_at)`.
- `smart_defaults`: for each report in **`top_reports`** (when non-empty), the most-used `filter_hash` / `filter_data` by `SUM(usage_count)`, listed in the **same order as `top_reports`**. If `top_reports` is empty, falls back to reports ordered by highest `usage_sum` first, up to `smart_default_limit`.
- `predict_hints`: weekday histogram for the single most-used report (requires at least 2 runs on the same weekday).
- `warnings`: strings like `top_reports: ...` if a subsection failed (e.g. missing table).

## cURL examples

Replace `BASE`, `TOKEN`, and `COMPANY_ID` as needed.

### 1) Basic (no JWT)

```bash
curl -s -X POST "$BASE/reports/suggestions" \
  -H "Content-Type: application/json" \
  -d "{\"idcompany\": 889, \"top_n\": 5, \"recent_n\": 10}"
```

**Expected:** HTTP 200, JSON with `idcompany: 889`, `top_reports` ordered by usage, `recent_runs` with `filter_hash` / truncated `filter_data` if long.

### 2) With JWT (production-style)

```bash
curl -s -X POST "$BASE/reports/suggestions" \
  -H "Content-Type: application/json" \
  -d "{\"idcompany\": $COMPANY_ID, \"access_token\": \"$TOKEN\", \"user_id\": 42}"
```

**Expected:** 200 if token company matches `idcompany`; **403** `company_mismatch` if they differ; **401** if token cannot be parsed for company.

### 3) Full filter payload (e.g. run-again)

```bash
curl -s -X POST "$BASE/reports/suggestions" \
  -H "Content-Type: application/json" \
  -d "{\"idcompany\": 889, \"truncate_filter_data\": false, \"filter_data_max_chars\": 50000, \"recent_n\": 3}"
```

**Expected:** `recent_runs[].filter_data` contains full JSON string; `filter_data_truncated: false` when under max length.

### 4) Feature disabled

```bash
REPORT_SUGGESTIONS_ENABLED=0 uvicorn app.main:app --port 8001
# then:
curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/reports/suggestions" \
  -H "Content-Type: application/json" \
  -d "{\"idcompany\": 1}"
```

**Expected:** HTTP **404**, body includes `report_suggestions_disabled`.

## Test cases and expected behavior

| # | Scenario | Expected |
|---|----------|----------|
| T1 | Gallery has multiple `report_usage` rows for `report_id` 302 | `top_reports[0]` likely 302 with largest `total_usage`; `report_name` from `tb_report_template.name` or `tb_company_report_templates.name` when join matches |
| T2 | `report_id` only exists in `tb_company_report_templates` | `name_source` is `gallery`; name from company template |
| T3 | `report_id` only in global template | `name_source` is `global` |
| T4 | Unknown `report_id` (no template row) | `report_name` null, `name_source` `unknown` |
| T5 | `user_id` set | Only that user’s rows contribute to aggregates |
| T6 | Same filters, different `usage_count` | `GROUP BY filter_hash` sums counts; smart default picks highest `usage_sum` per report |
| T7 | Many weekdays for top report | `predict_hints` lists up to 3 weekdays with `run_count >= 2` |
| T8 | Fresh DB / empty `report_usage` | Empty arrays, `ok: true`, no warnings |
| T9 | Table missing | `warnings` populated, `ok: false`, affected sections empty |
| T10 | OpenAPI | `GET /docs` shows **report_suggestions** → `POST /reports/suggestions` |

## Local smoke (Python)

From `copilot-api/` with env loaded:

```python
from app.report_suggestions.service import build_report_suggestions
r = build_report_suggestions(
    idcompany=889,
    user_id=None,
    top_n=5,
    recent_n=5,
    smart_default_limit=10,
    truncate_filter_data=True,
    filter_data_max_chars=4000,
)
print(r.model_dump())
```

**Expected:** Same structure as HTTP response; no import errors.
