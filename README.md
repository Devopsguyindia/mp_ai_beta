# AI Copilot (V1 - Read-only)

This workspace contains:

- `copilot-api/`: FastAPI service that converts natural language → validated **SELECT-only** SQL (always scoped by `idcompany`) → executes via read-only DB user → returns auditable results.
- `copilot-widget/`: standalone Angular 12 UI for testing the copilot without embedding into the legacy ERP.

