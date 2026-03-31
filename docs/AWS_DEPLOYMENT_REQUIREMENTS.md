# MP AI Copilot – AWS Deployment Requirements

**Document for Cloud Team**  
**Version:** 1.0  
**Last Updated:** March 2025

---

## 1. Application Overview

The MP AI Copilot is a two-tier application:

- **Backend API**: Python FastAPI service that converts natural language to SQL, executes queries against MySQL, and uses OpenAI for NL2SQL and insights.
- **Frontend**: Angular SPA that provides the copilot dashboard UI and communicates with the backend API.

Users authenticate via an external ERP API; the copilot API proxies login and uses JWT tokens for tenant scoping.

---

## 2. Technology Stack

### 2.1 Backend (copilot-api)

| Component | Version / Requirement |
|-----------|------------------------|
| **Runtime** | Python 3.11 or higher |
| **Web framework** | FastAPI 0.115+ |
| **ASGI server** | Uvicorn 0.30+ (standard) |
| **Database driver** | mysql-connector-python 9.0+ |
| **Other** | pydantic 2.7+, sqlglot 25.0+, python-dotenv 1.0+, openai 1.52+ |

**Default port:** 8001

### 2.2 Frontend (copilot-widget-v3)

| Component | Version / Requirement |
|-----------|------------------------|
| **Framework** | Angular 12.x |
| **Build tool** | Angular CLI 12.x |
| **Node.js** | 12.x or 14.x (for build) |
| **Package manager** | npm 6.x or 7.x |

**Build output:** Static files in `dist/copilot-widget/` (HTML, JS, CSS). Production deployment serves these as static assets (e.g. S3 + CloudFront, or static hosting).

---

## 3. Infrastructure Requirements

### 3.1 Compute

- **Backend:** Requires a process that runs `uvicorn app.main:app --host 0.0.0.0 --port 8001`.
- **Suggested:** EC2, ECS/Fargate, or App Runner.
- **Resources:** 512 MB RAM minimum; 1 vCPU recommended for concurrent LLM calls.

### 3.2 Database

- **Engine:** MySQL 5.7+ or MariaDB 10.3+ (compatible with mysql-connector-python).
- **Suggested:** Amazon RDS for MySQL or Aurora MySQL.
- **Access:** Read-only user strongly recommended for security.
- **Network:** Backend must have network access to the database (same VPC or peered).
- **Schema:** Application expects `mpm_pos` (or equivalent) database with tables such as `company_sale_data`, `company_item_data`, `company_contact`, etc.

### 3.3 External Dependencies

| Service | Purpose | Protocol |
|---------|---------|----------|
| **OpenAI API** | NL2SQL, insights, routing | HTTPS (api.openai.com) |
| **ERP Auth API** | User login / JWT | HTTPS (v12-api.masterpiecemanager.com) |

Outbound HTTPS access to these endpoints is required from the backend.

---

## 4. Environment Variables

### 4.1 Backend (copilot-api)

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `MYSQL_HOST` | Yes | MySQL hostname | `your-rds-endpoint.region.rds.amazonaws.com` |
| `MYSQL_PORT` | No | MySQL port (default: 3306) | `3306` |
| `MYSQL_DATABASE` | Yes | Database name | `mpm_pos` |
| `MYSQL_USERNAME` | Yes | DB username (read-only recommended) | `copilot_readonly` |
| `MYSQL_PASSWORD` | Yes | DB password | *(from Secrets Manager)* |
| `OPENAI_API_KEY` | Yes* | OpenAI API key | `sk-...` |
| `CORS_ALLOW_ORIGINS` | Yes | Allowed frontend origins (comma-separated) | `https://copilot.example.com` |
| `MYSQL_QUERY_TIMEOUT_MS` | No | Query timeout (default: 8000) | `8000` |
| `MYSQL_MAX_ROWS` | No | Max rows per query (default: 200) | `200` |
| `OPENAI_MODEL_SQL` | No | OpenAI model for SQL (default: gpt-4.1) | `gpt-4.1` |
| `OPENAI_MODEL_ROUTER` | No | OpenAI model for routing | `gpt-4.1-mini` |
| `OPENAI_MODEL_INSIGHT` | No | OpenAI model for insights (falls back to SQL model) | `gpt-4.1` |
| `V3_ASK_ENABLED` | No | Enable V3 ask endpoint (default: 1) | `1` |
| `V3_CHART_AGENT_ENABLED` | No | Enable chart generation (default: 0) | `1` |
| `V3_INSIGHT_LLM_ENABLED` | No | Enable LLM insights (default: 1) | `1` |
| `V3_VALIDATOR_MAX_RETRIES` | No | SQL validation retries (default: 1) | `1` |
| `V3_MIN_CONFIDENCE` | No | Min planner confidence (default: 0.55) | `0.55` |
| `V3_BLOCK_LOW_CONFIDENCE` | No | Block low-confidence (default: 0) | `0` |
| `V3_MEMORY_USE_MYSQL` | No | Use MySQL for memory (default: 1) | `1` |
| `V3_MEMORY_TABLE_NAME` | No | Memory table name | `ai_v3_memory_events` |
| `V3_MEMORY_PGVECTOR_ENABLED` | No | Use pgvector (default: 0) | `0` |
| `V3_MEMORY_LOG_PATH` | No | File-based memory path | *(empty)* |
| `COPILOT_ENV` | No | Environment label | `prod` |
| `REPORT_SUGGESTIONS_ENABLED` | No | Enable `POST /reports/suggestions` (default: `1`) | `1` |
| `REPORT_RERUN_ENABLED` | No | Enable `POST /reports/rerun` (Masterpiece report proxy) (default: `1`) | `1` |
| `MP_REPORT_GENERATE_URL` | No | Base URL for Masterpiece `generateReport` (must be reachable from backend) | `https://v12-api.masterpiecemanager.com/...` |
| `MP_REPORT_AUTH_BEARER` | No | If `1`/`true`/`yes`, send `Authorization: Bearer <token>`; otherwise raw token | `0` |
| `MP_REPORT_GENERATE_TIMEOUT_SEC` | No | HTTP timeout for report proxy GET (default: `120`) | `120` |

