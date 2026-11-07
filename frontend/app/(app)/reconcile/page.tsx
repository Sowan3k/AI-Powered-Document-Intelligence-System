"use client";

import { AnimatePresence, motion } from "motion/react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import { DocPicker } from "@/components/doc-picker";
import { CompareIcon } from "@/components/icons";
import { KindBadge } from "@/components/kind-badge";
import { ReconcileReport } from "@/components/reconcile-report";
import { Empty, ErrorBox, Loading, PageTitle } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { DocumentDetail, DocumentSummary, PairDocument, PairSuggestion, Page, Reconciliation } from "@/lib/types";
import { useApi } from "@/lib/use-api";

type Picked = Pick<PairDocument, "id" | "filename" | "source_kind" | "created_at"> & { invoice_count: number | null };
const spring = { type: "spring", stiffness: 380, damping: 32 } as const;

export default function ReconcilePage() {
  return (
    <Suspense>
      <Reconcile />
    </Suspense>
  );
}

function Reconcile() {
  const router = useRouter();
  const params = useSearchParams();
  const presetA = params.get("a");
  const presetB = params.get("b");
  const [a, setA] = useState<Picked | null>(null);
  const [b, setB] = useState<Picked | null>(null);
  const [picking, setPicking] = useState<"A" | "B" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<Reconciliation | null>(null);
  const started = useRef(false);
  const results = useRef<HTMLDivElement>(null);
  const suggestions = useApi<{ items: PairSuggestion[] }>("/api/reconcile/suggestions");
  const anyDocs = useApi<Page<DocumentSummary>>("/api/documents?status=completed&limit=2");

  async function compare(first: Picked, second: Picked) {
    // The URL below names both documents, and the effect that reads the URL would
    // compare them a second time: live, one tap saved two reports (D88).
    started.current = true;
    setBusy(true);
    setError(null);
    router.replace(`/reconcile?a=${first.id}&b=${second.id}`, { scroll: false });
    try {
      setReport(
        await api<Reconciliation>("/api/reconcile", {
          method: "POST",
          body: JSON.stringify({ document_a: first.id, document_b: second.id }),
        }),
      );
      requestAnimationFrame(() => results.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The comparison failed.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    // Two documents marked on Home arrive in the URL: fill both slots and compare at once.
    if (!presetA || !presetB || started.current) return;
    started.current = true;
    Promise.all([api<DocumentDetail>(`/api/documents/${presetA}`), api<DocumentDetail>(`/api/documents/${presetB}`)])
      .then(([da, db]) => {
        setA(da);
        setB(db);
        compare(da, db);
      })
      .catch(() => setError("One of the chosen documents could not be loaded."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presetA, presetB]);

  function choose(side: "A" | "B", doc: Picked) {
    (side === "A" ? setA : setB)(doc);
    setReport(null);
    setPicking(null);
  }

  function swap() {
    setA(b);
    setB(a);
    setReport(null);
  }

  const pairs = suggestions.data?.items ?? [];
  const tooFew = anyDocs.data !== null && anyDocs.data.total < 2;

  return (
    <>
      <PageTitle title="Compare" />
      <p className="-mt-3 text-sm text-muted">
        Check one document against another, for example a supplier statement against your Excel export. Invoices
        match by number first, then by supplier, date and total.
      </p>

      {anyDocs.error && <ErrorBox message={anyDocs.error} onRetry={anyDocs.reload} />}
      {anyDocs.loading && !anyDocs.data && <Loading slow={anyDocs.slow} />}
      {tooFew && <Empty>Process at least two documents first.</Empty>}

      {pairs.length > 0 && (
        <section className="flex flex-col gap-2">
          <h2 className="type-section">Suggested pairs</h2>
          <p className="-mt-1 text-xs text-muted">These documents share invoices. One tap compares them.</p>
          <div className="-mx-4 flex snap-x snap-mandatory gap-3 overflow-x-auto px-4 pb-1 [scrollbar-width:none]">
            {pairs.map((p, i) => (
              <motion.button
                key={`${p.document_a.id}-${p.document_b.id}`}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0, transition: { ...spring, delay: 0.05 * i } }}
                whileTap={{ scale: 0.97 }}
                onClick={() => {
                  setA(p.document_a);
                  setB(p.document_b);
                  compare(p.document_a, p.document_b);
                }}
                className="glass flex w-72 shrink-0 snap-start flex-col gap-2 rounded-3xl p-4 text-left"
              >
                <MiniDoc doc={p.document_a} tag="A" />
                <span className="flex items-center gap-2 pl-3 text-xs font-medium text-brass">
                  <span className="h-4 w-px bg-current opacity-40" />
                  {p.shared} shared invoice{p.shared === 1 ? "" : "s"}
                </span>
                <MiniDoc doc={p.document_b} tag="B" />
              </motion.button>
            ))}
          </div>
        </section>
      )}

      {!tooFew && anyDocs.data && (
        <section className="flex flex-col gap-3">
          <div className="relative flex flex-col gap-2 sm:flex-row sm:items-stretch">
            <Slot side="A" doc={a} onOpen={() => setPicking("A")} />
            <motion.button
              onClick={swap}
              disabled={!a && !b}
              whileTap={{ rotate: 180, scale: 0.9 }}
              transition={spring}
              aria-label="Swap A and B"
              className="glass z-10 mx-auto -my-5 grid size-11 shrink-0 place-items-center self-center rounded-full disabled:opacity-40 sm:mx-0 sm:-mx-5 sm:my-0"
            >
              <SwapIcon />
            </motion.button>
            <Slot side="B" doc={b} onOpen={() => setPicking("B")} />
          </div>
          <motion.button
            whileTap={{ scale: 0.98 }}
            disabled={!a || !b || busy}
            onClick={() => a && b && compare(a, b)}
            className="inline-flex min-h-12 items-center justify-center gap-2 rounded-2xl btn-primary px-4 font-semibold transition disabled:opacity-40 disabled:shadow-none"
          >
            {busy ? (
              <>
                <motion.span className="size-4 rounded-full border-2 border-white/40 border-t-white" animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 0.8, ease: "linear" }} />
                Comparing…
              </>
            ) : (
              <>
                <CompareIcon className="size-5" />
                {a && b ? "Compare" : "Choose two documents"}
              </>
            )}
          </motion.button>
        </section>
      )}

      {error && <ErrorBox message={error} />}
      <div ref={results} className="scroll-mt-20">
        <AnimatePresence mode="wait">{report && <ReconcileReport key={report.id} report={report} nameA={a?.filename} nameB={b?.filename} />}</AnimatePresence>
      </div>

      <DocPicker
        open={picking !== null}
        side={picking ?? "A"}
        selectedId={(picking === "B" ? b : a)?.id ?? null}
        otherId={(picking === "B" ? a : b)?.id ?? null}
        onPick={(doc) => picking && choose(picking, doc)}
        onClose={() => setPicking(null)}
      />
    </>
  );
}

