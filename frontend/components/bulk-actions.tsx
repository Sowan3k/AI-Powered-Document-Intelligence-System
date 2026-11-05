"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ExportButton } from "@/components/export-button";
import { Button } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { DocumentSummary, Page } from "@/lib/types";

const ACTIVE = new Set(["queued", "processing"]);

async function each(ids: string[], call: (id: string) => Promise<unknown>) {
  let ok = 0;
  const errors: string[] = [];
  for (const id of ids) {
    try {
      await call(id);
      ok += 1;
    } catch (e) {
      errors.push(e instanceof ApiError ? e.message : "failed");
    }
  }
  return { ok, errors };
}

function summary(verb: string, total: number, result: { ok: number; errors: string[] }): string {
  const skipped = total - result.ok;
  const reason = result.errors[0] ? ` (${result.errors[0]})` : "";
  return `${verb} ${result.ok} of ${total}.${skipped ? ` ${skipped} skipped${reason}.` : ""}`;
}

/** Actions on the documents marked in the list (D66). */
export function BulkActions({
  marked,
  docs,
  onDone,
}: {
  marked: string[];
  docs: DocumentSummary[];
  onDone: (message: string) => void;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const byId = new Map(docs.map((d) => [d.id, d]));
  const chosen = marked.map((id) => byId.get(id)).filter((d): d is DocumentSummary => !!d);
  const idle = chosen.filter((d) => !ACTIVE.has(d.status));
  const comparable = chosen.length === 2 && chosen.every((d) => d.status === "completed");

  async function run(work: () => Promise<string>) {
    setBusy(true);
    try {
      onDone(await work());
    } finally {
      setBusy(false);
    }
  }

  return (
    <div role="region" aria-label="Actions on marked documents" className="flex flex-col gap-2 rounded-xl border border-sky-200 bg-sky-50 p-3 dark:border-sky-900 dark:bg-sky-950/40">
      <p className="text-sm font-medium">{marked.length} marked</p>
      <div className="flex flex-wrap gap-2">
        <Button
          disabled={busy || idle.length === 0}
          onClick={() =>
            run(async () =>
              summary("Queued again", idle.length, await each(idle.map((d) => d.id), (id) => api(`/api/documents/${id}/reprocess`, { method: "POST" }))),
            )
          }
        >
          Process again
        </Button>
        <ExportButton documentIds={marked} label="Download marked for Excel" />
        {comparable && (
          <Button variant="secondary" disabled={busy} onClick={() => router.push(`/reconcile?a=${chosen[0].id}&b=${chosen[1].id}`)}>
            Compare these two
          </Button>
        )}
        <Button
          variant="ghost"
          className="text-red-700 dark:text-red-400"
          disabled={busy || idle.length === 0}
          onClick={() => {
            if (!window.confirm(`Delete ${idle.length} file${idle.length === 1 ? "" : "s"} and everything extracted from them? This cannot be undone.`)) return;
            run(async () =>
              summary("Deleted", idle.length, await each(idle.map((d) => d.id), (id) => api(`/api/documents/${id}`, { method: "DELETE" }))),
            );
          }}
        >
          Delete
        </Button>
      </div>
    </div>
  );
}

/** One tap to queue every failed document again. */
export function RetryAllFailed({ onDone }: { onDone: (message: string) => void }) {
  const [busy, setBusy] = useState(false);
  return (
    <Button
      variant="secondary"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          const failed = await api<Page<DocumentSummary>>("/api/documents?status=failed&limit=100");
          const ids = failed.items.map((d) => d.id);
          onDone(summary("Queued again", ids.length, await each(ids, (id) => api(`/api/documents/${id}/reprocess`, { method: "POST" }))));
        } catch (e) {
          onDone(e instanceof ApiError ? e.message : "That did not work.");
        } finally {
          setBusy(false);
        }
      }}
    >
      {busy ? "Queuing…" : "Retry all failed"}
    </Button>
  );
}
