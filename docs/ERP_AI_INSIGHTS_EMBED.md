# ERP AI Insights – embedding the sub-copilot

This document describes how the **standalone widget** exposes **Module AI Insights** for integration into the main Angular 12 ERP (same browser tab, modal / slide-over, no second login).

**Step-by-step integration (routes, token sharing, same-origin vs iframe):** see [`ERP_MODULE_INSIGHTS_INTEGRATION_GUIDE.md`](ERP_MODULE_INSIGHTS_INTEGRATION_GUIDE.md).

## Routes (standalone app)

After signing in to the widget, these routes are available for QA and demos:

| URL (hash router) | Purpose |
|---------------------|---------|
| `/#/module-insights/contact` | Contact / customer-scoped NL2SQL |
| `/#/module-insights/inventory` | Inventory-scoped |
| `/#/module-insights/sales` | Sales-scoped |
| `/#/module-insights/reports` | Report usage insights only (no `/v3/ask`) |

The ERP should navigate or open a modal that loads the same UI with the correct `:erpModule` path.

## Authentication contract

The ERP user is already logged in. Pass through the same credentials the widget uses today:

- **`idcompany`**: gallery / company id (integer).
- **`access_token`**: JWT from the ERP sign-in flow (same as `POST /auth/login` response `session.access_token`).
- **`user_id`** (optional): for server-side memory filtering on `GET /v3/memory/recent` and for tagging rows in `ai_v3_memory_events`.

Every API call must send `access_token` + matching `idcompany` so the backend can enforce [`company_mismatch`](copilot-api/app/main.py) checks.

## Integration options

### A. Angular library (recommended when ERP can add a dependency)

1. Extract `ModuleInsightsPanelComponent` (and its module) into a small Angular library, or publish this repo as an npm package.
2. In the ERP app, import the module and render `<app-module-insights-panel />` inside a **CDK Overlay**, **MatDialog**, or a simple `position: fixed` container.
3. Inject the ERP session service and pass `[idcompany]`, `[accessToken]`, `[userId]` via `@Input()` (requires refactoring the component from route-based to input-based for production embed). The current implementation uses `AuthService` + route param `erpModule`; the ERP can wrap it or we add inputs in a follow-up.

### B. Iframe inside ERP modal (same page)

1. Deploy the built widget (`ng build`) on a known origin (e.g. `https://copilot.example.com`).
2. ERP opens a modal containing `<iframe src="https://copilot.example.com/#/module-insights/contact">`.
3. **PostMessage handshake** (implement in a follow-up): parent sends `{ type: 'copilot-auth', access_token, idcompany, user_id }` after `iframe` `load`; child stores in `sessionStorage` or calls a small bootstrap script. **Restrict** `event.origin` to the ERP and copilot origins only.

### C. Copy source into ERP monorepo

Copy `module-insights-panel.component.*` and extend `CopilotApiService` patterns into the ERP codebase; align Angular version and paths.

## Backend features used

- `POST /v3/ask` with optional `erp_module`, `strict_module_scope`, `user_id` (see [`V3AskRequest`](copilot-api/app/v3/models.py)).
- `GET /v3/memory/recent` for last prompts filtered by `copilot` (+ optional `user_id`).
- `POST /reports/suggestions` for the **Reports** module only.

Environment variables for module scope LLM: see `copilot-api/.env.example` (`V3_MODULE_SCOPE_*`).
