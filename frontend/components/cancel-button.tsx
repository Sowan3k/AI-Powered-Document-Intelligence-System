"use client";

import { useState } from "react";

import { api, ApiError } from "@/lib/api";

/** Stop a file that is queued or being processed (D86). Nothing read so far is kept. */
export function CancelButton({
  documentId,
  filename,
  onDone,
  className = "",
}: {
  documentId: string;
  filename: string;
  onDone: () => void;
  className?: string;
}) {
  const [busy, setBusy] = useState(false);

  async function cancel() {
    if (!window.confirm(`Stop processing ${filename}? Nothing read so far is kept. You can process it again later.`)) return;
    setBusy(true);
    try {
      await api(`/api/documents/${documentId}/cancel`, { method: "POST" });
      onDone();
    } catch (err) {
      window.alert(err instanceof ApiError ? err.message : "It could not be cancelled. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      onClick={cancel}
      disabled={busy}
      className={`min-h-9 shrink-0 rounded-lg px-3 text-sm font-medium text-red-700 transition hover:bg-red-500/10 disabled:opacity-50 dark:text-red-400 ${className}`}
    >
      {busy ? "Cancelling…" : "Cancel"}
    </button>
  );
}
