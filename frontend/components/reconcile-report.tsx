"use client";

import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";

import { CountUp } from "@/components/count-up";
import { AlertIcon, CheckIcon } from "@/components/icons";
import { dateText, decimalChange, label, money } from "@/lib/format";
import type { ReconcileResult, ReconcileSide, Reconciliation } from "@/lib/types";

const spring = { type: "spring", stiffness: 380, damping: 32 } as const;

type Kind = "mismatched" | "only_in_a" | "only_in_b" | "matched";
type Diff = ReconcileResult["mismatched"][number]["differences"][number];
type Row = { key: string; kind: Kind; a: ReconcileSide | null; b: ReconcileSide | null; on: string | null; diffs: Diff[] };

/** Problems first: what a person must look at comes before what agrees. */
const KINDS: { kind: Kind; label: string; dot: string; tile: string; bar: string }[] = [
  { kind: "mismatched", label: "Mismatched", dot: "bg-rose-500", tile: "text-rose-700 dark:text-rose-300", bar: "bg-rose-500" },
  { kind: "only_in_a", label: "Only in A", dot: "bg-amber-500", tile: "text-amber-700 dark:text-amber-300", bar: "bg-amber-400" },
  { kind: "only_in_b", label: "Only in B", dot: "bg-slate-500", tile: "text-slate-700 dark:text-slate-300", bar: "bg-slate-400" },
  { kind: "matched", label: "Matched", dot: "bg-emerald-500", tile: "text-emerald-700 dark:text-emerald-300", bar: "bg-emerald-500" },
];

function rows(r: ReconcileResult): Row[] {
  return [
    ...r.mismatched.map((m, i) => ({ key: `x${i}`, kind: "mismatched" as const, a: m.a, b: m.b, on: m.matched_on, diffs: m.differences })),
    ...r.only_in_a.map((s) => ({ key: `a${s.invoice_id}`, kind: "only_in_a" as const, a: s, b: null, on: null, diffs: [] })),
    ...r.only_in_b.map((s) => ({ key: `b${s.invoice_id}`, kind: "only_in_b" as const, a: null, b: s, on: null, diffs: [] })),
    ...r.matched.map((m, i) => ({ key: `m${i}`, kind: "matched" as const, a: m.a, b: m.b, on: m.matched_on, diffs: [] })),
  ];
}

/**
 * The comparison as one list, like a bank statement (D79): a bar shows the
 * share of each outcome, the four counts filter the list, and each invoice is
 * one line. A mismatched pair opens to show A and B side by side, with the
 * fields that differ and by how much.
 */
export function ReconcileReport({ report, nameA, nameB }: { report: Reconciliation; nameA?: string; nameB?: string }) {
  const r = report.result;
  const s = r.summary;
  const [filter, setFilter] = useState<Kind | null>(null);
  const all = rows(r);
  const shown = filter ? all.filter((x) => x.kind === filter) : all;
  const total = s.matched + s.mismatched + s.only_in_a + s.only_in_b;
  const pairs = s.matched + s.mismatched;

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, y: -8 }} className="flex flex-col gap-3">
      <motion.section initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0, transition: spring }} className="surface flex flex-col gap-4 rounded-3xl p-4">
        <div className="flex flex-col gap-1.5 text-sm">
          <Doc tag="A" name={nameA} count={s.invoices_a} />
          <Doc tag="B" name={nameB} count={s.invoices_b} />
        </div>

        <div>
          <p className="type-section">
            {pairs === 0
              ? "No invoice appears in both."
              : `${pairs} ${pairs === 1 ? "pair" : "pairs"} found, ${s.matched} agree on every field.`}
          </p>
          {/* The share of each outcome, in the same order as the list. */}
          <div className="mt-3 flex h-2.5 overflow-hidden rounded-full bg-black/5 dark:bg-white/10" role="img" aria-label={KINDS.map((k) => `${k.label}: ${s[k.kind]}`).join(", ")}>
            {total > 0 &&
              KINDS.map((k, i) =>
                s[k.kind] > 0 ? (
                  <motion.span
                    key={k.kind}
                    className={`h-full ${k.bar} ${i > 0 ? "border-l-2 border-[var(--background)]" : ""}`}
                    initial={{ width: 0 }}
                    animate={{ width: `${(100 * s[k.kind]) / total}%` }}
                    transition={{ ...spring, delay: 0.1 + 0.08 * i }}
                  />
                ) : null,
              )}
          </div>
        </div>

        {/* The counts are also the filter: tap one to see only those, tap again for all. */}
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {KINDS.map((k) => {
            const on = filter === k.kind;
            return (
              <button
                key={k.kind}
                type="button"
                aria-pressed={on}
                disabled={s[k.kind] === 0}
                onClick={() => setFilter(on ? null : k.kind)}
                className={`relative rounded-2xl px-3 py-2.5 text-left transition disabled:opacity-40 ${on ? "bg-black/[0.06] ring-2 ring-current dark:bg-white/10" : "bg-black/[0.03] hover:bg-black/[0.06] dark:bg-white/[0.04] dark:hover:bg-white/[0.08]"} ${k.tile}`}
              >
                <span className="flex items-center gap-1.5 text-xs font-medium opacity-90">
                  <span className={`size-2 rounded-full ${k.dot}`} aria-hidden />
                  {k.label}
                </span>
                <span className="type-figure mt-0.5 block text-3xl">
                  <CountUp value={s[k.kind]} />
                </span>
              </button>
            );
          })}
        </div>
      </motion.section>

      <motion.ul layout className="surface flex flex-col overflow-hidden rounded-3xl" aria-label="Invoices compared">
        <AnimatePresence initial={false} mode="popLayout">
          {shown.map((row, i) => (
            <motion.li
              key={row.key}
              layout
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0, transition: { ...spring, delay: Math.min(i, 12) * 0.025 } }}
              exit={{ opacity: 0, transition: { duration: 0.15 } }}
              className="border-b border-[var(--surface-border)] last:border-b-0"
            >
              <Line row={row} />
            </motion.li>
          ))}
        </AnimatePresence>
        {shown.length === 0 && <li className="px-4 py-6 text-center text-sm text-muted">Nothing here.</li>}
      </motion.ul>
    </motion.div>
  );
}

