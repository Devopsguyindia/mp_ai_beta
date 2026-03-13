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

3) Run

```bash
uvicorn app.main:app --reload --port 8001
```

## Endpoints

- `GET /health`
- `POST /chat`

`POST /chat` supports `debug=true` to return model metadata + SQL + guardrail report + result rows.
