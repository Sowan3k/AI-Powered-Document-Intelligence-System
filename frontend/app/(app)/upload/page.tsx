"use client";

import Link from "next/link";
import { useRef, useState, type DragEvent } from "react";

import { Button, Card, ErrorBox, PageTitle, StatusBadge } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { bytes } from "@/lib/format";
import type { DocumentSummary, UploadResponse, UploadResult } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const ACCEPT = ".pdf,.jpg,.jpeg,.png,.tif,.tiff,.xlsx,.xls,.csv";

export default function UploadPage() {
  const input = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<UploadResult[] | null>(null);

  function add(list: FileList | null) {
    if (!list) return;
    setResults(null);
    setFiles((current) => [...current, ...Array.from(list)]);
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    add(event.dataTransfer.files);
  }

  async function upload() {
    setBusy(true);
    setError(null);
    const form = new FormData();
    for (const file of files) form.append("files", file);
    try {
      const body = await api<UploadResponse>("/api/documents", { method: "POST", body: form });
      setResults(body.documents);
      setFiles([]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageTitle title="Upload" />
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`flex flex-col items-center gap-3 rounded-xl border-2 border-dashed p-8 text-center ${dragging ? "border-sky-500 bg-sky-50 dark:bg-sky-950/30" : "border-black/15 dark:border-white/20"}`}
      >
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          Drop invoices, receipts, scans or spreadsheets here: PDF, JPG, PNG, TIFF, XLSX, XLS or CSV.
        </p>
        <Button variant="secondary" onClick={() => input.current?.click()}>
          Choose files
        </Button>
        <input
          ref={input}
          type="file"
          multiple
          accept={ACCEPT}
          className="sr-only"
          aria-label="Choose files"
          onChange={(e) => {
            add(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {files.length > 0 && (
        <Card>
          <ul className="flex flex-col gap-2 text-sm">
            {files.map((file, i) => (
              <li key={`${file.name}-${i}`} className="flex items-center justify-between gap-3">
                <span className="min-w-0 break-all">{file.name}</span>
                <span className="flex shrink-0 items-center gap-2 text-neutral-600 dark:text-neutral-400">
                  {bytes(file.size)}
                  <button
                    aria-label={`Remove ${file.name}`}
                    onClick={() => setFiles(files.filter((_, j) => j !== i))}
                    className="rounded px-2 py-1 hover:bg-neutral-100 dark:hover:bg-neutral-800"
                  >
                    ✕
                  </button>
                </span>
              </li>
            ))}
          </ul>
          <Button className="mt-4 w-full sm:w-auto" disabled={busy} onClick={upload}>
            {busy ? "Uploading…" : `Upload ${files.length} file${files.length === 1 ? "" : "s"}`}
          </Button>
        </Card>
      )}

      {error && <ErrorBox message={error} />}
      {results && <UploadResults results={results} />}
    </>
  );
}

function UploadResults({ results }: { results: UploadResult[] }) {
  return (
    <Card>
      <h2 className="mb-3 font-medium">Uploaded</h2>
      <ul className="flex flex-col gap-3">
        {results.map((r) => (
          <li key={r.document_id}>
            <LiveStatus result={r} />
          </li>
        ))}
      </ul>
      <p className="mt-4 text-sm">
        <Link href="/documents" className="font-medium text-sky-700 hover:underline dark:text-sky-400">
          See all documents
        </Link>
      </p>
    </Card>
  );
}


function LiveStatus({ result }: { result: UploadResult }) {
  // Rejected files have no job; accepted ones are polled until they finish.
  const { data } = useApi<DocumentSummary>(result.job_id ? `/api/documents/${result.document_id}` : null, {
    pollMs: 2500,
    keepPolling: (doc) => doc.status === "queued" || doc.status === "processing",
  });
  const status = data?.status ?? result.status;
  const errorText = data?.error_code ? `${data.error_code}: ${data.error_message}` : result.error_code ? `${result.error_code}: ${result.error_message}` : null;
  return (
    <div className="flex flex-col gap-1 text-sm">
      <div className="flex items-center justify-between gap-3">
        <Link href={`/documents/${result.document_id}`} className="min-w-0 break-all text-sky-700 hover:underline dark:text-sky-400">
          {result.filename}
        </Link>
        <StatusBadge status={status} />
      </div>
      {errorText && <p className="text-red-700 dark:text-red-400">{errorText}</p>}
      {data?.status === "completed" && <p className="text-neutral-600 dark:text-neutral-400">{data.invoice_count} invoices found</p>}
    </div>
  );
}
