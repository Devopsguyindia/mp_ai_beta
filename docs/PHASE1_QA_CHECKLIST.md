# Phase 1 QA checklist – ERP AI Insights / V3.1

## Regression – existing V3 dashboard

1. Sign in to the widget (`/#/login`), open **Dashboard** (`/#/dashboard`).
2. Ask a normal V3 question **without** new body fields (`erp_module`, `strict_module_scope` unset).
3. Confirm answers, charts (if enabled), debug, and report suggestions behave as before.
4. Optional: call `POST /v3/ask` with curl/Postman using the **old** JSON payload only; response must not require `scope_blocked`.

## New API – memory recent

1. `GET /v3/memory/recent?idcompany=<n>&access_token=<jwt>&copilot=customer&limit=10`
2. Expect `200` and `items` array with `question`, `copilot`, `created_at` when MySQL memory is enabled.

## Module insights UI (standalone)

1. Navigate to `/#/module-insights/contact` (logged in).
2. Confirm **Show work (debug)** and **Display chart output** checkboxes default **on**.
3. Ask a contact-related question; confirm rows / generation / intent cards update.
4. Open **Suggestions & history** tab; confirm last 10 server prompts (if any).
5. Open **Details** tab; confirm debug JSON when `Show work` is on.
6. Repeat for `inventory` and `sales`.
7. Navigate to `/#/module-insights/reports`; confirm **Report usage insights** loads (top / recent / smart defaults) and re-run opens a blob (same as dashboard).

## Module scope (strict)

1. From `module-insights/contact`, ask a question that is clearly **inventory-only** (e.g. stock QOH with no customer context).
2. With `strict_module_scope` + LLM enabled, expect a refusal and `scope_blocked: true` in JSON (when using API directly).
3. Set `V3_MODULE_SCOPE_LLM_ENABLED=0` to exercise heuristic-only behavior.

## ERP integration (manual)

- [ ] Modal opens on same page without new window.
- [ ] Token passed from ERP; no second login screen.
- [ ] CORS allows ERP origin to `copilot-api`.
