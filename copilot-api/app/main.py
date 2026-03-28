from __future__ import annotations

import os
import re
import time
import uuid
import base64
import json
from urllib import request as urlrequest, parse as urlparse, error as urlerror
from datetime import datetime, timezone
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .llm_nl2sql import generate_query_with_llm
from .nl2sql_engine import generate_query
from .v3.rag.schema_index import build_schema_from_registry
from .sql_guardrails import GuardrailResult, validate_select_sql
from .sql_runner import QueryResult, run_select_query
from .v3.models import DbConnectionStatus, V3AskRequest, V3AskResponse
from .v3.orchestrator import run_v3_ask
from .report_suggestions import router as report_suggestions_router


load_dotenv()

app = FastAPI(title="Copilot API (V1, read-only)", version="0.1.0")

cors_origins_raw = os.getenv(
    "CORS_ALLOW_ORIGINS",
    "http://localhost:4200,http://127.0.0.1:4200,http://localhost:4300,http://127.0.0.1:4300,https://doy5f9mehzv49.cloudfront.net",
)
def _normalize_origin(o: str) -> str:
    o = o.strip()
    if len(o) > 1 and o.endswith("/"):
        return o[:-1]
    return o


cors_allow_origins = [_normalize_origin(o) for o in cors_origins_raw.split(",") if o.strip()]
# Keep local dev origins for both V2 (4200) and V3 (4300) even if env omits them.
for local_origin in (
    "http://localhost:4200",
    "http://127.0.0.1:4200",
    "http://localhost:4300",
    "http://127.0.0.1:4300",
):
    if local_origin not in cors_allow_origins:
        cors_allow_origins.append(local_origin)

# Production SPA (S3 + CloudFront): merged in code so git pull on EC2 does not require a
# separate server-only CORS_ALLOW_ORIGINS line. Override list still applies first via env above.
_CLOUDFRONT_SPA_ORIGIN = "https://doy5f9mehzv49.cloudfront.net"
if _CLOUDFRONT_SPA_ORIGIN not in cors_allow_origins:
    cors_allow_origins.append(_CLOUDFRONT_SPA_ORIGIN)

# Browsers send Origin on cross-origin XHR. Match:
# - localhost / 127.0.0.1 (any port)
# - any host under https://*.mpstest.net (including apex https://mpstest.net)
# - any https://*.cloudfront.net (S3/CloudFront SPA distributions vary by ID)
# Override entirely with CORS_ALLOW_ORIGIN_REGEX if you need a custom pattern on the server.
_DEFAULT_CORS_ORIGIN_REGEX = (
    r"(^https?://(localhost|127\.0\.0\.1)(:\d+)?$)|"
    r"(^https://(?:[^/]+\.)?mpstest\.net(?::\d+)?$)|"
    r"(^https://[^/]+\.cloudfront\.net(?::\d+)?$)"
)
_cors_origin_regex = os.getenv("CORS_ALLOW_ORIGIN_REGEX", _DEFAULT_CORS_ORIGIN_REGEX).strip() or _DEFAULT_CORS_ORIGIN_REGEX

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allow_origins,
    allow_origin_regex=_cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(report_suggestions_router)


class ChatRequest(BaseModel):
    idcompany: int = Field(..., ge=1, description="Tenant/company ID (gallery)")
    access_token: str | None = Field(
        default=None,
        description="JWT from ERP login. If provided, company id is derived from token.",
    )
    question: str = Field(..., min_length=1, max_length=4000)
    copilot: Literal["sales", "inventory", "customer", "artist", "vendor"] | None = Field(
        default=None,
        description="Optional copilot selector. Backward compatible when omitted.",
    )
    debug: bool = Field(False, description="If true, include SQL and validation details")


class LoginRequest(BaseModel):
    txt_company: str = Field(..., min_length=1, max_length=200)
    txt_username: str = Field(..., min_length=1, max_length=200)
    txt_password: str = Field(..., min_length=1, max_length=200)


