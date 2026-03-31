from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ReportSuggestionsRequest(BaseModel):
    idcompany: int = Field(..., ge=1)
    access_token: str | None = None
    user_id: int | None = Field(
        default=None,
        description="If set, scopes usage to this user only; otherwise gallery-wide.",
    )
    top_n: int = Field(default=5, ge=1, le=50, description="Max top reports by total usage.")
    recent_n: int = Field(default=10, ge=1, le=100, description="Max recent usage rows.")
    smart_default_limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Max distinct reports to return smart defaults for.",
    )
    truncate_filter_data: bool = Field(
        default=True,
        description="If true, long filter_data JSON is truncated in the response.",
    )
    filter_data_max_chars: int = Field(default=4000, ge=500, le=50000)


class TopReportItem(BaseModel):
    report_id: int
    total_usage: int
    report_name: str | None = None
    name_source: str | None = Field(
        default=None,
        description="global | gallery | unknown",
    )


class RecentRunItem(BaseModel):
    report_id: int
    user_id: int
    usage_count: int
    last_used: Any = None
    filter_hash: str
    filter_data: str | None = None
    filter_data_truncated: bool = False
    report_name: str | None = None


class SmartDefaultItem(BaseModel):
    report_id: int
    filter_hash: str
    usage_sum: int
    filter_data: str | None = None
    filter_data_truncated: bool = False
    report_name: str | None = None


class PredictHintItem(BaseModel):
    report_id: int
    report_name: str | None = None
    weekday: int = Field(..., description="MySQL DAYOFWEEK: 1=Sunday .. 7=Saturday")
    weekday_label: str
    run_count: int


class ReportRerunRequest(BaseModel):
    """Proxy re-run: server GETs MP generateReport with Authorization = sign-in token (see MP_REPORT_AUTH_BEARER)."""

    access_token: str = Field(..., min_length=8)
    filter_data: str = Field(..., min_length=2, description="Original filter_data JSON string from report_usage")
    roll_end_dates: bool = Field(
        default=True,
        description="If true, set *ToDate / end-date keys to today (MM/DD/YYYY). Use false to re-run with stored dates (e.g. Recent runs).",
    )


class ReportSuggestionsResponse(BaseModel):
    ok: bool = True
    idcompany: int
    scoped_to_user_id: int | None = None
    top_reports: list[TopReportItem] = []
    recent_runs: list[RecentRunItem] = []
    smart_defaults: list[SmartDefaultItem] = []
    predict_hints: list[PredictHintItem] = []
    warnings: list[str] = []
