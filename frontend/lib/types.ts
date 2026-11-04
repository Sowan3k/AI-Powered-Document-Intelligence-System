// Shapes returned by the DocIntel API. Money arrives as decimal strings and
// stays a string here: the browser never turns it into a float.

export type DocumentStatus = "queued" | "processing" | "completed" | "failed";
export type JobStatus = "queued" | "running" | "succeeded" | "failed";
export type ReviewStatus = "pending" | "ok" | "needs_review" | "reviewed";
export type Severity = "error" | "warning" | "info";

export type Job = {
  id: string;
  document_id: string;
  job_type: string;
  status: JobStatus;
  attempts: number;
  max_attempts: number;
  progress_done: number;
  progress_total: number | null;
  last_error: string | null;
  run_after: string;
  created_at: string;
  finished_at: string | null;
};

export type DocumentSummary = {
  id: string;
  filename: string;
  mime_type: string | null;
  size_bytes: number;
  page_count: number | null;
  source_kind: "pdf" | "image" | "spreadsheet" | "csv" | null;
  status: DocumentStatus;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  latest_job: Job | null;
  invoice_count: number | null;
};

export type Page<T> = { items: T[]; total: number; limit: number; offset: number };

export type HistoryEvent = {
  event: string;
  job_id: string | null;
  detail: Record<string, unknown> | null;
  created_at: string;
};

export type DocumentDetail = DocumentSummary & { jobs: Job[]; history: HistoryEvent[] };

export type FieldMeta = {
  confidence?: number;
  evidence?: string | null;
  raw?: string | null;
  flags?: string[];
};

export type LineItem = {
  position: number;
  description: string | null;
  quantity: string | null;
  unit_price: string | null;
  amount: string | null;
  confidence: number | null;
};

export type Issue = {
  rule_code: string;
  severity: Severity;
  field: string | null;
  message: string;
  details: Record<string, unknown> | null;
  created_at: string;
};

export type Correction = {
  field: string;
  old_value: unknown;
  new_value: unknown;
  username: string;
  created_at: string;
};

export type Invoice = {
  id: string;
  document_id: string;
  page_start: number | null;
  page_end: number | null;
  row_start: number | null;
  row_end: number | null;
  invoice_number: string | null;
  invoice_date: string | null;
  supplier_name: string | null;
  customer_name: string | null;
  subtotal: string | null;
  tax: string | null;
  total: string | null;
  currency: string | null;
  review_status: ReviewStatus;
  field_meta: Record<string, FieldMeta | unknown>;
  created_at: string;
  updated_at: string;
};

export type InvoiceDetail = Invoice & {
  line_items: LineItem[];
  issues: Issue[];
  corrections: Correction[];
};

export type PageText = {
  page_number: number;
  method: "digital" | "ocr" | "vision";
  ocr_confidence: number | null;
  text: string;
};

export type Results = { document: DocumentSummary; invoices: InvoiceDetail[]; pages: PageText[] };

export type UploadResult = {
  document_id: string;
  filename: string;
  status: DocumentStatus;
  error_code: string | null;
  error_message: string | null;
  job_id: string | null;
};

export type UploadResponse = { documents: UploadResult[]; accepted: number; rejected: number };

export type ReviewItem = Invoice & { filename: string; error_count: number; warning_count: number };

export type SearchHit = Invoice & { filename: string; score: number | null; line_items: LineItem[] };

export type SearchResponse = Page<SearchHit> & { mode: "keyword" | "semantic"; query: string | null };

export type ReconcileSide = {
  invoice_id: string;
  invoice_number: string | null;
  supplier_name: string | null;
  invoice_date: string | null;
  total: string | null;
  where: string;
};

export type ReconcileResult = {
  summary: {
    invoices_a: number;
    invoices_b: number;
    matched: number;
    mismatched: number;
    only_in_a: number;
    only_in_b: number;
  };
  matched: { a: ReconcileSide; b: ReconcileSide; matched_on: string }[];
  mismatched: {
    a: ReconcileSide;
    b: ReconcileSide;
    matched_on: string;
    differences: { field: string; a: unknown; b: unknown }[];
  }[];
  only_in_a: ReconcileSide[];
  only_in_b: ReconcileSide[];
};

export type Reconciliation = {
  id: string;
  document_a_id: string;
  document_b_id: string;
  result: ReconcileResult;
  created_at: string;
};

export const EDITABLE_FIELDS = [
  "invoice_number",
  "invoice_date",
  "supplier_name",
  "customer_name",
  "subtotal",
  "tax",
  "total",
  "currency",
] as const;
export type EditableField = (typeof EDITABLE_FIELDS)[number];
