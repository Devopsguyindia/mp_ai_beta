# Step-by-step: ERP Module AI Insights integration

This guide explains how to open **Contact / Inventory / Sales / Reports** AI Insights (`module-insights/:erpModule`) from your **existing ERP UI**, and how to **share the JWT** so users do not log in twice.

The standalone widget uses a **hash router**. Example dev URLs (replace host/port with your deployment):

- `http://localhost:4200/#/module-insights/contact` (or the port in `copilot-widget-v3/angular.json`, e.g. `4300`)
- `http://localhost:4200/#/module-insights/inventory`
- `http://localhost:4200/#/module-insights/sales`
- `http://localhost:4200/#/module-insights/reports`

---

## 1. What the widget expects (session contract)

The insights screens use the same session as the main dashboard. `AuthService` persists a JSON object in **`localStorage`** under the key **`copilotSession`**.

Required fields for `AuthGuard` and API calls:

| Field | Type | Purpose |
|--------|------|--------|
| `access_token` | string | JWT; sent to `copilot-api` on every request (e.g. `POST /v3/ask`, `GET /v3/memory/recent`). |
| `idcompany` | number | Tenant id; must match JWT / backend `company_mismatch` checks. |

Optional but recommended:

| Field | Type | Purpose |
|--------|------|--------|
| `userid` | string | User id; used when the API accepts `user_id` (memory, auditing). |

Shape matches the `POST /auth/login` response `session` object (see `AuthService` / `SessionInfo` in `copilot-widget-v3/src/app/auth.service.ts`).

**Rule:** Whatever token your ERP already uses for **Copilot API** calls should be the same **`access_token`** stored here. Do not invent a second login; reuse the ERP session.

---

## 2. Choose an integration pattern

| Pattern | Same browser origin as widget? | Token sharing approach |
|--------|--------------------------------|-------------------------|
| **A. Reverse proxy / path on ERP host** | Yes (e.g. `https://erp.example.com/ai-copilot/`) | ERP writes `localStorage['copilotSession']` before navigation, or a tiny bootstrap page does. |
| **B. Iframe (widget on another subdomain)** | No | Parent **postMessages** JWT + `idcompany` to the child; child must **listen** and call the same session shape (see note below). |
| **C. Angular library** | N/A (in-process) | Inject ERP session into inputs/services; refactor panel to accept `@Input()` if you extract a library. |

**Important:** `localStorage` is **per origin** (scheme + host + port). The ERP at `https://erp.app` cannot read storage for `https://copilot.app`. For **cross-origin** embedding you must pass the token explicitly (typically **postMessage** with strict origin checks), not rely on shared storage.

---

## 3. Path A — Same origin (recommended first step)

Goal: users open the widget under the **same hostname** as the ERP (different path is fine), e.g. `https://erp.example.com/copilot/#/module-insights/contact`.

### Step A1 — Build and host the widget

1. In `copilot-widget-v3`, run `ng build` with the correct `environment.prod.ts` (`copilotApiBaseUrl` pointing at your deployed API).
2. Deploy the `dist/` output behind your web server or CDN **on the ERP origin** (or behind a reverse proxy that preserves the same host).

### Step A2 — Align API URL

1. Set `copilotApiBaseUrl` in the built environment to your real API (e.g. `https://api.example.com`).
2. Ensure **CORS** on `copilot-api` allows the ERP origin (see `AWS_DEPLOYMENT_REQUIREMENTS.md` / CORS config).

### Step A3 — Write the session before opening insights

When the ERP user is already authenticated **and** you have the same JWT + `idcompany` the API expects:

1. Serialize a `SessionInfo`-compatible object (at minimum `access_token`, `idcompany`; include `userid` if available).
2. Run in the **same origin** as the loaded widget app:

```javascript
localStorage.setItem('copilotSession', JSON.stringify({
  access_token: '<JWT from ERP session>',
  idcompany: 12345,
  userid: '<optional user id string>'
}));
```

3. Navigate the user (or set `iframe src`) to the hash route, for example:
   - `.../#/module-insights/contact`
   - `.../#/module-insights/inventory`
   - `.../#/module-insights/sales`
   - `.../#/module-insights/reports`

### Step A4 — Wire ERP buttons / menus

Map ERP areas to routes:

| ERP area | Widget route |
|----------|----------------|
| Contacts / CRM | `/#/module-insights/contact` |
| Inventory | `/#/module-insights/inventory` |
| Sales | `/#/module-insights/sales` |
| Reporting | `/#/module-insights/reports` |

Use your framework’s router or `window.location.assign` / `window.open` to the full URL including hash.

### Step A5 — Verify

1. Open DevTools → Application → Local Storage: confirm `copilotSession` exists on the widget origin.
2. Load `/#/module-insights/contact` — you should **not** be redirected to `/#/login`.
3. Ask a question; confirm `POST` to `copilot-api` includes `access_token` and correct `idcompany`.

---

## 4. Path B — Iframe on a different origin

