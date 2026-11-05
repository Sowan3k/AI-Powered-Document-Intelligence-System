"use client";

import { motion } from "motion/react";
import { useEffect, useState } from "react";

import { CheckIcon, SearchIcon } from "@/components/icons";
import { KindBadge, type Kind } from "@/components/kind-badge";
import { Sheet } from "@/components/sheet";
import { query } from "@/lib/api";
import { dateText } from "@/lib/format";
import type { DocumentSummary, Page } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const FILTERS: { kind: Kind | null; label: string }[] = [
  { kind: null, label: "All" },
  { kind: "pdf", label: "PDF" },
  { kind: "spreadsheet", label: "Excel" },
  { kind: "csv", label: "CSV" },
  { kind: "image", label: "Photos" },
];

/**
 * Choose one document out of many: type to search by name, or tap a type.
 * The search runs on the server, so it works with any number of documents.
 */
export function DocPicker({
  open,
  side,
  selectedId,
  otherId,
  onPick,
  onClose,
}: {
  open: boolean;
  side: "A" | "B";
  selectedId: string | null;
  otherId: string | null;
  onPick: (doc: DocumentSummary) => void;
  onClose: () => void;
}) {
  const [text, setText] = useState("");
  const [needle, setNeedle] = useState("");
  const [kind, setKind] = useState<Kind | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setNeedle(text.trim()), 200);
    return () => clearTimeout(t);
  }, [text]);

  const docs = useApi<Page<DocumentSummary>>(
    open ? `/api/documents${query({ status: "completed", limit: 50, q: needle, kind })}` : null,
  );
  const items = docs.data?.items ?? [];

  return (
    <Sheet open={open} onClose={onClose} title={`Choose document ${side}`}>
      <div className="flex flex-col gap-3 px-5 pb-3">
        <label className="relative block">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted" />
          <input
            autoFocus
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Search by file name"
            aria-label="Search documents by file name"
            className="min-h-11 w-full rounded-xl border border-black/10 bg-white/70 pr-3 pl-9 text-base outline-none focus:border-foreground/40 focus:ring-4 focus:ring-foreground/10 dark:border-white/12 dark:bg-white/5"
          />
        </label>
        <div className="-mx-5 flex gap-1.5 overflow-x-auto px-5 [scrollbar-width:none]" role="group" aria-label="Filter by file type">
          {FILTERS.map((f) => {
            const on = kind === f.kind;
            return (
              <button
                key={f.label}
                onClick={() => setKind(f.kind)}
                aria-pressed={on}
                className={`relative shrink-0 rounded-full px-3.5 py-1.5 text-sm transition-colors ${on ? "font-medium text-foreground" : "text-muted"}`}
              >
                {on && <motion.span layoutId="picker-filter" className="glass-lens absolute inset-0 rounded-full" transition={{ type: "spring", stiffness: 420, damping: 34 }} />}
                <span className="relative">{f.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      <ul className="min-h-40 flex-1 overflow-y-auto px-3 pb-4">
        {docs.loading && !docs.data && <li className="px-2 py-6 text-center text-sm text-muted">Loading documents…</li>}
        {docs.error && <li className="px-2 py-6 text-center text-sm text-rose-600">{docs.error}</li>}
        {docs.data && items.length === 0 && (
          <li className="px-2 py-6 text-center text-sm text-muted">No processed document matches. Only completed documents can be compared.</li>
        )}
        {items.map((d, i) => {
          const taken = d.id === otherId;
          const chosen = d.id === selectedId;
          return (
            <motion.li
              key={d.id}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0, transition: { delay: Math.min(i, 10) * 0.02 } }}
            >
              <button
                disabled={taken}
                onClick={() => onPick(d)}
                className={`flex w-full items-center gap-3 rounded-2xl px-2 py-2.5 text-left transition-colors ${chosen ? "bg-foreground/[0.06]" : "hover:bg-black/5 dark:hover:bg-white/5"} disabled:opacity-40`}
              >
                <KindBadge kind={d.source_kind} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">
                    <Highlight text={d.filename} needle={needle} />
                  </span>
                  <span className="block text-xs text-muted">
                    {d.invoice_count ?? 0} invoice{d.invoice_count === 1 ? "" : "s"} · {dateText(d.created_at)}
                    {taken && ` · chosen as ${side === "A" ? "B" : "A"}`}
                  </span>
                </span>
                {chosen && <CheckIcon className="size-5 text-foreground" />}
              </button>
            </motion.li>
          );
        })}
        {docs.data && docs.data.total > items.length && (
          <li className="px-2 pt-2 text-center text-xs text-muted">
            Showing {items.length} of {docs.data.total}. Type part of the name to narrow it down.
          </li>
        )}
      </ul>
    </Sheet>
  );
}

/** The part of the name that matches the search, in bold. */
function Highlight({ text, needle }: { text: string; needle: string }) {
  if (!needle) return <>{text}</>;
  const at = text.toLowerCase().indexOf(needle.toLowerCase());
  if (at === -1) return <>{text}</>;
  return (
    <>
      {text.slice(0, at)}
      <mark className="rounded bg-brass/30 px-0.5 text-inherit">{text.slice(at, at + needle.length)}</mark>
      {text.slice(at + needle.length)}
    </>
  );
}