\* Without `OPENAI_API_KEY`, some features (e.g. LLM insights) are disabled.

**Report usage insights:** The read-only MySQL user must be able to `SELECT` from report analytics tables used by the suggestions service (see `schema_registry.json` / `metric_definitions.md` for table names). The report re-run proxy calls the ERP/Masterpiece API using the same sign-in token the client sends; ensure outbound HTTPS to `MP_REPORT_GENERATE_URL` is allowed from the backend.

The Angular dashboard summarizes `filter_data` for end users without showing internal IDs (`report_id`, `*AutoID`, keys ending in `_id`) or opaque numeric enums such as `dd_mailingSign` when the value is digits-only. **Top reports** ranks by total usage (SQL aggregates `report_usage`); **Patterns** shows weekday clustering for the single most-used report. **Smart defaults → Re-run** refreshes end-date fields in the stored filter JSON to **today** in `MM/DD/YYYY` form while leaving from/start dates unchanged (ERP must accept that format in `generateReport` query strings).

### 4.2 Frontend (build-time)

The frontend needs the API base URL at build time. Update `copilot-widget-v3/src/environments/environment.prod.ts`:

```typescript
export const environment = {
  production: true,
  copilotApiBaseUrl: 'https://api.your-domain.com',  // Backend API URL
  v3AskEnabled: true
};
```

---

## 5. Network and Security

### 5.1 Ports

| Service | Port | Notes |
|---------|------|-------|
| Backend API | 8001 | HTTP/HTTPS (via ALB) |
| Frontend | 80/443 | Served by S3+CloudFront or similar |

### 5.2 Outbound Access (Backend)

- **OpenAI:** `api.openai.com` (HTTPS)
- **ERP Auth:** `v12-api.masterpiecemanager.com` (HTTPS)
- **MySQL:** RDS endpoint (port 3306)

### 5.3 Inbound Access

- Backend: ALB or API Gateway on 443 (HTTPS).
- Frontend: CloudFront or similar on 80/443.

### 5.4 CORS

Configure `CORS_ALLOW_ORIGINS` with the production frontend URL(s), e.g.:

```
CORS_ALLOW_ORIGINS=https://copilot.example.com,https://www.example.com
```

The app also merges `https://doy5f9mehzv49.cloudfront.net` in `app/main.py` so EC2 does not need a separate CORS line for that origin.

### 5.5 HTTPS required when the SPA uses HTTPS (mixed content)

If the Angular app is loaded from **HTTPS** (e.g. CloudFront), the browser **blocks** calls to **`http://` API URLs** (e.g. `http://54.177.67.222:8001`). This is **not** a CORS misconfiguration: the request is blocked before it reaches the server (DevTools may show “Provisional headers” and no response headers).

**Fix:** Terminate **TLS** for the API and set `copilotApiBaseUrl` in `environment.prod.ts` to **`https://...`** (for example: **Nginx + Let’s Encrypt** on EC2 with a DNS name pointing to the instance, or an **ALB** with an **ACM** certificate).

---

## 6. Suggested AWS Architecture

```
                    ┌─────────────────┐
                    │   Route 53       │
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
              ▼                             ▼
    ┌─────────────────┐           ┌─────────────────┐
    │   CloudFront    │           │   CloudFront     │
    │   (Frontend)    │           │   (API - opt.)   │
    └────────┬────────┘           └────────┬────────┘
             │                             │
             ▼                             ▼
    ┌─────────────────┐           ┌─────────────────┐
    │   S3 Bucket     │           │   ALB            │
    │   (Static)      │           │   (Backend)      │
    └─────────────────┘           └────────┬────────┘
                                           │
                              ┌────────────┴────────────┐
                              │   ECS / EC2              │
                              │   (copilot-api)          │
                              └────────────┬────────────┘
                                           │
                              ┌────────────┴────────────┐
                              │                        │
                              ▼                        ▼
                    ┌─────────────────┐      ┌─────────────────┐
                    │   RDS MySQL     │      │  OpenAI / ERP   │
                    │   (Aurora opt.) │      │  (External)     │
                    └─────────────────┘      └─────────────────┘
```

