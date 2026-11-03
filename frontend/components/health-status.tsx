"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { API_BASE_URL, HEALTH_TIMEOUT_MS, fetchHealth, type HealthResult } from "@/lib/api";

type State = { kind: "checking" } | HealthResult;

const COLD_START_HINT_AFTER_S = 5;

export function HealthStatus() {
  const [state, setState] = useState<State>({ kind: "checking" });
  const [elapsed, setElapsed] = useState(0);
  const controllerRef = useRef<AbortController | null>(null);

  const check = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    const timeout = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);

    setState({ kind: "checking" });
    setElapsed(0);
    const result = await fetchHealth(controller.signal);
    clearTimeout(timeout);
    if (controllerRef.current === controller) {
      setState(result);
    }
  }, []);

  useEffect(() => {
    // Run the first check after mount; later checks come from the retry button.
    const first = setTimeout(check, 0);
    return () => {
      clearTimeout(first);
      controllerRef.current?.abort();
    };
  }, [check]);

  useEffect(() => {
    if (state.kind !== "checking") return;
    const timer = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, [state.kind]);

  return (
    <section
      aria-live="polite"
      className="w-full rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/15 dark:bg-neutral-900"
    >
      <div className="flex items-center gap-3">
        <StatusDot kind={state.kind} />
        <p className="text-lg font-medium">{headline(state)}</p>
      </div>

      {state.kind === "checking" && elapsed >= COLD_START_HINT_AFTER_S && (
        <p className="mt-3 text-sm text-neutral-600 dark:text-neutral-400">
          The backend runs on a free instance that sleeps when idle. Waking it can take up to a
          minute. Waiting {elapsed}s.
        </p>
      )}

      {(state.kind === "healthy" || state.kind === "degraded") && (
        <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-1 text-sm text-neutral-600 dark:text-neutral-400">
          <dt>Database latency</dt>
          <dd>
            {state.body.database_latency_ms === null ? "n/a" : `${state.body.database_latency_ms} ms`}
          </dd>
          <dt>Environment</dt>
          <dd>{state.body.environment}</dd>
          <dt>API version</dt>
          <dd>{state.body.version}</dd>
        </dl>
      )}

      {state.kind === "unreachable" && (
        <p className="mt-3 text-sm text-neutral-600 dark:text-neutral-400">{state.reason}</p>
      )}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <code className="break-all text-xs text-neutral-500">{API_BASE_URL}</code>
        <button
          type="button"
          onClick={check}
          disabled={state.kind === "checking"}
          className="rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-white dark:text-neutral-900"
        >
          Check again
        </button>
      </div>
    </section>
  );
}

function headline(state: State): string {
  switch (state.kind) {
    case "checking":
      return "Checking the API…";
    case "healthy":
      return "API healthy, database connected";
    case "degraded":
      return "API reachable, database unavailable";
    case "unreachable":
      return "API unreachable";
  }
}

function StatusDot({ kind }: { kind: State["kind"] }) {
  const color = {
    checking: "bg-amber-400 animate-pulse",
    healthy: "bg-emerald-500",
    degraded: "bg-orange-500",
    unreachable: "bg-red-500",
  }[kind];
  return <span aria-hidden className={`inline-block h-3 w-3 shrink-0 rounded-full ${color}`} />;
}