function Slot({ side, doc, onOpen }: { side: "A" | "B"; doc: Picked | null; onOpen: () => void }) {
  return (
    <motion.button
      layout
      whileTap={{ scale: 0.98 }}
      onClick={onOpen}
      className={`surface flex min-h-20 flex-1 items-center gap-3 rounded-3xl p-4 text-left ${doc ? "" : "border-dashed"}`}
    >
      <span className="grid size-7 shrink-0 place-items-center rounded-full bg-foreground text-xs font-bold text-background">{side}</span>
      <AnimatePresence mode="popLayout" initial={false}>
        {doc ? (
          <motion.span key={doc.id} initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -10 }} transition={spring} className="flex min-w-0 flex-1 items-center gap-3">
            <KindBadge kind={doc.source_kind} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">{doc.filename}</span>
              <span className="block text-xs text-muted">
                {doc.invoice_count !== null ? `${doc.invoice_count} invoice${doc.invoice_count === 1 ? "" : "s"} · ` : ""}
                {shortWhen(doc.created_at)}
              </span>
            </span>
            <span className="link text-xs">Change</span>
          </motion.span>
        ) : (
          <motion.span key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex-1 text-sm text-muted">
            Choose document {side}
          </motion.span>
        )}
      </AnimatePresence>
    </motion.button>
  );
}

function MiniDoc({ doc, tag }: { doc: PairDocument; tag: string }) {
  return (
    <span className="flex items-center gap-2.5">
      <KindBadge kind={doc.source_kind} className="size-8" />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium">{doc.filename}</span>
        <span className="block text-2xs text-muted">
          {tag} · {doc.invoice_count} invoice{doc.invoice_count === 1 ? "" : "s"}
        </span>
      </span>
    </span>
  );
}

function SwapIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-5 fill-none stroke-current stroke-2 [stroke-linecap:round] [stroke-linejoin:round] sm:rotate-90" aria-hidden>
      <path d="M7 4v16M7 4L4 7M7 4l3 3" />
      <path d="M17 20V4M17 20l-3-3M17 20l3-3" />
    </svg>
  );
}

function shortWhen(value: string): string {
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}