---

## 7. Deployment Steps (High Level)

### 7.1 Backend

1. Create Python 3.11 runtime environment (EC2, ECS, or App Runner).
2. Install dependencies: `pip install -e .` (from `copilot-api/`).
3. Set environment variables (from `.env` or AWS Secrets Manager/Parameter Store).
4. Run: `uvicorn app.main:app --host 0.0.0.0 --port 8001`.
5. Place behind ALB with HTTPS termination.

### 7.2 Frontend

1. Set `copilotApiBaseUrl` in `environment.prod.ts` to the backend API URL.
2. Build: `npm run build` (produces `dist/copilot-widget/`).
3. Upload contents of `dist/copilot-widget/` to S3 bucket.
4. Configure CloudFront distribution with S3 origin.
5. Configure error pages (e.g. 404 → index.html) for SPA routing.

### 7.3 Database

1. Ensure MySQL/RDS is in the same VPC (or reachable via VPC peering).
2. Create a database user with access to required tables. Read-only is sufficient for NL2SQL and report suggestions; **INSERT** is required for `ai_v3_memory_events` (V3 memory) and `ai_v3_copilot_auth_audit` (auth audit), or use a separate user / extra `GRANT` for those tables only.
3. Create `ai_v3_memory_events` table if `V3_MEMORY_USE_MYSQL=1`. Example schema:

```sql
CREATE TABLE ai_v3_memory_events (
  request_id VARCHAR(64) PRIMARY KEY,
  idcompany INT NOT NULL,
  user_id VARCHAR(64),
  copilot VARCHAR(32),
  intent VARCHAR(128),
  question TEXT,
  sql_text TEXT,
  rows_returned INT DEFAULT 0,
  meta_json JSON,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FULLTEXT KEY ft_question_sql (question, sql_text)
);
```

4. Create `ai_v3_copilot_auth_audit` if `COPILOT_AUTH_AUDIT_USE_MYSQL=1` (login / logout audit). The app user needs **INSERT** on this table. Example schema:

```sql
CREATE TABLE ai_v3_copilot_auth_audit (
  id BIGINT NOT NULL AUTO_INCREMENT,
  event_type VARCHAR(32) NOT NULL COMMENT 'login_success | login_failure | logout',
  occurred_at_utc DATETIME(6) NOT NULL,
  auth_session_id VARCHAR(36) NULL COMMENT 'UUID; correlates login_success with logout',
  idcompany INT NULL,
  txt_company VARCHAR(200) NULL COMMENT 'gallery code from login form when known',
  userid VARCHAR(64) NULL,
  username VARCHAR(200) NULL,
  failure_code VARCHAR(64) NULL,
  failure_message VARCHAR(512) NULL,
  client_ip VARCHAR(45) NULL,
  user_agent VARCHAR(512) NULL,
  role_id VARCHAR(64) NULL,
  meta_json JSON NULL,
  PRIMARY KEY (id),
  KEY idx_occurred (occurred_at_utc),
  KEY idx_company_time (idcompany, occurred_at_utc),
  KEY idx_auth_session (auth_session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

## 8. Secrets Management

- Store `MYSQL_PASSWORD` and `OPENAI_API_KEY` in AWS Secrets Manager or Parameter Store (SecureString).
- Inject into the backend at runtime (e.g. via ECS task definition, Lambda env, or startup script).

---

## 9. Health Check

- **Endpoint:** `GET /health`
- **Expected response:** `{"status": "ok"}`
- Use for ALB health checks and monitoring.

---

## 10. API Endpoints Summary

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Health check |
| POST | `/auth/login` | Proxy login to ERP; returns JWT session + `auth_session_id` for audit |
| POST | `/auth/logout` | Records logout in `ai_v3_copilot_auth_audit` (best-effort); body includes `auth_session_id` |
| POST | `/chat` | Legacy chat (V1/V2) |
| POST | `/v3/ask` | V3 ask (primary copilot endpoint) |
| POST | `/reports/suggestions` | Report usage suggestions (LLM + read-only MySQL on report tables); requires `Authorization` |
| POST | `/reports/rerun` | Proxy GET to Masterpiece `generateReport` with filter JSON; requires `Authorization` |

---

## 11. Optional: ERP Auth URL

The auth endpoint is currently hardcoded: `https://v12-api.masterpiecemanager.com/signIn`. If a different ERP URL is needed for staging/production, the codebase would need an environment variable (e.g. `ERP_AUTH_URL`) and a small code change. Contact the development team if this is required.

---

## 12. Metric Definitions (Reference)

Canonical definitions for Revenue, TotalSales, Margin, Markup, and Returns are maintained in:

- **Schema registry (agents):** `copilot-api/prompt_coverage/schema_registry.json` → `metric_definitions`
- **Human docs:** `copilot-api/prompt_coverage/metric_definitions.md`

These ensure agents and UI use consistent formulas. Do not edit without updating both.

---

## 13. Contact

For questions about schema, prompts, or application logic, contact the development team. For infrastructure and deployment, use this document with the cloud team.