Use when the widget is hosted at e.g. `https://copilot.example.com` and the ERP at `https://erp.example.com`.

### Step B1 — Deploy widget and configure CORS

Same as Path A for build and API base URL. CORS must allow the **ERP** origin for API calls from the iframe.

### Step B2 — Parent (ERP) responsibilities

1. Embed: `<iframe id="insights" src="https://copilot.example.com/#/module-insights/contact"></iframe>`.
2. After the iframe **loads**, send the session from the parent (only if your ERP page holds the JWT):

```javascript
const iframe = document.getElementById('insights');
iframe.addEventListener('load', () => {
  iframe.contentWindow.postMessage(
    {
      type: 'copilot-auth',
      access_token: '<JWT>',
      idcompany: 12345,
      user_id: '<optional>',
      redirect_to: '/module-insights/contact' // optional: route after auth if iframe landed on /login
    },
    'https://copilot.example.com'  // exact child origin
  );
});
```

3. **Never** send tokens to `*`; always target the widget origin.

### Step B3 — Child (widget) responsibilities

The widget registers a **`window` `message` listener** only when **`parentOriginsAllowlist`** is non-empty in [`copilot-widget-v3/src/environments/environment.ts`](copilot-widget-v3/src/environments/environment.ts) (and `environment.prod.ts` for production builds).

1. **Enable the listener:** Set `parentOriginsAllowlist` in `environment.ts` / `environment.prod.ts` to the **exact ERP page origins** that may embed the iframe (scheme + host + port, no trailing slash). This must be the **parent** page’s origin (the URL in the browser address bar on the ERP app), **not** the CloudFront/widget URL. To confirm: on the ERP page, run `window.location.origin` in DevTools.  
   If the array is **empty**, **no listener is registered** — `postMessage` is ignored and users see login again.

2. **Validation:** For each message, the app checks `event.origin` is in that allowlist, then requires `data.type === 'copilot-auth'`, `access_token`, and `idcompany`. It then writes the same `copilotSession` shape as login via `AuthService.applyEmbeddedSession` (JWT payload is decoded client-side for `token_payload` / display fields when possible).

3. **Optional `redirect_to`:** If the iframe first loads a guarded route and Angular sends the user to `/#/login` before `postMessage` runs, pass `redirect_to` (Angular path, e.g. `/module-insights/contact`). After a successful handoff, the app navigates there instead of staying on login. If omitted while on login, navigation falls back to `/dashboard`.

4. **Same-tab redirect / wrapper page:** Still valid alternatives if you prefer not to use the built-in listener.

Document the chosen allowlist and ERP release notes in your deployment.

### Step B4 — Security checklist (iframe)

- The widget validates **`event.origin`** against **`parentOriginsAllowlist`** (deny by default when the allowlist is empty).
- Prefer **short-lived** tokens if your IdP allows scoped tokens for Copilot only.
- Use **HTTPS** everywhere.

---

## 5. Path C — Angular library (longer term)

1. Extract `ModuleInsightsPanelComponent` and dependencies into a library (or consume this repo as a package).
2. Pass `access_token`, `idcompany`, and `user_id` from the ERP `AuthService` via `@Input()` or a shared token service (requires refactoring off route-only session for some flows).
3. Keep the **same** backend contract as `POST /v3/ask` (see `ERP_AI_INSIGHTS_EMBED.md`).

---

## 6. Backend alignment

- All calls: **`access_token`** + **`idcompany`** consistent with `POST /auth/login`.
- Module insights also send `erp_module` and `strict_module_scope` from the panel; no change required on the ERP for token shape.
- Reports tab uses **`POST /reports/suggestions`** (and related endpoints) — same JWT.

---

## 7. Quick troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| Redirect to `/#/login` | Missing or invalid `copilotSession` on **this** origin. |
| `401` / `403` from API | Wrong or expired JWT; `idcompany` mismatch with token. |
| CORS errors | API `Access-Control-Allow-Origin` does not include ERP or widget origin. |
| Blank iframe | Wrong `src` hash path; check `#/module-insights/...` spelling. |
| Iframe always shows login (Path B) | `parentOriginsAllowlist` empty or missing your **ERP** origin; listener not registered or `postMessage` origin rejected. |

---

## 8. Related docs

- [`ERP_AI_INSIGHTS_EMBED.md`](ERP_AI_INSIGHTS_EMBED.md) — API fields, `erp_module`, memory.
- [`PHASE1_QA_CHECKLIST.md`](PHASE1_QA_CHECKLIST.md) — manual QA including ERP integration bullets.

---

## Summary

1. **Reuse the same JWT** your ERP (or Copilot login) already uses for **`copilot-api`**.
2. Store it as **`localStorage['copilotSession']`** on the **widget’s origin**, with **`access_token`** + **`idcompany`** (and **`userid`** when available).
3. Navigate to **`/#/module-insights/{contact|inventory|sales|reports}`**.
4. For **cross-origin** iframes, **postMessage** from ERP → widget (plus a small listener or wrapper page), with strict origins — **not** shared `localStorage` across domains.
