"use client";

import { useState } from "react";

import { useActivity } from "@/components/activity";
import { CheckIcon } from "@/components/icons";
import { api, ApiError } from "@/lib/api";
import type { InvoiceDetail } from "@/lib/types";

/** One tap: a person confirms the invoice as it is (no fields change). */
export function ApproveButton({
  invoiceId,
  onDone,
  label = "Approve",
}: {
  invoiceId: string;
  onDone: (saved: InvoiceDetail) => void;
  label?: string;
}) {
  const { refresh } = useActivity();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <span className="flex flex-col">
      <button
        disabled={busy}
        onClick={async (e) => {
          e.preventDefault();
          e.stopPropagation();
          setBusy(true);
          setError(null);
          try {
            const saved = await api<InvoiceDetail>(`/api/invoices/${invoiceId}`, {
              method: "PATCH",
              body: JSON.stringify({ mark_reviewed: true }),
            });
            onDone(saved);
            refresh();
          } catch (err) {
            setError(err instanceof ApiError ? err.message : "Could not approve.");
          } finally {
            setBusy(false);
          }
        }}
        className="inline-flex min-h-10 w-full items-center justify-center gap-1.5 rounded-lg bg-emerald-600 px-4 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
      >
        <CheckIcon className="size-4" />
        {busy ? "Saving…" : label}
      </button>
      {error && <span className="mt-1 text-xs text-red-700 dark:text-red-400">{error}</span>}
    </span>
  );
}
