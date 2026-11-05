import { StatusBadge } from "@/components/ui";
import type { Job } from "@/lib/types";

export function JobProgress({ job }: { job: Job | null }) {
  if (!job) return null;
  const total = job.progress_total;
  const pct = total ? Math.min(100, Math.round((job.progress_done / total) * 100)) : null;
  return (
    <div className="flex min-w-0 flex-col gap-1 text-xs text-neutral-600 dark:text-neutral-400">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={job.status} />
        {job.job_type === "index" && <span>search refresh</span>}
        {job.attempts > 1 && (
          <span>
            attempt {job.attempts} of {job.max_attempts}
          </span>
        )}
        {total ? (
          <span>
            {job.progress_done} of {total} pages
          </span>
        ) : null}
      </div>
      {job.status === "running" && pct !== null && (
        <div className="h-1.5 w-full overflow-hidden rounded bg-neutral-200 dark:bg-neutral-800" aria-label={`${pct}% done`}>
          <div className="h-full bg-foreground/80 transition-all" style={{ width: `${pct}%` }} />
        </div>
      )}
      {job.last_error && job.status !== "succeeded" && (
        <p className="break-words text-red-700 dark:text-red-400">{job.last_error}</p>
      )}
    </div>
  );
}
