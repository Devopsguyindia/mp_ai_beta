# Follow-up Prompts Verification Guide

## Where to Check

### 1. Dashboard UI (Primary)

1. Open the copilot dashboard: **http://localhost:4300** (or your configured port)
2. Log in with valid credentials
3. In the **right sidebar**, find the section **"Suggested prompts (auto copilot)"**
4. **Before** running a query: you see 5 static prompts (e.g. "recent 10 sold items", "inventory count and qoh summary for this month", etc.)
5. **After** running a query that returns data: the section shows **3 related prompts** generated from the Follow-up insight (if the LLM includes one)
6. Click any suggested prompt to populate the input and run it

### 2. API Response (Debug)

Call `POST /v3/ask` and inspect the JSON response for `follow_up_prompts`:

```json
{
  "answer": "...",
  "data": [...],
  "insights": [
    {"title": "Interpretation", "detail": "..."},
    {"title": "Follow-up", "detail": "Consider asking: ..."}
  ],
  "follow_up_prompts": [
    "Which artists contributed most to high-margin sales?",
    "Show sales with margins below 20% this year",
    "Break down top margin sales by customer"
  ],
  ...
}
```

---

## Test Data and Expected Output

Use these prompts in the dashboard (or via API) with a valid `idcompany` (e.g. 212):

| # | Test Prompt | Expected Behavior |
|---|-------------|-------------------|
| 1 | `top 10 highest margin sales this year` | Returns data + insights + 3 `follow_up_prompts` (e.g. artist breakdown, low-margin sales, customer breakdown) |
| 2 | `recent 10 sold items` | Returns data + insights + 3 `follow_up_prompts` (e.g. total value, artists, missing info) |
| 3 | `inventory count and qoh summary for this month` | Returns data + insights + 3 `follow_up_prompts` (e.g. inventory added, value by artist, highest QOH) |

**Sample expected `follow_up_prompts`** (actual text may vary slightly due to LLM):

- For "top 10 highest margin sales this year":
  - `Which artists contributed most to high-margin sales?`
  - `Show sales with margins below 20% this year`
  - `Break down top margin sales by customer`

- For "recent 10 sold items":
  - `Show total sales value for these 10 items`
  - `Which artists had the most recent sales?`
  - `List recent sales with missing artist or vendor info`

---

## Automated Verification

Run the verification script (requires backend on port 8001):

```bash
cd "d:\My Projects\MP\V12\mp_ai_beta"
python copilot-api/tests/verify_follow_up_prompts.py
```

Set `VERIFY_IDCOMPANY` in `.env` or environment if needed (default: 212).

---

## Backend Restart

**Yes, a backend restart is required** after changes to:

- `copilot-api/app/v3/agents/insight_agent.py`
- `copilot-api/app/v3/models.py`
- `copilot-api/app/v3/orchestrator.py`
- `copilot-api/app/v3/prompts/insight.md`

If running with `--reload`, uvicorn will auto-reload on file changes. Otherwise restart manually:

```bash
cd copilot-api
uvicorn app.main:app --reload --port 8001
```
