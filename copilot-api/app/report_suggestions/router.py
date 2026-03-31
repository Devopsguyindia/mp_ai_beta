from __future__ import annotations

import base64
import json
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from .models import ReportRerunRequest, ReportSuggestionsRequest, ReportSuggestionsResponse
from .rerun_proxy import proxy_generate_report_get
from .service import build_report_suggestions


def _decode_jwt_payload_unverified(token: str) -> dict:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8")
        data = json.loads(decoded)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _resolve_idcompany(*, req_idcompany: int, access_token: str | None) -> int:
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


router = APIRouter(prefix="/reports", tags=["report_suggestions"])


@router.post("/rerun")
def post_report_rerun(req: ReportRerunRequest) -> Response:
    if os.getenv("REPORT_RERUN_ENABLED", "1") not in {"1", "true", "TRUE", "yes", "YES"}:
        raise HTTPException(status_code=404, detail={"error": "report_rerun_disabled"})
    return proxy_generate_report_get(
        access_token=req.access_token.strip(),
        filter_data=req.filter_data,
        roll_end_dates=req.roll_end_dates,
    )


@router.post("/suggestions", response_model=ReportSuggestionsResponse)
def post_report_suggestions(req: ReportSuggestionsRequest) -> ReportSuggestionsResponse:
    if os.getenv("REPORT_SUGGESTIONS_ENABLED", "1") not in {"1", "true", "TRUE", "yes", "YES"}:
        raise HTTPException(status_code=404, detail={"error": "report_suggestions_disabled"})

    resolved = _resolve_idcompany(req_idcompany=req.idcompany, access_token=req.access_token)

    return build_report_suggestions(
        idcompany=resolved,
        user_id=req.user_id,
        top_n=req.top_n,
        recent_n=req.recent_n,
        smart_default_limit=req.smart_default_limit,
        truncate_filter_data=req.truncate_filter_data,
        filter_data_max_chars=req.filter_data_max_chars,
    )
