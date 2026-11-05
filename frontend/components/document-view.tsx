"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useActivity } from "@/components/activity";
import { InvoiceCard } from "@/components/invoice-card";
import { JobProgress } from "@/components/job-progress";
import { OriginalFile } from "@/components/original-file";
import { ProcessFlow } from "@/components/process-flow";
import { Badge, Button, Card, Empty, ErrorBox, Loading, PageTitle, StatusBadge } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { bytes, dateText, EVENT_LABELS } from "@/lib/format";
import type { DocumentDetail, InvoiceDetail, Results } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const ACTIVE = new Set(["queued", "processing"]);

export function DocumentView() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { activity, refresh } = useActivity();
  const doc = useApi<DocumentDetail>(`/api/documents/${id}`, {
    pollMs: 2500,
    keepPolling: (d) => ACTIVE.has(d.status) || d.jobs.some((j) => j.status === "queued" || j.status === "running"),
  });
  const done = doc.data?.status === "completed";
  const results = useApi<Results>(done ? `/api/documents/${id}/results?include_pages=true` : null);
  const reloadResults = results.reload;
  const [invoices, setInvoices] = useState<InvoiceDetail[] | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    // Keep a local copy, so a saved correction shows at once.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (results.data) setInvoices(results.data.invoices);
  }, [results.data]);

  const updatedAt = doc.data?.updated_at;
  useEffect(() => {
    if (done) reloadResults();
  }, [done, updatedAt, reloadResults]);

  const live = activity?.active.find((a) => a.document_id === id) ?? null;
  if (doc.error && !doc.data) return <ErrorBox message={doc.error} onRetry={doc.reload} />;
  if (!doc.data) return <Loading slow={doc.slow} what="Loading document" />;
  const d = doc.data;
  const job = d.latest_job;

  async function act(path: string) {
    setActionError(null);
    try {
      await api(path, { method: "POST" });
      doc.reload();
      refresh();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "That did not work.");
    }
  }

  async function remove() {
    if (!window.confirm(`Delete ${d.filename} and everything extracted from it? This cannot be undone.`)) return;
    setActionError(null);
    try {
      await api(`/api/documents/${d.id}`, { method: "DELETE" });
      refresh();
      router.push("/documents");
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "That did not work.");
    }
  }

  return (
    <>
      <PageTitle title={d.filename}>
        <StatusBadge status={d.status} />
      </PageTitle>
      <p className="-mt-3 text-sm text-neutral-600 dark:text-neutral-400">
        {[d.source_kind, d.page_count ? `${d.page_count} pages` : null, bytes(d.size_bytes), `uploaded ${dateText(d.created_at)}`]
          .filter(Boolean)
          .join(" · ")}
      </p>

      {d.error_code && <ErrorBox message={`${d.error_code}: ${d.error_message ?? ""}`} />}
      {live && (
        <Card>
          <ProcessFlow item={live} />
        </Card>
      )}
      {!live && job && job.status === "failed" && <JobProgress job={job} />}
      {actionError && <ErrorBox message={actionError} />}

      <div className="flex flex-wrap gap-2">
        {job?.status === "failed" && (
          <Button onClick={() => act(`/api/jobs/${job.id}/retry`)}>Retry failed job</Button>
        )}
        {!ACTIVE.has(d.status) && d.status !== "queued" && job && (
          <Button variant="secondary" onClick={() => act(`/api/documents/${d.id}/reprocess`)}>
            Process again
          </Button>
        )}
        {!ACTIVE.has(d.status) && (
          <Button variant="ghost" onClick={remove} className="text-red-700 dark:text-red-400">
            Delete
          </Button>
        )}
      </div>
      {d.mime_type && d.status !== "failed" && (
        <OriginalFile documentId={d.id} mimeType={d.mime_type} filename={d.filename} />
      )}

      {ACTIVE.has(d.status) && !live && <Loading what="Processing. This page updates by itself" />}

      {done && (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          <section className="flex flex-col gap-3">
            <h2 className="type-section">Extracted invoices</h2>
            {results.error && <ErrorBox message={results.error} onRetry={results.reload} />}
            {!invoices && <Loading slow={results.slow} what="Loading results" />}
            {invoices?.length === 0 && (
              <p role="status" className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-200">
                <span className="block font-medium">No invoice found</span>
                This file does not look like an invoice or receipt, so nothing was extracted. If it is one, upload a clearer copy.
              </p>
            )}
            {invoices?.map((inv) => (
              <InvoiceCard
                key={inv.id}
                invoice={inv}
                onSaved={(saved) => setInvoices((list) => list?.map((x) => (x.id === saved.id ? saved : x)) ?? null)}
              />
            ))}
          </section>
          <SourceText results={results.data} />
        </div>
      )}

      <History doc={d} />
    </>
  );
}

