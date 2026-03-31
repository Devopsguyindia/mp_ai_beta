/**
 * Human-readable labels for common ERP report filter JSON keys (mailing & general).
 * Unknown keys fall back to spaced Title Case.
 */

const LABELS: Record<string, string> = {
  mailingCustomers: 'Customers on mailing list',
  mailingVendors: 'Vendors on mailing list',
  mailingArtists: 'Artists on mailing list',
  mailingDesigners: 'Designers on mailing list',
  mailingGallery: 'Gallery on mailing list',
  dd_mailingGroup: 'Mailing group',
  dd_staff: 'Staff',
  dd_location: 'Location',
  dd_mailingtype: 'Mailing type',
  mailingDateAdded: 'Date added filter',
  mailingContactFromDate: 'Contact added from',
  mailingContactToDate: 'Contact added to',
  mailingContactCountry: 'Contact country',
  mailingContactState: 'Contact state / province',
  mailingContactCity: 'Contact city',
  dd_mailingSign: 'Signature / sign option',
  mailingSaleAmount: 'Sale amount',
  mailingSaleTotalAmount: 'Sale total amount',
  mailingContactNote: 'Contact note',
  mailingSaleFromDate: 'Sale from date',
  mailingSaleToDate: 'Sale to date',
  custom1: 'Custom field 1',
  custom2: 'Custom field 2',
  custom3: 'Custom field 3',
  mailingArtistAutoID: 'Artist ID',
  mailingContactArtist: 'Contact artist',
  mailingVendorAutoID: 'Vendor ID',
  mailingContactVendor: 'Contact vendor',
  dd_mailingCategory: 'Category',
  dd_mailingMedium: 'Medium',
  dd_mailingAttribute: 'Attribute',
  dd_mailingCostCode: 'Cost code',
  mailingItemTitle: 'Item title',
  mailingItemSubject: 'Item subject',
  mailingAllData: 'Include all data',
  orderby: 'Sort by',
  sortmethod: 'Sort direction',
  report_id: 'Report ID',
  type: 'Scope type',
  print_format: 'Export format'
};

function humanizeKey(key: string): string {
  const k = key.trim();
  if (!k) {
    return k;
  }
  if (LABELS[k]) {
    return LABELS[k];
  }
  const spaced = k.replace(/([a-z])([A-Z])/g, '$1 $2').replace(/_/g, ' ');
  return spaced.replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatValue(key: string, raw: string): string {
  const v = raw.trim();
  if (/^mailing/i.test(key) && (v === '1' || v === '0')) {
    return v === '1' ? 'Yes' : 'No';
  }
  if (key === 'sortmethod' && v.toUpperCase() === 'ASC') {
    return 'Ascending';
  }
  if (key === 'sortmethod' && v.toUpperCase() === 'DESC') {
    return 'Descending';
  }
  if (key === 'print_format' && v.toLowerCase() === 'csv') {
    return 'CSV';
  }
  if (key === 'type' && v.toLowerCase() === 'global') {
    return 'Global';
  }
  if (key === 'mailingDateAdded' && v.toLowerCase() === 'added') {
    return 'Date added';
  }
  return v;
}

function isValueSupplied(v: unknown): boolean {
  if (v === null || v === undefined) {
    return false;
  }
  return String(v).trim().length > 0;
}

/** Do not expose internal IDs or foreign keys to end users in filter summaries. */
function isExcludedKey(key: string): boolean {
  const k = key.trim();
  if (!k) {
    return true;
  }
  const lower = k.toLowerCase();
  if (lower === 'report_id' || lower === 'id') {
    return true;
  }
  if (/autoID$/i.test(k)) {
    return true;
  }
  if (/_id$/i.test(lower)) {
    return true;
  }
  return false;
}

/** Hide opaque numeric enum values (e.g. Signature / sign option: 4). */
function shouldSkipOpaqueNumericValue(key: string, raw: string): boolean {
  if (key === 'dd_mailingSign' && /^\d+$/.test(raw.trim())) {
    return true;
  }
  return false;
}

/**
 * Parse filter_data JSON and return label/value pairs only for non-empty values.
 */
export function summarizeReportFilters(filterData: string | null | undefined): { label: string; value: string }[] {
  if (!filterData || !filterData.trim()) {
    return [];
  }
  let obj: Record<string, unknown>;
  try {
    obj = JSON.parse(filterData) as Record<string, unknown>;
  } catch {
    return [];
  }
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) {
    return [];
  }
  const out: { label: string; value: string }[] = [];
  const keys = Object.keys(obj).sort((a, b) => humanizeKey(a).localeCompare(humanizeKey(b)));
  for (const key of keys) {
    if (isExcludedKey(key)) {
      continue;
    }
    const val = obj[key];
    if (!isValueSupplied(val)) {
      continue;
    }
    const str = String(val).trim();
    if (shouldSkipOpaqueNumericValue(key, str)) {
      continue;
    }
    out.push({
      label: humanizeKey(key),
      value: formatValue(key, str)
    });
  }
  return out;
}