class DebugInfo(BaseModel):
    request_id: str | None = None
    server_ts_utc: str | None = None
    input_question: str | None = None
    matched_intent: str | None = None
    router_model: str | None = None
    sql_model: str | None = None
    generated_sql: str | None = None
    rendered_sql_preview: str | None = None
    parameters: dict[str, Any] | None = None
    guardrails: GuardrailResult | None = None
    elapsed_ms: int | None = None
    rows_returned: int | None = None
    requested_limit: int | None = None
    applied_limit: int | None = None
    window_label: str | None = None
    generation_path: str | None = None
    generation_error: str | None = None
    retry_attempted: bool | None = None
    retry_success: bool | None = None
    resolved_idcompany: int | None = None
    selected_copilot: str | None = None
    routed_intent: str | None = None
    contract_guardrails: dict[str, Any] | None = None


class ChatResponse(BaseModel):
    answer: str
    data: list[dict[str, Any]] | None = None
    debug: DebugInfo | None = None
    row_limit_notice: str | None = None
    db_status: DbConnectionStatus | None = None


def _decode_jwt_payload_unverified(token: str) -> dict[str, Any]:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8")
        data = json.loads(decoded)
        if isinstance(data, dict):
            return data
        return {}
    except Exception:
        return {}


def _resolve_idcompany_from_request(*, req_idcompany: int, access_token: str | None) -> int:
    if not access_token:
        return req_idcompany
    token_payload = _decode_jwt_payload_unverified(access_token)
    token_company = token_payload.get("company_id") or token_payload.get("idcompany")
    try:
        token_company_int = int(token_company)
    except Exception:
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_token", "message": "Could not resolve company_id from JWT token."},
        )
    if token_company_int != req_idcompany:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "company_mismatch",
                "message": "Request idcompany does not match JWT company_id.",
                "token_company_id": token_company_int,
                "request_idcompany": req_idcompany,
            },
        )
    return token_company_int


def _to_sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    # basic display escaping for debug preview only
    s = str(value).replace("'", "''")
    return f"'{s}'"


def _render_sql_preview(sql: str, params: dict[str, Any]) -> str:
    """
    Build a best-effort SQL preview with placeholders replaced by values.
    This is only for observability/debugging; execution remains parameterized.
    """
    rendered = sql
    for key, value in params.items():
        pattern = re.compile(rf"%\({re.escape(key)}\)s")
        rendered = pattern.sub(_to_sql_literal(value), rendered)
    return rendered


def _extract_sql_relations(sql: str) -> set[str]:
    matches = re.findall(r"(?is)\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)", sql)
    return {m.lower() for m in matches}


def _infer_routed_intent_from_question(question: str) -> str:
    q = question.lower()
    # Direct routing for simple inventory edition-count asks (e.g., "count of limited items").
    has_count = any(t in q for t in ["count", "how many", "total"])
    has_item = any(t in q for t in ["item", "items"])
    has_edition_signal = any(t in q for t in ["limited", "open", "unique", "edition"])
    if has_count and has_item and has_edition_signal:
        return "inventory_total_stock"

    intent_signals: list[tuple[str, list[str]]] = [
        ("sales_layaway_outstanding", ["layaway", "receivable", "overdue", "due", "installment"]),
        ("inventory_total_stock", ["inventory", "stock", "qoh", "on hand", "unsold", "item", "items", "edition", "limited", "open", "unique"]),
        ("customer_top_by_ltv", ["customer", "customers", "buyer", "buyers", "collector", "ltv", "followup", "inactive"]),
        ("artist_sales_performance", ["artist", "artists", "commission", "sell through"]),
        ("vendor_outstanding_payables", ["vendor", "vendors", "supplier", "suppliers", "payable", "invoice", "spend"]),
        ("sales_count_and_revenue", ["sale", "sales", "sold", "revenue", "quote", "approval", "return"]),
    ]
    best_intent = "sales_count_and_revenue"
    best_score = 0
    for intent, signals in intent_signals:
        score = sum(1 for token in signals if token in q)
        if score > best_score:
            best_score = score
            best_intent = intent
    return best_intent


def _copilot_from_intent(intent: str) -> str:
    i = intent.strip().lower()
    if i.startswith("inventory_"):
        return "inventory"
    if i.startswith("customer_"):
        return "customer"
    if i.startswith("artist_"):
        return "artist"
    if i.startswith("vendor_"):
        return "vendor"
    return "sales"


