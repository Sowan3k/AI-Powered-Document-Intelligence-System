"use client";

import { useRef, useState, type DragEvent } from "react";

import { useActivity } from "@/components/activity";
import { UploadIcon } from "@/components/icons";
import { ErrorBox } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { UploadResponse } from "@/lib/types";

const ACCEPT = ".pdf,.jpg,.jpeg,.png,.tif,.tiff,.xlsx,.xls,.csv";

/** Pick or drop files and they upload at once: one step, no confirm button. */
export function DropZone() {
  const input = useRef<HTMLInputElement>(null);
  const { refresh } = useActivity();
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rejected, setRejected] = useState<UploadResponse["documents"]>([]);

  async function send(list: FileList | null) {
    if (!list || list.length === 0) return;
    const form = new FormData();
    for (const file of Array.from(list)) form.append("files", file);
    setBusy(list.length);
    setError(null);
    setRejected([]);
    try {
      const body = await api<UploadResponse>("/api/documents", { method: "POST", body: form });
      setRejected(body.documents.filter((d) => d.job_id === null));
      refresh(); // the dock picks the new files up at once
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed.");
    } finally {
      setBusy(null);
    }
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    send(event.dataTransfer.files);
  }

  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        onClick={() => input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        disabled={busy !== null}
        className={`flex w-full flex-col items-center gap-2 rounded-2xl border-2 border-dashed px-4 py-8 text-center transition ${dragging ? "border-sky-500 bg-sky-50 dark:bg-sky-950/30" : "border-sky-300 bg-white hover:border-sky-500 hover:bg-sky-50/50 dark:border-sky-800 dark:bg-neutral-900"}`}
      >
        <span className="grid size-12 place-items-center rounded-full bg-sky-600 text-white">
          <UploadIcon className="size-6" />
        </span>
        <span className="text-base font-semibold">{busy ? `Uploading ${busy} file${busy === 1 ? "" : "s"}…` : "Tap to add files"}</span>
        <span className="text-sm text-neutral-600 dark:text-neutral-400">
          or drop them here. Invoices, receipts, scans, Excel or CSV. Several at once is fine.
        </span>
      </button>
      <input
        ref={input}
        type="file"
        multiple
        accept={ACCEPT}
        className="sr-only"
        aria-label="Add files"
        onChange={(e) => {
          send(e.target.files);
          e.target.value = "";
        }}
      />
      {error && <ErrorBox message={error} />}
      {rejected.length > 0 && (
        <div className="relative">
          <ErrorBox
            message={`Not accepted: ${rejected.map((r) => `${r.filename} (${r.error_message ?? r.error_code})`).join("; ")}`}
          />
          <button
            onClick={() => setRejected([])}
            aria-label="Dismiss"
            className="absolute top-2 right-2 rounded px-2 text-red-800 hover:bg-red-100 dark:text-red-300 dark:hover:bg-red-900"
          >
            ✕
          </button>
        </div>
      )}
    </div>
  );
}
