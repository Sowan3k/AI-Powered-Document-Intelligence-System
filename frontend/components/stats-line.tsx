"use client";

import { useEffect } from "react";

import type { Stats } from "@/lib/types";
import { useApi } from "@/lib/use-api";

function usd(value: number): string {
  return value < 0.01 ? `$${value.toFixed(4)}` : `$${value.toFixed(2)}`;
}

// One quiet line under the document list: how the system is doing and what
// Gemini has cost so far (D62). Refreshes when the list changes.
export function StatsLine({ changes }: { changes: string }) {
  const { data, reload } = useApi<Stats>("/api/stats");
  useEffect(() => {
    reload();
  }, [changes, reload]);
  if (!data) return null;
  const total = Object.values(data.documents).reduce((a, b) => a + b, 0);
  if (total === 0) return null;
  const tokens = data.tokens_input + data.tokens_output + data.tokens_thinking;
  const perFile = data.cost_per_completed_document_usd;
  const parts = [
    `${total} file${total === 1 ? "" : "s"}`,
    data.success_rate !== null ? `${Math.round(data.success_rate * 100)}% processed` : null,
    data.processing_seconds_mean !== null ? `${Math.round(data.processing_seconds_mean)} s each on average` : null,
    tokens > 0 ? `${tokens.toLocaleString()} AI tokens` : null,
    data.cost_usd !== null && tokens > 0
      ? `about ${usd(data.cost_usd)} at paid Gemini prices${perFile !== null ? ` (${usd(perFile)} a file)` : ""}`
      : null,
  ].filter(Boolean);
  return (
    <p className="text-xs text-neutral-500 dark:text-neutral-400" title={`Prices checked ${data.prices_checked}`}>
      {parts.join(" · ")}
    </p>
  );
}
