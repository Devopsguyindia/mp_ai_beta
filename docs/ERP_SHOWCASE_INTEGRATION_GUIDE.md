# ERP integration: Artwork showcase (inventory preview)

This guide explains how to open the **Artwork showcase** from your ERP (same patterns as [Module AI Insights](ERP_MODULE_INSIGHTS_INTEGRATION_GUIDE.md)): shared JWT, `copilotSession`, hash routes, and optional iframe `postMessage`.

---

## Isolation from V3 and Module AI Insights (mandatory)

This module is designed so enabling or disabling it does **not** change existing behavior:

| Area | Behavior |
|------|----------|
| **V3** | `/v3/ask`, `/v3/memory/recent`, and the V3 orchestrator are **unchanged**. Showcase does not call NL2SQL or the V3 pipeline. |
| **Module AI Insights** | Routes `/#/module-insights/...` and their API usage are **unchanged**. |
| **API** | Showcase routes live under **`/showcase/*`**. They are registered **only** when `SHOWCASE_ENABLED` is truthy in `copilot-api` env. When off, those paths return **404** and no showcase code is mounted. |
| **Widget** | Route `/#/showcase/inventory` exists in the bundle but is **guarded**: if `showcaseEnabled` is `false` in the built environment, users are redirected to **`/dashboard`** (same session; no V3/insights impact). |

Operational rule: keep **production** builds with `showcaseEnabled: false` until the API flag and ERP deep links are ready; then flip **both** API and SPA flags together.

---

## 1. Session contract (same as insights)

The showcase panel uses **`AuthGuard`** and the same `localStorage` key **`copilotSession`** as the dashboard and module insights.

Required fields:

| Field | Type | Purpose |
|--------|------|--------|
| `access_token` | string | JWT; sent as `access_token` query param on showcase GETs. |
| `idcompany` | number | Tenant id; must match JWT (`company_mismatch` checks). |

Optional: `userid` (for future auditing; not required for current showcase GETs).

Shape matches `POST /auth/login` → `session` (see `copilot-widget-v3/src/app/auth.service.ts`).

---

## 2. Widget route and query parameters

| URL | Purpose |
|-----|---------|
| `/#/showcase/inventory?itemId=<idcompany_item>` | Load pictures for one inventory item from `company_item_pictures`. |

- **`itemId`** must be the numeric **`idcompany_item`** primary key.
- If `itemId` is omitted, the page explains the contract; no API call is made.

Dev example (adjust host/port):

- `http://localhost:4200/#/showcase/inventory?itemId=12345`

---

## 3. API endpoints (`copilot-api`)

All require **`SHOWCASE_ENABLED=1`** (or `true` / `yes`) on the server. Otherwise: **404** `showcase_disabled`.

### `GET /showcase/items/{idcompany_item}/pictures`

Query parameters:

| Param | Required | Description |
|--------|-----------|--------------|
| `idcompany` | Yes | Tenant id. |
| `access_token` | Recommended | JWT; when present, must match `idcompany` in token. |
| `debug` | No | If `true` / `1`, response includes a **`debug`** object (`sql_row_count`, `skips`, `hints`, first-row sample). Set **`SHOWCASE_DEBUG_LOG=1`** on the API to emit the same payload as **`INFO`** logs on every fetch (useful with uvicorn). |

Response (summary):

- `item_title`, `artist_display`, `edition_label`, `item_edition_type` — from `company_item` + `company_item_data` when available.
- `category_label`, `medium_label` — soft hints when ERP text suggests a category/medium (see [SHOWCASE_DATA_CONTRACT.md](SHOWCASE_DATA_CONTRACT.md)).
- `pipeline_version` — matches the loaded **scene library manifest** (render cache grouping).
- `pictures[]` — ordered list with `resolved_url` built from `MP_ASSET_CDN_BASE` + `server_path` + `picture`.

### `GET /showcase/scenes`

Same query params (`idcompany`, optional `access_token`). Returns `pipeline_version` and `scenes[]` from the manifest (`preview_asset_url`, `qa_status`, `tags` when present). Batch QA updates the JSON file or `SHOWCASE_SCENE_MANIFEST_PATH` / `SHOWCASE_SCENE_MANIFEST_JSON`.

### `POST /showcase/options`

JSON body: `idcompany`, optional `access_token`, `idcompany_item`, optional `idcompany_item_pictures` (narrow to one image).

Returns **presentation suggestions**: `recommended_scene_ids`, `frame_style`, `lighting`, `placement`, `suitable_picture_ids`, optional `notes`. Uses **rules** by default; set `SHOWCASE_PRESENTATION_LLM_ENABLED=1` and `OPENAI_API_KEY` for optional LLM refinement (isolated from V3).

### `POST /showcase/render`

JSON body: `idcompany`, optional `access_token`, `idcompany_item`, `idcompany_item_pictures`, `scene_id`, optional `frame_style` / `lighting` / `placement`.

