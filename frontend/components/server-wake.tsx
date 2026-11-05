"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";

import { CheckIcon } from "@/components/icons";
import { HEALTH_TIMEOUT_MS, fetchHealth, type HealthResult } from "@/lib/api";

type StepState = "waiting" | "working" | "done" | "error";
export type Wake = {
  ready: boolean;
  seconds: number;
  steps: { label: string; state: StepState }[];
  line: string;
  short: string;
};

// One wake-up per tab. The landing page starts it; the sign-in page picks it
// up where it was, so the seconds do not restart and a ready server stays ready.
let startedAt = 0;
let lastHealthy: HealthResult | null = null;

/**
 * The free server sleeps when idle, so the first visitor usually waits for it.
 * This polls the real health check and describes the wait step by step
 * (server, database, file storage), with the seconds counting (D73, D74).
 */
export function useServerWake(): Wake {
  const [health, setHealth] = useState<HealthResult | null>(() => lastHealthy);
  const [seconds, setSeconds] = useState(0);
  const ready = health?.kind === "healthy";

  useEffect(() => {
    if (!startedAt) startedAt = Date.now();
    if (ready) return;
    const tick = setInterval(() => setSeconds(Math.round((Date.now() - startedAt) / 1000)), 1000);
    return () => clearInterval(tick);
  }, [ready]);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let tries = 0;
    let controller = new AbortController();
    const check = async () => {
      controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);
      const result = await fetchHealth(controller.signal);
      clearTimeout(timeout);
      if (cancelled) return;
      if (result.kind === "healthy") lastHealthy = result;
      setHealth(result);
      tries += 1;
      // A sleeping server answers once it is up; a part that is down gets a few more looks.
      if (result.kind !== "healthy" && tries < 30) timer = setTimeout(check, 4000);
    };
    check();
    return () => {
      cancelled = true;
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, []);

  const body = health && health.kind !== "unreachable" ? health.body : null;
  const lost = health?.kind === "unreachable" && seconds > 85;
  const server: StepState = body ? "done" : lost ? "error" : "working";
  const database: StepState = !body ? "waiting" : body.database === "connected" ? "done" : "error";
  const storage: StepState = !body ? "waiting" : body.storage === "error" ? "error" : "done";

  const line = ready
    ? "Ready. Everything is connected."
    : body
      ? `${database === "error" ? "The database" : "File storage"} is not answering yet. Checking again.`
      : lost && health?.kind === "unreachable"
        ? health.reason
        : seconds < 4
          ? "Checking the server…"
          : `Waking the free server · ${seconds} s. Usually under a minute. You can sign in now.`;
  const short = ready ? "Server ready" : body ? "Almost ready" : lost ? "Server not answering" : seconds < 4 ? "Checking the server" : `Waking the server · ${seconds} s`;

  return {
    ready,
    seconds,
    line,
    short,
    steps: [
      { label: "Server", state: server },
      { label: "Database", state: database },
      { label: "File storage", state: storage },
    ],
  };
}

/** Three steps with lines that fill as each part answers. */
export function WakeTimeline({ wake }: { wake: Wake }) {
  const { steps } = wake;
  return (
    <div aria-live="polite" className="flex flex-col gap-2.5">
      <div className="flex items-center">
        {steps.map((step, i) => (
          <div key={step.label} className={`flex items-center ${i < steps.length - 1 ? "flex-1" : ""}`}>
            <Node state={step.state} />
            {i < steps.length - 1 && (
              <span className="relative mx-1.5 h-0.5 flex-1 overflow-hidden rounded-full bg-black/10 dark:bg-white/10">
                <motion.span
                  className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-sky-400 to-violet-400"
                  initial={{ width: "0%" }}
                  animate={{ width: step.state === "done" ? "100%" : "0%" }}
                  transition={{ duration: 0.5, ease: "easeOut", delay: 0.15 * i }}
                />
              </span>
            )}
          </div>
        ))}
      </div>
      <div className="flex justify-between text-[11px] font-medium">
        {steps.map((step, i) => (
          <span key={step.label} className={`${i === 0 ? "text-left" : i === steps.length - 1 ? "text-right" : "text-center"} ${step.state === "waiting" ? "text-muted" : ""}`}>
            {step.label}
          </span>
        ))}
      </div>
      <p className={`text-xs ${wake.ready ? "text-emerald-600 dark:text-emerald-400" : "text-muted"}`}>{wake.line}</p>
    </div>
  );
}

/**
 * A small floating pill at the top of the screen, like the iPhone's Dynamic
 * Island: the wake-up stays in view however far the visitor scrolls, then
 * tucks itself away a moment after the server is ready.
 */
export function WakeIsland({ wake }: { wake: Wake }) {
  const [gone, setGone] = useState(false);
  useEffect(() => {
    if (!wake.ready) return;
    const t = setTimeout(() => setGone(true), 2600);
    return () => clearTimeout(t);
  }, [wake.ready]);

  return (
    <div className="pointer-events-none fixed inset-x-0 top-[max(0.75rem,env(safe-area-inset-top))] z-40 flex justify-center px-4">
      <AnimatePresence>
        {!gone && (
          <motion.div
            layout
            initial={{ opacity: 0, y: -16, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -16, scale: 0.9, transition: { duration: 0.25 } }}
            transition={{ type: "spring", stiffness: 420, damping: 32 }}
            className="glass-strong pointer-events-auto flex items-center gap-2.5 rounded-full py-2 pr-4 pl-2 text-sm font-medium"
            role="status"
          >
            <span className="relative grid size-6 place-items-center">
              {wake.ready ? (
                <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} className="grid size-6 place-items-center rounded-full bg-emerald-500 text-white">
                  <CheckIcon className="size-3.5" />
                </motion.span>
              ) : (
                <motion.span
                  className="size-5 rounded-full border-2 border-sky-400/30 border-t-sky-400"
                  animate={{ rotate: 360 }}
                  transition={{ repeat: Infinity, duration: 0.9, ease: "linear" }}
                />
              )}
            </span>
            <motion.span layout="position" className="tabular-nums">
              {wake.short}
            </motion.span>
            <span className="flex gap-1" aria-hidden>
              {wake.steps.map((s) => (
                <span
                  key={s.label}
                  className={`size-1.5 rounded-full transition-colors duration-500 ${s.state === "done" ? "bg-emerald-400" : s.state === "error" ? "bg-rose-400" : s.state === "working" ? "animate-pulse bg-sky-400" : "bg-black/20 dark:bg-white/20"}`}
                />
              ))}
            </span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Node({ state }: { state: StepState }) {
  return (
    <span className="relative grid size-7 shrink-0 place-items-center">
      {state === "working" && (
        <motion.span
          className="absolute inset-0 rounded-full border-2 border-sky-400/30 border-t-sky-400"
          animate={{ rotate: 360 }}
          transition={{ repeat: Infinity, duration: 0.9, ease: "linear" }}
        />
      )}
      <motion.span
        initial={false}
        animate={{ scale: state === "done" || state === "error" ? 1 : 0.55 }}
        transition={{ type: "spring", stiffness: 500, damping: 24 }}
        className={`grid size-7 place-items-center rounded-full text-white ${
          state === "done"
            ? "bg-emerald-500 shadow-[0_0_14px_rgb(16_185_129/0.55)]"
            : state === "error"
              ? "bg-rose-500"
              : state === "working"
                ? "bg-sky-500/80"
                : "bg-black/15 dark:bg-white/15"
        }`}
      >
        {state === "done" && <CheckIcon className="size-4" />}
        {state === "error" && <span className="text-xs font-bold">!</span>}
      </motion.span>
    </span>
  );
}