function Doc({ tag, name, count }: { tag: "A" | "B"; name?: string; count: number }) {
  return (
    <span className="flex min-w-0 items-center gap-2">
      <span className="grid size-6 shrink-0 place-items-center rounded-lg bg-foreground text-xs font-bold text-background">{tag}</span>
      <span className="min-w-0 truncate font-medium">{name ?? `Document ${tag}`}</span>
      <span className="shrink-0 text-muted">
        {count} {count === 1 ? "invoice" : "invoices"}
      </span>
    </span>
  );
}

const MARKS: Record<Kind, { icon: React.ReactNode; tone: string }> = {
  matched: { icon: <CheckIcon className="size-3.5" />, tone: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400" },
  mismatched: { icon: <AlertIcon className="size-3.5" />, tone: "bg-rose-500/15 text-rose-600 dark:text-rose-400" },
  only_in_a: { icon: <span className="text-2xs font-bold">A</span>, tone: "bg-amber-500/15 text-amber-700 dark:text-amber-300" },
  only_in_b: { icon: <span className="text-2xs font-bold">B</span>, tone: "bg-slate-500/15 text-slate-700 dark:text-slate-300" },
};

/** One invoice: its number and total, the supplier, then the date and where it was found. */
function Line({ row }: { row: Row }) {
  const main = row.a ?? row.b;
  if (!main) return null;
  const mark = MARKS[row.kind];
  const where =
    row.kind === "only_in_a"
      ? `A ${row.a?.where} · not found in B`
      : row.kind === "only_in_b"
        ? `B ${row.b?.where} · not found in A`
        : `A ${row.a?.where} ↔ B ${row.b?.where} · ${row.on === "invoice_number" ? "same number" : "same supplier, date and total"}`;
  return (
    <div className="px-4 py-3">
      <div className="flex items-start gap-3">
        <span className={`mt-0.5 grid size-6 shrink-0 place-items-center rounded-full ${mark.tone}`} aria-label={KINDS.find((k) => k.kind === row.kind)?.label}>
          {mark.icon}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-3">
            <p className="min-w-0 truncate font-mono text-sm font-medium">{main.invoice_number ?? "no number"}</p>
            <p className="shrink-0 text-sm font-semibold tabular-nums">{money(main.total)}</p>
          </div>
          <p className="text-sm">{main.supplier_name ?? "unknown supplier"}</p>
          <p className="mt-0.5 text-xs text-muted">
            {dateText(main.invoice_date)} · {where}
          </p>
          {row.kind === "mismatched" && <Differences row={row} />}
        </div>
      </div>
    </div>
  );
}

/** A mismatched pair: each differing field with A's value, B's value, and the change for amounts. */
function Differences({ row }: { row: Row }) {
  return (
    <div className="mt-2.5 overflow-hidden rounded-2xl border border-rose-500/20 bg-rose-500/[0.04] text-sm">
      <div className="grid grid-cols-[minmax(5rem,auto)_1fr_1fr] gap-x-3 border-b border-rose-500/15 px-3 py-1.5 type-eyebrow text-muted">
        <span>Field</span>
        <span>A</span>
        <span>B</span>
      </div>
      {row.diffs.map((d) => {
        const change = decimalChange(d.a, d.b);
        return (
          <div key={d.field} className="grid grid-cols-[minmax(5rem,auto)_1fr_1fr] items-baseline gap-x-3 border-b border-rose-500/10 px-3 py-2 last:border-b-0">
            <span className="text-xs font-medium text-muted">{label(d.field)}</span>
            <span className="min-w-0 break-words tabular-nums">{show(d.field, d.a)}</span>
            <span className="min-w-0 break-words font-semibold text-rose-600 tabular-nums dark:text-rose-400">
              {show(d.field, d.b)}
              {change && <span className="ml-1.5 text-xs font-medium whitespace-nowrap opacity-80">({change})</span>}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function show(field: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "empty";
  if (field === "invoice_date" && typeof value === "string") return dateText(value);
  if (["subtotal", "tax", "total"].includes(field) && typeof value === "string") return money(value);
  return String(value);
}