- **Default (`SHOWCASE_COMPOSITOR_ENABLED` off):** `output_mode: pass_through` — `preview_url` is the artwork CDN URL; **`cache_key`** is `sha256(picture_id|scene_id|pipeline_version)` for caching.
- **Compositor on:** `output_mode: composited` — `preview_url` points to **`GET /showcase/render/{cache_key}/preview`** (same auth query params). PNG is generated with Pillow (procedural scene plate or `preview_asset_url` when set). Cache is **in-process LRU** — use one API worker or replace with shared storage later.

### Scene list vs default selection

- **`GET /showcase/scenes`** returns **every** scene in `scene_library_manifest.json` (order as in the file). There is no server-side filtering per item.
- **`POST /showcase/options`** returns **`recommended_scene_ids`** (rules / optional LLM). The widget picks the **first** recommended id that exists in the loaded scene list, else the **first** scene in the manifest.

### `POST /showcase/share`

Stub response: `enabled: false` with a message — customer magic links are a later phase.

### Environment variables

| Variable | Purpose |
|----------|---------|
| `SHOWCASE_ENABLED` | `0` / `1` — gates router registration and endpoints. |
| `SHOWCASE_COMPOSITOR_ENABLED` | `1` enables Pillow compositor + `/showcase/render/{cache_key}/preview` (default off). |
| `MP_ASSET_CDN_BASE` | Base URL for picture assets (default `https://masterpiece.s3.amazonaws.com`). |
| `SHOWCASE_ASSET_HOST_ALLOWLIST` | Optional comma-separated hostnames; if set, `resolved_url` (and thumbnails) must match. |
| `SHOWCASE_PICTURES_MAX_ROWS` | Optional cap per item (default `50`). |
| `SHOWCASE_SCENE_MANIFEST_PATH` / `SHOWCASE_SCENE_MANIFEST_JSON` | Override scene library (defaults to packaged JSON). |
| `SHOWCASE_PRESENTATION_LLM_ENABLED` | `1` to refine `/showcase/options` with OpenAI (optional). |

See `copilot-api/.env.example`. Feature roadmap vs leading apps: [SHOWCASE_PARITY_MATRIX.md](SHOWCASE_PARITY_MATRIX.md).

---

## 4. Integration patterns (A / B)

Use the same approach as **Module AI Insights** ([ERP_MODULE_INSIGHTS_INTEGRATION_GUIDE.md](ERP_MODULE_INSIGHTS_INTEGRATION_GUIDE.md)):

- **Path A — same origin:** Write `copilotSession` to `localStorage`, then navigate to `/#/showcase/inventory?itemId=...`.
- **Path B — iframe:** Embed the widget; after load, `postMessage` with `type: 'copilot-auth'`, `access_token`, `idcompany`, and optionally:

```javascript
redirect_to: '/showcase/inventory?itemId=12345'
```

The widget applies the session and navigates off `/login` using `redirect_to` (see `app.component.ts`).

**CORS:** Allow the ERP/widget origins on `copilot-api` (`CORS_ALLOW_ORIGINS`), same as for `/v3/ask`.

---

## 5. ERP deep link checklist

1. Set **`SHOWCASE_ENABLED=1`** on `copilot-api` and redeploy.
2. Set **`showcaseEnabled: true`** in `environment.prod.ts` (or your build config) and rebuild the SPA.
3. Confirm MySQL has **`company_item_pictures`** with at least: `idcompany_item_pictures`, `idcompany`, `idcompany_item`, `picture`, `server_path` (see [SHOWCASE_DATA_CONTRACT.md](SHOWCASE_DATA_CONTRACT.md)).
4. From ERP inventory, open:  
   `https://<widget-host>/#/showcase/inventory?itemId=<idcompany_item>`
5. Verify `GET /showcase/items/.../pictures` in Network tab returns **200** and URLs load in the browser.

---

## 6. Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| 404 `showcase_disabled` | API flag off or old deploy. |
| Redirect to `/dashboard` | SPA `showcaseEnabled` is false. |
| 401 /403 on API | Missing or mismatched JWT vs `idcompany`. |
| 503 `showcase_pictures_unavailable` | DB error or missing table; check API logs (no SQL echoed to client). |
| Empty `pictures` | No rows for item, or URLs blocked by `SHOWCASE_ASSET_HOST_ALLOWLIST`. |

---

## 7. Data contract reference

Pictures are read **read-only** from **`company_item_pictures`**, joined to **`company_item`** for title and soft-delete on the item. URL rule:

`resolved_url = MP_ASSET_CDN_BASE + server_path + picture` (with slash normalization server-side).

For columns, manifest workflow, and QA URLs, see [SHOWCASE_DATA_CONTRACT.md](SHOWCASE_DATA_CONTRACT.md). Do not treat this guide as a substitute for DBA-approved schema documentation.
