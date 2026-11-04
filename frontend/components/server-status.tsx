"use client";

import { useEffect, useState } from "react";

import { HEALTH_TIMEOUT_MS, fetchHealth, type HealthResult } from "@/lib/api";

/** One line: is the backend awake? It sleeps on the free plan and takes up to a minute to wake. */
export function ServerStatus() {
  const [state, setState] = useState<HealthResult | { kind: "checking" }>({ kind: "checking" });
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);
    const tick = setInterval(() => setSeconds((s) => s + 1), 1000);
    fetchHealth(controller.signal).then((result) => {
      setState(result);
      clearInterval(tick);
    });
    return () => {
      controller.abort();
      clearTimeout(timeout);
      clearInterval(tick);
    };
  }, []);
  const [dot, text] =
    state.kind === "checking"
      ? ["bg-sky-500 animate-pulse", seconds >= 5 ? `Waking the server (free plan), ${seconds}s. Sign in meanwhile.` : "Checking the server…"]
      : state.kind === "healthy"
        ? ["bg-emerald-500", "Server ready"]
        : state.kind === "degraded"
          ? ["bg-amber-500", "Server up, database unavailable"]
          : ["bg-red-500", state.reason];
  return (
    <p aria-live="polite" className="flex items-center gap-2 text-sm text-neutral-600 dark:text-neutral-400">
      <span className={`size-2.5 shrink-0 rounded-full ${dot}`} />
      {text}
    </p>
  );
}