def _load_runtime_contracts() -> dict[str, list[dict[str, Any]]]:
    contract_file = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "prompt_coverage",
        "prompt_to_sql_contracts.json",
    )
    try:
        with open(contract_file, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return {}

    contracts = payload.get("contracts") if isinstance(payload, dict) else None
    if not isinstance(contracts, list):
        return {}

    by_copilot: dict[str, list[dict[str, Any]]] = {
        "sales": [],
        "inventory": [],
        "customer": [],
        "artist": [],
        "vendor": [],
    }
    for c in contracts:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("contract_id") or "")
        if cid.startswith("sales_"):
            by_copilot["sales"].append(c)
        elif cid.startswith("inventory_"):
            by_copilot["inventory"].append(c)
        elif cid.startswith("contact_"):
            by_copilot["customer"].append(c)
        elif cid.startswith("artist_"):
            by_copilot["artist"].append(c)
        elif cid.startswith("vendor_"):
            by_copilot["vendor"].append(c)
    return by_copilot


RUNTIME_CONTRACTS = _load_runtime_contracts()


def _validate_runtime_contract(
    *,
    sql: str,
    copilot: str | None,
    applied_limit: int | None,
    max_rows_default: int,
) -> tuple[bool, dict[str, Any]]:
    if not copilot:
        return True, {"ok": True, "skipped": True}

    contracts = RUNTIME_CONTRACTS.get(copilot, [])
    if not contracts:
        return True, {"ok": True, "skipped": True, "reason": "no_contracts_for_copilot"}

    relations = _extract_sql_relations(sql)
    allowed_relations: set[str] = set()
    detail_max_limit = max_rows_default

    for c in contracts:
        rels = c.get("preferred_relations") or []
        if isinstance(rels, list):
            for rel in rels:
                if isinstance(rel, str) and rel.strip():
                    allowed_relations.add(rel.strip().lower())
        if c.get("enforce_limit"):
            c_max = c.get("max_limit")
            if isinstance(c_max, int) and c_max > 0:
                detail_max_limit = max(detail_max_limit, c_max)

    violations: list[dict[str, Any]] = []
    if relations and allowed_relations and not relations.intersection(allowed_relations):
        violations.append(
            {
                "code": "relation_family_mismatch",
                "message": "Query relations are outside expected copilot relation families.",
                "relations": sorted(relations),
                "allowed_relations": sorted(allowed_relations),
            }
        )

    if applied_limit is not None and applied_limit > detail_max_limit:
        violations.append(
            {
                "code": "limit_exceeds_contract",
                "message": f"Applied LIMIT {applied_limit} exceeds allowed maximum {detail_max_limit}.",
            }
        )

    return (
        len(violations) == 0,
        {
            "ok": len(violations) == 0,
            "copilot": copilot,
            "relations": sorted(relations),
            "violations": violations,
        },
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/auth/login")
def auth_login(req: LoginRequest) -> dict[str, Any]:
    url = "https://v12-api.masterpiecemanager.com/signIn"
    body = urlparse.urlencode(
        {
            "txt_company": req.txt_company,
            "txt_username": req.txt_username,
            "txt_password": req.txt_password,
        }
    ).encode("utf-8")
    http_req = urlrequest.Request(url, data=body, method="POST")
    http_req.add_header("Content-Type", "application/x-www-form-urlencoded")
    http_req.add_header("Accept", "application/json")

    try:
        with urlrequest.urlopen(http_req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
    except urlerror.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8")
        except Exception:
            pass
        raise HTTPException(
            status_code=502,
            detail={
                "error": "upstream_login_failed",
                "message": f"HTTP {e.code}",
                "upstream_body": err_body,
            },
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "upstream_login_failed",
                "message": repr(e),
            },
        )

    try:
        payload = json.loads(raw)
    except Exception:
        raise HTTPException(status_code=502, detail={"error": "invalid_login_response"})

    if not payload.get("status"):
        raise HTTPException(
            status_code=401,
            detail={
                "error": "invalid_credentials",
                "message": payload.get("message", "Login failed"),
            },
        )

    data = payload.get("data") or {}
    user_info = (data.get("userInfo") or [{}])[0] or {}
    token = str(data.get("access_token") or "")
    token_payload = _decode_jwt_payload_unverified(token) if token else {}

    company_id = token_payload.get("company_id") or token_payload.get("idcompany")
    try:
        idcompany = int(company_id) if company_id is not None else None
    except Exception:
        idcompany = None

    session = {
        "access_token": token,
        "token_payload": token_payload,
        "idcompany": idcompany,
        "company_name": token_payload.get("company_name"),
        "username": user_info.get("username") or token_payload.get("username"),
        "firstname": user_info.get("firstname") or token_payload.get("firstname"),
        "lastname": user_info.get("lastname") or token_payload.get("lastname"),
        "role_name": user_info.get("role"),
        "role_id": token_payload.get("role"),
        "userid": token_payload.get("userid") or user_info.get("id"),
        "idcompany_location": token_payload.get("idcompany_location") or user_info.get("idcompany_location"),
        "location_name": user_info.get("location_name") or token_payload.get("location_name"),
    }

    return {
        "status": True,
        "message": payload.get("message", "Login Successful"),
        "session": session,
    }


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    requested_copilot = (req.copilot or "").strip().lower() or None
    if requested_copilot not in {None, "sales", "inventory", "customer", "artist", "vendor"}:
        raise HTTPException(status_code=400, detail={"error": "invalid_copilot"})
    routed_intent = _infer_routed_intent_from_question(req.question)
    selected_copilot = requested_copilot or _copilot_from_intent(routed_intent)

    resolved_idcompany = req.idcompany
    if req.access_token:
        token_payload = _decode_jwt_payload_unverified(req.access_token)
        token_company = token_payload.get("company_id") or token_payload.get("idcompany")
        try:
            token_company_int = int(token_company)
        except Exception:
            raise HTTPException(
                status_code=401,
                detail={"error": "invalid_token", "message": "Could not resolve company_id from JWT token."},
            )
        if token_company_int != req.idcompany:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "company_mismatch",
                    "message": "Request idcompany does not match JWT company_id.",
                    "token_company_id": token_company_int,
                    "request_idcompany": req.idcompany,
                },
            )
        resolved_idcompany = token_company_int

    start = time.time()
    request_id = str(uuid.uuid4())
    server_ts_utc = datetime.now(timezone.utc).isoformat()

    generation_path = "llm"
    generation_error = None
    v2_schema = build_schema_from_registry(selected_copilot)
    query, generation_error = generate_query_with_llm(
        req.question,
        copilot=selected_copilot,
        schema_from_context=v2_schema or None,
    )
    if query is None:
        generation_path = "deterministic_fallback"
        query = generate_query(req.question, copilot=selected_copilot)

    sql = query.sql
    matched_intent = query.intent
    params = {**query.params, "idcompany": resolved_idcompany}

    guard = validate_select_sql(sql=sql, required_idcompany_param="idcompany")
    if not guard.ok:
        raise HTTPException(status_code=400, detail={"error": "sql_blocked", "guardrails": guard.model_dump()})

    max_rows = int(os.getenv("MYSQL_MAX_ROWS", "200"))
    contract_ok, contract_guardrails = _validate_runtime_contract(
        sql=sql,
        copilot=selected_copilot,
        applied_limit=query.applied_limit,
        max_rows_default=max_rows,
    )
    # Contract checks are advisory now. Hard blocking remains in SQL safety guardrails.
    if not contract_ok:
        generation_error = (
            f"{generation_error}; contract_warning"
            if generation_error
            else "contract_warning"
        )

    timeout_ms = int(os.getenv("MYSQL_QUERY_TIMEOUT_MS", "8000"))
    retry_attempted = False
    retry_success = False
    try:
        result: QueryResult = run_select_query(sql=sql, params=params, max_rows=max_rows, timeout_ms=timeout_ms)
    except Exception as e:
        err_msg = str(e)
        # One self-heal retry for common LLM SQL errors.
        if generation_path == "llm" and (
            "unknown column" in err_msg.lower() or "syntax" in err_msg.lower()
        ):
            retry_attempted = True
            repaired_query, repair_err = generate_query_with_llm(
                req.question,
                copilot=selected_copilot,
                schema_from_context=v2_schema or None,
                error_context={"previous_sql": sql, "db_error": err_msg},
            )
            if repaired_query is not None:
                repaired_sql = repaired_query.sql
                repaired_params = {**repaired_query.params, "idcompany": resolved_idcompany}
                repaired_guard = validate_select_sql(sql=repaired_sql, required_idcompany_param="idcompany")
                if repaired_guard.ok:
                    repaired_contract_ok, repaired_contract_guard = _validate_runtime_contract(
                        sql=repaired_sql,
                        copilot=selected_copilot,
                        applied_limit=repaired_query.applied_limit,
                        max_rows_default=max_rows,
                    )
                    if not repaired_contract_ok:
                        generation_error = (
                            f"{generation_error}; contract_warning_after_retry"
                            if generation_error
                            else "contract_warning_after_retry"
                        )
                    try:
                        repaired_result: QueryResult = run_select_query(
                            sql=repaired_sql,
                            params=repaired_params,
                            max_rows=max_rows,
                            timeout_ms=timeout_ms,
                        )
                        # Promote repaired query to the active output/debug.
                        sql = repaired_sql
                        params = repaired_params
                        query = repaired_query
                        matched_intent = repaired_query.intent
                        guard = repaired_guard
                        contract_guardrails = repaired_contract_guard
                        generation_error = repair_err
                        result = repaired_result
                        retry_success = True
                    except Exception as e2:
                        raise HTTPException(status_code=500, detail={"error": "query_failed", "message": str(e2)})
                else:
                    raise HTTPException(
                        status_code=400,
                        detail={"error": "sql_blocked_after_retry", "guardrails": repaired_guard.model_dump()},
                    )
            else:
                raise HTTPException(status_code=500, detail={"error": "query_failed", "message": err_msg})
        else:
            raise HTTPException(status_code=500, detail={"error": "query_failed", "message": err_msg})

    elapsed_ms = int((time.time() - start) * 1000)

    answer = "Here are the results from your ERP data (read-only)."
    debug = None
    if req.debug:
        debug = DebugInfo(
            request_id=request_id,
            server_ts_utc=server_ts_utc,
            input_question=req.question,
            matched_intent=matched_intent,
            router_model=os.getenv("OPENAI_MODEL_ROUTER"),
            sql_model=os.getenv("OPENAI_MODEL_SQL"),
            generated_sql=sql,
            rendered_sql_preview=_render_sql_preview(sql, params),
            parameters=params,
            guardrails=guard,
            elapsed_ms=elapsed_ms,
            rows_returned=len(result.rows),
            requested_limit=query.requested_limit,
            applied_limit=query.applied_limit,
            window_label=query.window_label,
            generation_path=generation_path,
            generation_error=generation_error,
            retry_attempted=retry_attempted,
            retry_success=retry_success,
            resolved_idcompany=resolved_idcompany,
            selected_copilot=selected_copilot,
            routed_intent=routed_intent,
            contract_guardrails=contract_guardrails,
        )

    row_limit_notice = None
    if result.truncated:
        row_limit_notice = (
            f"Only the first {max_rows} rows are shown (Copilot default row limit). "
            "More rows matched your question but were not returned—narrow the date range or add filters."
        )
    return ChatResponse(
        answer=answer,
        data=result.rows,
        debug=debug,
        row_limit_notice=row_limit_notice,
        db_status=DbConnectionStatus(
            ok=True,
            detail="MySQL connection succeeded; read-only query completed.",
            database=os.getenv("MYSQL_DATABASE"),
        ),
    )


@app.post("/v3/ask", response_model=V3AskResponse)
def v3_ask(req: V3AskRequest) -> V3AskResponse:
    if os.getenv("V3_ASK_ENABLED", "1") not in {"1", "true", "TRUE", "yes", "YES"}:
        raise HTTPException(status_code=404, detail={"error": "v3_disabled"})
    resolved_idcompany = _resolve_idcompany_from_request(
        req_idcompany=req.idcompany,
        access_token=req.access_token,
    )
    try:
        return run_v3_ask(req=req, resolved_idcompany=resolved_idcompany)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": "v3_validation_failed", "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "v3_failed", "message": str(e)})

