"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { useActivity } from "@/components/activity";
import { ApproveButton } from "@/components/approve-button";
import { BulkActions, RetryAllFailed } from "@/components/bulk-actions";
import { DropZone } from "@/components/drop-zone";
import { ExportButton } from "@/components/export-button";
import { SearchIcon } from "@/components/icons";
import { ProcessFlow } from "@/components/process-flow";
import { StatsLine } from "@/components/stats-line";
import { Button, Card, Empty, ErrorBox, Loading, StatusBadge, inputClass } from "@/components/ui";
import { query } from "@/lib/api";
import { bytes, dateText, money } from "@/lib/format";
import type { DocumentSummary, Page, ReviewItem } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const PAGE_SIZE = 20;
const FILTERS = [
  { value: "", label: "All" },
  { value: "processing", label: "Processing" },
  { value: "completed", label: "Done" },
  { value: "failed", label: "Failed" },
];

export default function HomePage() {
  const { activity } = useActivity();
  const active = activity?.active ?? [];
  return (
    <>
      <QuickSearch />
      <DropZone />
      {active.length > 0 && (
        <section className="flex flex-col gap-2">
          <h2 className="type-section">Processing now</h2>
          {active.map((item) => (
            <Link key={item.document_id} href={`/documents/${item.document_id}`} className="block">
              <Card className="hover:border-brand/40">
                <p className="mb-2 truncate text-sm font-medium">{item.filename}</p>
                <ProcessFlow item={item} />
              </Card>
            </Link>
          ))}
        </section>
      )}
      <NeedsAttention />
      <RecentDocuments />
    </>
  );
}

function QuickSearch() {
  const router = useRouter();
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const q = String(new FormData(e.currentTarget).get("q") ?? "").trim();
    router.push(`/search${query({ q })}`);
  }
  return (
    <form onSubmit={submit} role="search" className="relative">
      <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-5 -translate-y-1/2 text-neutral-400" />
      <input name="q" placeholder="Search invoices: number, supplier, item…" className={`${inputClass} min-h-12 rounded-xl pl-10`} aria-label="Search invoices" />
    </form>
  );
}

function NeedsAttention() {
  const { activity } = useActivity();
  const reviewCount = activity?.review_count;
  const { data, reload } = useApi<Page<ReviewItem>>("/api/review-queue?limit=3");
  const [hidden, setHidden] = useState<string[]>([]);
  useEffect(() => {
    // New results or approvals change the queue; fetch it again.
    if (reviewCount !== undefined) reload();
  }, [reviewCount, reload]);
  const items = (data?.items ?? []).filter((i) => !hidden.includes(i.id));
  if (!data || items.length === 0) return null;
  return (
    <section className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between">
        <h2 className="type-section">Needs your attention</h2>
        {data.total > items.length && (
          <Link href="/review" className="text-sm font-medium text-brand">
            See all {data.total}
          </Link>
        )}
      </div>
      {items.map((inv) => (
        <Card key={inv.id}>
          <Link href={`/documents/${inv.document_id}`} className="block">
            <div className="flex items-baseline justify-between gap-2">
              <p className="font-medium">{inv.invoice_number ?? "No invoice number"}</p>
              <p className="shrink-0 text-sm font-medium tabular-nums">{money(inv.total, inv.currency)}</p>
            </div>
            <p className="truncate text-sm text-neutral-600 dark:text-neutral-400">{inv.supplier_name ?? "Unknown supplier"}</p>
            {inv.top_issue && (
              <p className="mt-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800 dark:bg-red-950/40 dark:text-red-300">
                {inv.top_issue}
                {inv.error_count > 1 && <span className="text-red-600"> (+{inv.error_count - 1} more)</span>}
              </p>
            )}
          </Link>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:flex sm:justify-end">
            <Link href={`/documents/${inv.document_id}`} className="inline-flex min-h-10 items-center justify-center rounded-lg border border-black/15 px-4 text-sm font-medium dark:border-white/20">
              Fix
            </Link>
            <ApproveButton invoiceId={inv.id} onDone={() => setHidden((h) => [...h, inv.id])} />
          </div>
        </Card>
      ))}
    </section>
  );
}