function evidenceOf(results: Results): string[] {
  const out = new Set<string>();
  for (const inv of results.invoices) {
    for (const meta of Object.values(inv.field_meta)) {
      const m = meta as { evidence?: string | null; flags?: string[] } | null;
      if (m?.evidence && m.evidence.trim().length >= 3 && !m.flags?.includes("corrected")) out.add(m.evidence.trim());
    }
  }
  return [...out];
}

// Marks the text each extracted value came from, so a reviewer sees where it was
// read. Whitespace may differ between the model's copy and the page, so runs of
// spaces match any whitespace. React escapes the text; nothing is injected as HTML.
function Highlighted({ text, snippets }: { text: string; snippets: string[] }) {
  if (snippets.length === 0) return <>{text}</>;
  const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "\\s+");
  const pattern = new RegExp(`(${[...snippets].sort((a, b) => b.length - a.length).map(escape).join("|")})`, "g");
  const parts = text.split(pattern);
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <mark key={i} className="rounded bg-amber-200 px-0.5 text-inherit dark:bg-amber-700/60">
            {part}
          </mark>
        ) : (
          part
        ),
      )}
    </>
  );
}

function SourceText({ results }: { results: Results | null }) {
  const evidence = results ? evidenceOf(results) : [];
  if (!results || results.pages.length === 0) {
    return results ? (
      <section className="flex flex-col gap-3">
        <h2 className="type-section">Source</h2>
        <Empty>Spreadsheet rows are shown with each invoice&apos;s row numbers.</Empty>
      </section>
    ) : null;
  }
  return (
    <section className="flex flex-col gap-3 lg:sticky lg:top-16 lg:max-h-[calc(100vh-5rem)] lg:overflow-y-auto">
      <h2 className="type-section">Source text</h2>
      {results.pages.map((p) => (
        <details key={p.page_number} open={results.pages.length <= 2} className="rounded-xl border border-black/10 bg-white p-3 dark:border-white/15 dark:bg-neutral-900">
          <summary className="flex cursor-pointer flex-wrap items-center gap-2 text-sm">
            <span className="font-medium">Page {p.page_number}</span>
            <Badge tone={p.method === "digital" ? "green" : p.method === "vision" ? "blue" : "gray"}>{p.method}</Badge>
            {p.ocr_confidence !== null && <span className="text-xs text-neutral-500">OCR {Math.round(p.ocr_confidence)}%</span>}
          </summary>
          <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-relaxed">
            {p.text ? <Highlighted text={p.text} snippets={evidence} /> : "(no text)"}
          </pre>
        </details>
      ))}
    </section>
  );
}

function History({ doc }: { doc: DocumentDetail }) {
  const events = doc.history.filter((e) => e.event !== "llm_call");
  const calls = doc.history.filter((e) => e.event === "llm_call");
  const tokens = calls.reduce(
    (sum, e) =>
      sum + Number(e.detail?.prompt_tokens ?? 0) + Number(e.detail?.output_tokens ?? 0) + Number(e.detail?.thinking_tokens ?? 0),
    0,
  );
  return (
    <Card>
      <details>
        <summary className="cursor-pointer font-semibold">Processing history</summary>
        {calls.length > 0 && (
          <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-400">
            {calls.length} model call{calls.length === 1 ? "" : "s"}, {tokens.toLocaleString()} tokens
          </p>
        )}
        <ol className="mt-3 flex flex-col gap-2 text-sm">
          {events.map((e, i) => (
            <li key={i} className="flex flex-wrap gap-x-3">
              <span className="w-40 shrink-0 text-xs text-neutral-500">{dateText(e.created_at)}</span>
              <span>
                {EVENT_LABELS[e.event] ?? e.event}
                {typeof e.detail?.error_code === "string" && ` (${e.detail.error_code})`}
                {typeof e.detail?.error === "string" && ` (${e.detail.error})`}
                {typeof e.detail?.invoices === "number" && ` (${e.detail.invoices} invoices)`}
              </span>
            </li>
          ))}
        </ol>
      </details>
    </Card>
  );
}
