// Display helpers. Money stays a string; it is only grouped for reading.

export const FIELD_LABELS: Record<string, string> = {
  invoice_number: "Invoice number",
  invoice_date: "Invoice date",
  supplier_name: "Supplier",
  customer_name: "Customer",
  subtotal: "Subtotal",
  tax: "Tax",
  total: "Total",
  currency: "Currency",
  line_items: "Line items",
};

export function label(field: string | null | undefined): string {
  if (!field) return "";
  return FIELD_LABELS[field] ?? field.replaceAll("_", " ");
}

export function money(value: string | null | undefined, currency?: string | null): string {
  if (value === null || value === undefined || value === "") return "—";
  const [whole, fraction] = value.split(".");
  const negative = whole.startsWith("-");
  const digits = negative ? whole.slice(1) : whole;
  const grouped = digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const text = `${negative ? "-" : ""}${grouped}${fraction !== undefined ? `.${fraction}` : ""}`;
  return currency ? `${text} ${currency}` : text;
}

/** Quantities and unit prices are stored with four decimals; show only the ones that matter. */
export function trimmed(value: string | null | undefined, minDecimals = 0): string {
  if (value === null || value === undefined || value === "") return "—";
  const [whole, fraction = ""] = value.split(".");
  let keep = fraction.replace(/0+$/, "");
  if (keep.length < minDecimals) keep = keep.padEnd(minDecimals, "0");
  return money(keep ? `${whole}.${keep}` : whole);
}

export function dateText(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  if (Number.isNaN(d.getTime())) return value;
  return value.length === 10
    ? d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })
    : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function percent(confidence: number | undefined | null): string {
  return confidence === undefined || confidence === null ? "—" : `${Math.round(confidence * 100)}%`;
}

export function where(inv: { page_start: number | null; page_end: number | null; row_start: number | null; row_end: number | null }): string {
  if (inv.page_start !== null) {
    return inv.page_end && inv.page_end !== inv.page_start
      ? `pages ${inv.page_start}–${inv.page_end}`
      : `page ${inv.page_start}`;
  }
  if (inv.row_start !== null) {
    return inv.row_end && inv.row_end !== inv.row_start
      ? `rows ${inv.row_start}–${inv.row_end}`
      : `row ${inv.row_start}`;
  }
  return "";
}

export const EVENT_LABELS: Record<string, string> = {
  uploaded: "File stored",
  rejected: "File rejected",
  job_queued: "Queued",
  job_started: "Processing started",
  ingest_started: "Reading the file",
  ingested: "File read",
  ingest_failed: "File could not be read",
  vision_page: "Page read by the vision model",
  vision_failed: "Vision model unavailable, kept OCR text",
  extract_started: "Extracting invoices",
  llm_call: "Model call",
  extracted: "Invoices extracted",
  extract_failed: "Extraction failed",
  validated: "Validated",
  completed: "Completed",
  job_succeeded: "Job finished",
  job_retry_scheduled: "Will retry",
  job_failed: "Job failed",
  job_recovered: "Recovered after a worker stop",
  job_retry_requested: "Retry requested",
};

/**
 * b minus a for two decimal strings, exact, for display only: "1105.15" and
 * "1150.15" give "+45.00". It works in whole units of the smallest decimal
 * place with BigInt, so no floating point touches money. Returns null when
 * either side is not a plain number.
 */
export function decimalChange(a: unknown, b: unknown): string | null {
  const plain = /^-?\d+(\.\d+)?$/;
  if (typeof a !== "string" || typeof b !== "string" || !plain.test(a) || !plain.test(b)) return null;
  const places = Math.max(a.split(".")[1]?.length ?? 0, b.split(".")[1]?.length ?? 0);
  const units = (s: string) => {
    const negative = s.startsWith("-");
    const [whole, fraction = ""] = (negative ? s.slice(1) : s).split(".");
    const n = BigInt(whole + fraction.padEnd(places, "0"));
    return negative ? -n : n;
  };
  const d = units(b) - units(a);
  const negative = d < BigInt(0);
  const digits = (negative ? -d : d).toString().padStart(places + 1, "0");
  const text = places ? `${digits.slice(0, -places)}.${digits.slice(-places)}` : digits;
  return `${negative ? "−" : "+"}${money(text)}`;
}
