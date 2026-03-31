"""
Align with copilot-widget-v3/src/app/report-filter-roll-dates.ts:
for Smart-default re-runs, roll end/snapshot date fields to today (MM/DD/YYYY)
while leaving start/from dates unchanged.

- Strict keys (*ToDate, todate, …): any non-empty value is replaced with today (ERP parity).
- Context keys (asof, cutoff, through, …): only values that look like calendar dates are updated.
"""

from __future__ import annotations

import json
import re
from datetime import date

_US_DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
_ISO_DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")

_END_DATE_KEYS: frozenset[str] = frozenset(
    {
        "mailingContactToDate",
        "mailingSaleToDate",
        "todate",
        "toDate",
        "dateTo",
        "DateTo",
        "saleToDate",
        "contactToDate",
    }
)

# Exact keys (lowercase) treated as “as of / snapshot / period end” — only if value looks like a date.
_CONTEXT_DATE_KEYS: frozenset[str] = frozenset(
    {
        "asof",
        "asofdate",
        "as_of",
        "as_of_date",
        "reportasof",
        "report_asof",
        "snapshotdate",
        "snapshot_date",
        "cutoffdate",
        "cut_off_date",
        "cutoff_date",
        "thrudate",
        "throughdate",
        "through_date",
        "periodenddate",
        "period_end_date",
        "endingdate",
        "enddate",
        "end_date",
        "datethrough",
        "date_through",
    }
)


def _looks_like_date_value(s: str) -> bool:
    if not s or not s.strip():
        return False
    t = s.strip()
    if _US_DATE_RE.fullmatch(t):
        return True
    if _ISO_DATE_PREFIX_RE.match(t):
        return True
    return False


def _is_exclude_key(key: str) -> bool:
    """Start / from bounds — never roll to today."""
    k = key.strip()
    if re.search(r"FromDate$", k, re.IGNORECASE):
        return True
    kl = k.lower()
    if kl in (
        "fromdate",
        "from_date",
        "startdate",
        "start_date",
        "begindate",
        "begin_date",
        "datefrom",
        "date_from",
        "mailingcontactfromdate",
    ):
        return True
    if re.search(r"fromdate$", k, re.IGNORECASE):
        return True
    if re.search(r"from_date$", k, re.IGNORECASE):
        return True
    if re.search(r"startdate$", k, re.IGNORECASE):
        return True
    if re.search(r"begindate$", k, re.IGNORECASE):
        return True
    if re.search(r"datefrom$", k, re.IGNORECASE):
        return True
    return False


def _is_end_date_key(key: str) -> bool:
    if key in _END_DATE_KEYS:
        return True
    k = key.strip()
    if re.search(r"todate$", k, re.IGNORECASE):
        return True
    if re.search(r"ToDate$", k, re.IGNORECASE) and not re.search(r"FromDate$", k, re.IGNORECASE):
        return True
    if re.search(r"DateTo$", k, re.IGNORECASE):
        return True
    return False


def _is_context_roll_key(key: str) -> bool:
    """As-of / snapshot / period-end style keys (not strict *ToDate)."""
    if _is_exclude_key(key):
        return False
    k = key.strip()
    kl = k.lower()
    if kl in _CONTEXT_DATE_KEYS:
        return True
    if re.fullmatch(r"asof(_date)?", kl):
        return True
    if re.search(r"(^|_)asof$", kl):
        return True
    if re.search(r"(^|_)asofdate$", kl):
        return True
    if re.search(r"(through|thru)date$", kl):
        return True
    if re.search(r"(cutoff|snapshot)date$", kl):
        return True
    if re.search(r"periodenddate$", kl):
        return True
    if re.search(r"(^|_)endingdate$", kl):
        return True
    return False


def _today_us() -> str:
    d = date.today()
    return f"{d.month:02d}/{d.day:02d}/{d.year:04d}"


def apply_rolling_end_dates_to_filter_data(filter_data: str) -> str:
    """
    Returns updated filter_data JSON string, or original if parse fails.
    """
    if not filter_data or not filter_data.strip():
        return filter_data
    try:
        obj = json.loads(filter_data)
    except json.JSONDecodeError:
        return filter_data
    if not isinstance(obj, dict):
        return filter_data

    today = _today_us()
    changed = False
    for key in list(obj.keys()):
        if _is_exclude_key(key):
            continue
        v = obj[key]
        if v is None:
            continue
        s = str(v).strip()
        if not s:
            continue

        if _is_end_date_key(key):
            # Same as legacy widget: any non-empty end-date value becomes today.
            obj[key] = today
            changed = True
            continue
        if _is_context_roll_key(key):
            if _looks_like_date_value(s):
                obj[key] = today
                changed = True
            continue

    if not changed:
        return filter_data
    try:
        return json.dumps(obj, separators=(",", ":"))
    except (TypeError, ValueError):
        return filter_data