function RecentDocuments() {
  const { activity, refresh } = useActivity();
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const { data, error, loading, slow, reload } = useApi<Page<DocumentSummary>>(
    `/api/documents${query({ status, limit: PAGE_SIZE, offset })}`,
  );
  const [marked, setMarked] = useState<string[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const changes = `${activity?.active.length ?? 0}:${activity?.recent.length ?? 0}:${activity?.recent[0]?.updated_at ?? ""}`;
  useEffect(() => {
    reload(); // a file started or finished: refresh the list
  }, [changes, reload]);

  const pageIds = data?.items.map((d) => d.id) ?? [];
  const allOnPage = pageIds.length > 0 && pageIds.every((id) => marked.includes(id));
  const toggle = (id: string, on: boolean) => setMarked((m) => (on ? [...new Set([...m, id])] : m.filter((x) => x !== id)));
  const finished = (message: string) => {
    setNotice(message);
    setMarked([]);
    reload();
    refresh();
  };

  return (
    <section className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="type-section">Your documents</h2>
        <div className="flex gap-1" role="tablist" aria-label="Filter documents">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              role="tab"
              aria-selected={status === f.value}
              onClick={() => {
                setStatus(f.value);
                setOffset(0);
                setMarked([]);
              }}
              className={`rounded-full px-3 py-1.5 text-xs font-medium ${status === f.value ? "bg-neutral-900 text-white dark:bg-white dark:text-neutral-900" : "bg-neutral-100 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300"}`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>
      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading && !data && <Loading slow={slow} what="Loading documents" />}
      {data && data.items.length === 0 && <Empty>{status ? "Nothing here." : "No documents yet. Add a few files above."}</Empty>}
      {notice && (
        <p role="status" className="text-sm text-neutral-700 dark:text-neutral-300">
          {notice}
        </p>
      )}
      {status === "failed" && data && data.total > 0 && <RetryAllFailed onDone={finished} />}
      {marked.length > 0 && data && <BulkActions marked={marked} docs={data.items} onDone={finished} />}
      {data && data.items.length > 0 && (
        <label className="flex items-center gap-2 px-1 text-xs text-neutral-600 dark:text-neutral-400">
          <input
            type="checkbox"
            className="size-4"
            checked={allOnPage}
            onChange={(e) => setMarked((m) => (e.target.checked ? [...new Set([...m, ...pageIds])] : m.filter((id) => !pageIds.includes(id))))}
          />
          Mark all on this page
        </label>
      )}
      <ul className="flex flex-col divide-y divide-black/5 overflow-hidden rounded-xl border border-black/10 bg-white dark:divide-white/10 dark:border-white/15 dark:bg-neutral-900">
        {data?.items.map((doc) => (
          <li key={doc.id} className="flex items-center">
            <input
              type="checkbox"
              aria-label={`Mark ${doc.filename}`}
              checked={marked.includes(doc.id)}
              onChange={(e) => toggle(doc.id, e.target.checked)}
              className="ml-4 size-4 shrink-0"
            />
            <Link href={`/documents/${doc.id}`} className="flex min-w-0 flex-1 items-center justify-between gap-3 px-3 py-3 hover:bg-neutral-50 dark:hover:bg-neutral-800">
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium">{doc.filename}</span>
                <span className="block text-xs text-neutral-500">
                  {doc.status === "completed" && doc.invoice_count === 0 && (
                    <span className="font-medium text-amber-700 dark:text-amber-400">No invoice found · </span>
                  )}
                  {doc.status === "completed" && !!doc.invoice_count && `${doc.invoice_count} invoice${doc.invoice_count === 1 ? "" : "s"} · `}
                  {doc.error_code ? `${doc.error_code} · ` : ""}
                  {bytes(doc.size_bytes)} · {dateText(doc.created_at)}
                </span>
              </span>
              <StatusBadge status={doc.status} />
            </Link>
          </li>
        ))}
      </ul>
      {data && data.total > PAGE_SIZE && (
        <div className="flex items-center justify-between text-sm">
          <Button variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
            Previous
          </Button>
          <span>
            {offset + 1}–{Math.min(offset + PAGE_SIZE, data.total)} of {data.total}
          </span>
          <Button variant="secondary" disabled={offset + PAGE_SIZE >= data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>
            Next
          </Button>
        </div>
      )}
      {data && data.total > 0 && <ExportButton />}
      <StatsLine changes={changes} />
    </section>
  );
}
