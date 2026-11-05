import { CheckIcon, FileIcon, ReadIcon, ShieldIcon, SparkIcon, AlertIcon } from "@/components/icons";
import type { ActivityItem, Stage } from "@/lib/types";

const STEPS = [
  { key: "queued", label: "Upload", Icon: FileIcon },
  { key: "reading", label: "Read", Icon: ReadIcon },
  { key: "extracting", label: "AI extract", Icon: SparkIcon },
  { key: "checking", label: "Check", Icon: ShieldIcon },
  { key: "done", label: "Done", Icon: CheckIcon },
] as const;

// "indexing" sits between Check and Done; it shows as the end of Check.
function stepIndex(stage: Stage): number {
  if (stage === "indexing") return 3;
  if (stage === "failed") return -1;
  return STEPS.findIndex((s) => s.key === stage);
}

/** A file moving through the pipeline: finished steps filled, the current one pulsing. */
export function ProcessFlow({ item, compact = false }: { item: ActivityItem; compact?: boolean }) {
  const current = stepIndex(item.stage);
  const failed = item.stage === "failed";
  const pct =
    item.progress_total && item.progress_total > 0
      ? Math.min(100, Math.round((item.progress_done / item.progress_total) * 100))
      : null;
  return (
    <div className="w-full">
      <ol className="flex items-center" aria-label={`${item.filename}: ${item.stage_label}`}>
        {STEPS.map((step, i) => {
          const done = !failed && (i < current || item.stage === "done");
          const active = !failed && i === current && item.stage !== "done";
          const Icon = failed && i === 0 ? AlertIcon : step.Icon;
          return (
            <li key={step.key} className="flex flex-1 items-center last:flex-none">
              <span
                className={`relative grid shrink-0 place-items-center rounded-full border-2 transition-colors ${compact ? "size-7" : "size-9"} ${
                  failed && i === 0
                    ? "border-red-300 bg-red-50 text-red-600 dark:border-red-800 dark:bg-red-950"
                    : done
                      ? "border-emerald-500 bg-emerald-500 text-white"
                      : active
                        ? "border-foreground bg-white text-foreground dark:bg-neutral-900"
                        : "border-neutral-200 bg-white text-neutral-400 dark:border-neutral-700 dark:bg-neutral-900"
                }`}
                title={step.label}
              >
                {active && <span className="absolute inset-0 animate-ping rounded-full bg-foreground/20 motion-reduce:hidden" />}
                <Icon className={compact ? "size-3.5" : "size-4"} />
              </span>
              {i < STEPS.length - 1 && (
                <span className="relative mx-1 h-1 flex-1 overflow-hidden rounded bg-neutral-200 dark:bg-neutral-800">
                  {(done || (active && i === current)) && (
                    <span
                      className={`absolute inset-y-0 left-0 rounded ${done ? "w-full bg-emerald-500" : "w-1/2 bg-foreground/70 flow-slide motion-reduce:animate-none"}`}
                    />
                  )}
                </span>
              )}
            </li>
          );
        })}
      </ol>
      {!compact && (
        <div className="mt-1 grid grid-cols-5 text-center text-2xs text-neutral-500 sm:text-xs">
          {STEPS.map((s) => (
            <span key={s.key} className="last:text-right first:text-left">
              {s.label}
            </span>
          ))}
        </div>
      )}
      <p className={`mt-1.5 flex items-center justify-between gap-2 text-xs ${failed ? "text-red-700 dark:text-red-400" : "text-neutral-600 dark:text-neutral-400"}`}>
        <span>
          {item.stage_label}
          {failed && item.error_code ? `: ${item.error_code}` : ""}
          {item.stage === "done" && item.invoice_count === 0 && (
            <span className="font-medium text-amber-700 dark:text-amber-400"> · no invoice found</span>
          )}
          {item.stage === "done" && item.invoice_count > 0 && ` · ${item.invoice_count} invoice${item.invoice_count === 1 ? "" : "s"}`}
          {item.stage === "done" && item.needs_review > 0 && ` · ${item.needs_review} to review`}
          {item.attempts > 1 && item.stage !== "done" && !failed && ` · try ${item.attempts}`}
        </span>
        {pct !== null && item.progress_unit && (
          <span className="tabular-nums">
            {item.progress_done}/{item.progress_total} {item.progress_unit}
          </span>
        )}
      </p>
      {pct !== null && !compact && (
        <div className="mt-1 h-1 w-full overflow-hidden rounded bg-neutral-200 dark:bg-neutral-800">
          <div className="h-full bg-foreground/80 transition-all duration-500" style={{ width: `${pct}%` }} />
        </div>
      )}
    </div>
  );
}
