/**
 * For Smart-default re-runs: roll end/snapshot date fields to today (MM/DD/YYYY)
 * while leaving start/from dates unchanged. Kept in sync with
 * copilot-api/app/report_suggestions/report_filter_roll_dates.py.
 */

const US_DATE_RE = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/;

/** Keys whose values are strict end dates (case-sensitive keys as in ERP JSON). */
const END_DATE_KEYS: ReadonlySet<string> = new Set([
  'mailingContactToDate',
  'mailingSaleToDate',
  'todate',
  'toDate',
  'dateTo',
  'DateTo',
  'saleToDate',
  'contactToDate'
]);

/** Lowercase exact keys: as-of / snapshot / period-end — only if value looks like a date. */
const CONTEXT_DATE_KEYS: ReadonlySet<string> = new Set([
  'asof',
  'asofdate',
  'as_of',
  'as_of_date',
  'reportasof',
  'report_asof',
  'snapshotdate',
  'snapshot_date',
  'cutoffdate',
  'cut_off_date',
  'cutoff_date',
  'thrudate',
  'throughdate',
  'through_date',
  'periodenddate',
  'period_end_date',
  'endingdate',
  'enddate',
  'end_date',
  'datethrough',
  'date_through'
]);

function looksLikeDateValue(s: string): boolean {
  const t = s.trim();
  if (!t) {
    return false;
  }
  if (US_DATE_RE.test(t)) {
    return true;
  }
  if (/^\d{4}-\d{2}-\d{2}/.test(t)) {
    return true;
  }
  return false;
}

function isExcludeKey(key: string): boolean {
  if (/FromDate$/i.test(key)) {
    return true;
  }
  const kl = key.trim().toLowerCase();
  if (
    [
      'fromdate',
      'from_date',
      'startdate',
      'start_date',
      'begindate',
      'begin_date',
      'datefrom',
      'date_from',
      'mailingcontactfromdate'
    ].includes(kl)
  ) {
    return true;
  }
  if (/fromdate$/i.test(key)) {
    return true;
  }
  if (/from_date$/i.test(key)) {
    return true;
  }
  if (/startdate$/i.test(key)) {
    return true;
  }
  if (/begindate$/i.test(key)) {
    return true;
  }
  if (/datefrom$/i.test(key)) {
    return true;
  }
  return false;
}

function isEndDateKey(key: string): boolean {
  if (END_DATE_KEYS.has(key)) {
    return true;
  }
  const k = key.trim();
  if (/todate$/i.test(k)) {
    return true;
  }
  if (/ToDate$/i.test(k) && !/FromDate$/i.test(k)) {
    return true;
  }
  if (/DateTo$/i.test(k)) {
    return true;
  }
  return false;
}

function isContextRollKey(key: string): boolean {
  if (isExcludeKey(key)) {
    return false;
  }
  const kl = key.trim().toLowerCase();
  if (CONTEXT_DATE_KEYS.has(kl)) {
    return true;
  }
  if (/^asof(_date)?$/i.test(kl)) {
    return true;
  }
  if (/(^|_)asof$/i.test(kl)) {
    return true;
  }
  if (/(^|_)asofdate$/i.test(kl)) {
    return true;
  }
  if (/(through|thru)date$/i.test(kl)) {
    return true;
  }
  if (/(cutoff|snapshot)date$/i.test(kl)) {
    return true;
  }
  if (/periodenddate$/i.test(kl)) {
    return true;
  }
  if (/(^|_)endingdate$/i.test(kl)) {
    return true;
  }
  return false;
}

function todayUs(): string {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  const yyyy = d.getFullYear();
  return `${mm}/${dd}/${yyyy}`;
}

/**
 * Returns updated filter_data JSON string, or original if parse fails.
 */
export function applyRollingEndDatesToFilterData(filterData: string | null | undefined): string {
  if (!filterData || !filterData.trim()) {
    return filterData || '';
  }
  let obj: Record<string, unknown>;
  try {
    obj = JSON.parse(filterData) as Record<string, unknown>;
  } catch {
    return filterData;
  }
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) {
    return filterData;
  }
  const today = todayUs();
  let changed = false;
  for (const key of Object.keys(obj)) {
    if (isExcludeKey(key)) {
      continue;
    }
    const v = obj[key];
    if (v === null || v === undefined) {
      continue;
    }
    const s = String(v).trim();
    if (!s) {
      continue;
    }
    if (isEndDateKey(key)) {
      if (US_DATE_RE.test(s)) {
        obj[key] = today;
        changed = true;
        continue;
      }
      if (/^\d{4}-\d{2}-\d{2}/.test(s)) {
        obj[key] = today;
        changed = true;
        continue;
      }
      obj[key] = today;
      changed = true;
      continue;
    }
    if (isContextRollKey(key)) {
      if (looksLikeDateValue(s)) {
        obj[key] = today;
        changed = true;
      }
      continue;
    }
  }
  if (!changed) {
    return filterData;
  }
  try {
    return JSON.stringify(obj);
  } catch {
    return filterData;
  }
}
