"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useState } from "react";

import { AlertIcon, SparkIcon } from "@/components/icons";

// One invoice, read and checked, on a loop. The same story as the planted
// wrong-total invoice in the test set: the model reads, Python adds up.
const STEPS = 5; // 0 idle, 1 number, 2 supplier, 3 totals, 4 the check
const BEAT_MS = 1300;

const chips = [
  { at: 1, label: "Invoice no.", value: "INV-2026-00004", conf: "98%" },
  { at: 2, label: "Supplier", value: "Blue River Stationers", conf: "97%" },
  { at: 3, label: "Total", value: "428.75 GBP", conf: "99%" },
];

export function ScanPreview() {
  const reduce = useReducedMotion();
  const [step, setStep] = useState(reduce ? 4 : 0);

  useEffect(() => {
    if (reduce) return;
    const timer = setInterval(() => setStep((s) => (s + 1) % (STEPS + 1)), BEAT_MS);
    return () => clearInterval(timer);
  }, [reduce]);
  const shown = reduce ? 4 : Math.min(step, 4);

  return (
    <div className="flex flex-col gap-3" aria-label="Preview: an invoice being read and checked">
      <div className="glass relative overflow-hidden rounded-3xl p-5">
        {!reduce && (
          <span className="scan-beam pointer-events-none absolute inset-x-0 top-0 h-16 bg-gradient-to-b from-transparent via-brass/25 to-transparent" />
        )}
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="type-eyebrow text-muted">INVOICE</p>
            <Field on={shown >= 1} className="mt-1 text-sm font-semibold">
              INV-2026-00004
            </Field>
          </div>
          <div className="text-right text-2xs text-muted">
            <p>20 Apr 2026</p>
            <p>GBP</p>
          </div>
        </div>
        <Field on={shown >= 2} className="mt-3 text-xs font-medium">
          Blue River Stationers
        </Field>
        <div className="mt-4 flex flex-col gap-1.5" aria-hidden>
          {[78, 64, 70].map((w, i) => (
            <div key={i} className="flex items-center justify-between gap-3">
              <span className="h-1.5 rounded-full bg-black/10 dark:bg-white/12" style={{ width: `${w}%` }} />
              <span className="h-1.5 w-10 rounded-full bg-black/10 dark:bg-white/12" />
            </div>
          ))}
        </div>
        <div className="mt-4 ml-auto flex w-40 flex-col gap-0.5 text-2xs">
          <Row label="Subtotal" value="390.00" on={shown >= 3} />
          <Row label="Tax" value="28.75" on={shown >= 3} />
          <Row label="Total" value="428.75" on={shown >= 3} strong />
        </div>
      </div>

      <div className="relative flex flex-col gap-1.5">
        {/* Faint slots, so the list never leaves a hole while it refills. */}
        <div className="pointer-events-none absolute inset-0 flex flex-col gap-1.5" aria-hidden>
          {[0, 1, 2, 3].map((i) => (
            <span key={i} className="h-[1.85rem] rounded-2xl border border-dashed border-black/10 dark:border-white/10" />
          ))}
        </div>
        <div className="min-h-[7.85rem]" aria-hidden />
        <div className="absolute inset-x-0 top-0 flex flex-col gap-1.5">
        <AnimatePresence mode="popLayout">
          {chips
            .filter((c) => shown >= c.at)
            .map((c) => (
              <motion.div
                key={c.label}
                layout
                initial={{ opacity: 0, y: 8, scale: 0.96 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, scale: 0.96, transition: { duration: 0.15 } }}
                transition={{ type: "spring", stiffness: 420, damping: 30 }}
                className="glass flex h-[1.85rem] items-center gap-2 rounded-2xl px-3 text-xs"
              >
                <SparkIcon className="size-3.5 text-brass" />
                <span className="text-muted">{c.label}</span>
                <span className="min-w-0 flex-1 truncate font-medium">{c.value}</span>
                <span className="text-2xs text-emerald-600 dark:text-emerald-400">{c.conf}</span>
              </motion.div>
            ))}
          {shown >= 4 && (
            <motion.div
              key="check"
              layout
              initial={{ opacity: 0, y: 8, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, scale: 0.96, transition: { duration: 0.15 } }}
              transition={{ type: "spring", stiffness: 420, damping: 30 }}
              className="flex h-[1.85rem] items-center gap-2 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-3 text-xs text-rose-700 dark:text-rose-300"
            >
              <AlertIcon className="size-3.5" />
              <span className="min-w-0 flex-1 truncate">Python: 390.00 + 28.75 = 418.75, not 428.75</span>
              <span className="shrink-0 font-medium">Review</span>
            </motion.div>
          )}
        </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

function Field({ on, className, children }: { on: boolean; className?: string; children: string }) {
  return (
    <motion.span
      animate={{
        backgroundColor: on ? "rgba(201, 150, 63, 0.18)" : "rgba(201, 150, 63, 0)",
        boxShadow: on ? "0 0 0 1px rgba(201, 150, 63, 0.55)" : "0 0 0 1px rgba(201, 150, 63, 0)",
      }}
      transition={{ duration: 0.35 }}
      className={`-mx-1 inline-block rounded-md px-1 ${className ?? ""}`}
    >
      {children}
    </motion.span>
  );
}

function Row({ label, value, on, strong }: { label: string; value: string; on: boolean; strong?: boolean }) {
  return (
    <motion.div
      animate={{ backgroundColor: on ? "rgba(201, 150, 63, 0.14)" : "rgba(201, 150, 63, 0)" }}
      transition={{ duration: 0.35 }}
      className={`flex justify-between rounded-md px-1.5 py-0.5 ${strong ? "font-semibold" : "text-muted"}`}
    >
      <span>{label}</span>
      <span className="tabular-nums">{value}</span>
    </motion.div>
  );
}
