## Run locally

Prereqs: Python 3.11+

1) Create env

- Copy `.env.example` → `.env` and set MySQL read-only credentials.

2) Install

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -U pip
pip install -e .
```

For **Artwork showcase** compositor + optional **cutout** (rembg + ONNX runtime on CPU):

```bash
pip install -e ".[showcase]"
```

Then set `SHOWCASE_ENABLED=1`, `SHOWCASE_COMPOSITOR_ENABLED=1`, and optionally `SHOWCASE_CUTOUT_ENABLED=1` in `.env`.

3) Run

```bash
uvicorn app.main:app --reload --port 8001
```

## Production notes

**CORS:** Browsers send an `Origin` header on `fetch`/XHR. `copilot-api` only reflects that origin in `Access-Control-Allow-Origin` when it appears in `CORS_ALLOW_ORIGINS` (and optional `CORS_EXTRA_ORIGINS`). After deploy, if the widget moved to a new CloudFront URL or the env file no longer sets these variables, the console will show CORS errors. Fix: set `CORS_ALLOW_ORIGINS` to every HTTPS origin that loads the Angular app (comma-separated, no trailing slashes). Restart the API and check logs: you should see `CORS: allowing N origin(s)`; if you see a warning about no `https://` origin, the variable is still wrong or empty on the server.

**Mixed content:** The SPA must use `copilotApiBaseUrl` with `https://` if the page is served over HTTPS.

## Endpoints

- `GET /health`
- `POST /chat`

`POST /chat` supports `debug=true` to return model metadata + SQL + guardrail report + result rows.
