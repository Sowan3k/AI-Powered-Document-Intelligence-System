"use client";

import Link from "next/link";
import { useState } from "react";

import { JobProgress } from "@/components/job-progress";
import { Button, Card, Empty, ErrorBox, Loading, PageTitle, StatusBadge, inputClass } from "@/components/ui";
import { query } from "@/lib/api";
import { bytes, dateText } from "@/lib/format";
import type { DocumentSummary, Page } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const PAGE_SIZE = 20;
const ACTIVE = new Set(["queued", "processing"]);

export default function DocumentsPage() {
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const { data, error, loading, slow, reload } = useApi<Page<DocumentSummary>>(
    `/api/documents${query({ status, limit: PAGE_SIZE, offset })}`,
    // Poll while anything is still being processed.
    { pollMs: 3000, keepPolling: (page) => page.items.some((d) => ACTIVE.has(d.status)) },
  );

  return (
    <>
      <PageTitle title="Documents">
        <Link href="/upload" className="inline-flex min-h-10 items-center rounded-lg bg-neutral-900 px-4 text-sm font-medium text-white dark:bg-white dark:text-neutral-900">
          Upload files
        </Link>
      </PageTitle>
      <div className="flex items-center gap-2">
        <label htmlFor="status" className="text-sm font-medium">
          Status
        </label>
        <select
          id="status"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setOffset(0);
          }}
          className={`${inputClass} max-w-48`}
        >
          <option value="">All</option>
          <option value="queued">Queued</option>
          <option value="processing">Processing</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
        </select>
      </div>

      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading && !data && <Loading slow={slow} what="Loading documents" />}
      {data && data.items.length === 0 && <Empty>No documents yet. Upload a few files to start.</Empty>}

      <ul className="flex flex-col gap-3">
        {data?.items.map((doc) => (
          <li key={doc.id}>
            <Card>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <Link href={`/documents/${doc.id}`} className="break-all font-medium text-sky-700 hover:underline dark:text-sky-400">
                    {doc.filename}
                  </Link>
                  <p className="mt-1 text-xs text-neutral-600 dark:text-neutral-400">
                    {[doc.source_kind, doc.page_count ? `${doc.page_count} pages` : null, bytes(doc.size_bytes), dateText(doc.created_at)]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                  {doc.error_code && (
                    <p className="mt-1 text-sm text-red-700 dark:text-red-400">
                      {doc.error_code}: {doc.error_message}
                    </p>
                  )}
                </div>
                <div className="flex shrink-0 flex-col items-start gap-1 sm:items-end">
                  <StatusBadge status={doc.status} />
                  {doc.status === "completed" && <span className="text-xs">{doc.invoice_count} invoices</span>}
                </div>
              </div>
              {doc.latest_job && ACTIVE.has(doc.status) && (
                <div className="mt-2">
                  <JobProgress job={doc.latest_job} />
                </div>
              )}
            </Card>
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
    </>
  );
}
