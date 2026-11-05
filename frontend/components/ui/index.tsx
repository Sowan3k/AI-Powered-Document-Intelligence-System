import Link from "next/link";
import type { ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <section
      className={`surface w-full rounded-2xl p-4 ${className}`}
    >
      {children}
    </section>
  );
}

export function PageTitle({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-3">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      {children}
    </header>
  );
}

const TONES = {
  green: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  amber: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  red: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
  blue: "bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300",
  gray: "bg-neutral-100 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300",
} as const;
export type Tone = keyof typeof TONES;

export function Badge({ tone = "gray", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${TONES[tone]}`}>
      {children}
    </span>
  );
}

export const STATUS_TONE: Record<string, Tone> = {
  queued: "gray",
  processing: "blue",
  running: "blue",
  completed: "green",
  succeeded: "green",
  ok: "green",
  reviewed: "green",
  failed: "red",
  needs_review: "amber",
  pending: "gray",
};

export function StatusBadge({ status }: { status: string }) {
  return <Badge tone={STATUS_TONE[status] ?? "gray"}>{status.replaceAll("_", " ")}</Badge>;
}

export function Button({
  children,
  variant = "primary",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" }) {
  const styles = {
    primary: "bg-neutral-900 text-white hover:bg-neutral-700 dark:bg-white dark:text-neutral-900 dark:hover:bg-neutral-200",
    secondary: "surface hover:brightness-110",
    ghost: "hover:bg-neutral-100 dark:hover:bg-neutral-800",
  }[variant];
  return (
    <button
      className={`inline-flex min-h-10 items-center justify-center gap-2 rounded-xl px-4 text-sm font-medium transition active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-50 ${styles} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
      <p>{message}</p>
      {onRetry && (
        <button onClick={onRetry} className="mt-2 font-medium underline">
          Try again
        </button>
      )}
    </div>
  );
}

export function Loading({ slow, what = "Loading" }: { slow?: boolean; what?: string }) {
  return (
    <div aria-live="polite" className="py-6 text-sm text-neutral-600 dark:text-neutral-400">
      <p className="flex items-center gap-2">
        <span className="size-2 animate-pulse rounded-full bg-sky-500" />
        {what}…
      </p>
      {slow && (
        <p className="mt-2">
          The backend runs on a free instance that sleeps when idle. Waking it can take up to a
          minute.
        </p>
      )}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-2xl border border-dashed border-black/15 p-6 text-center text-sm text-muted dark:border-white/15">
      {children}
    </p>
  );
}

export function TextLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link href={href} className="font-medium text-sky-700 underline-offset-2 hover:underline dark:text-sky-400">
      {children}
    </Link>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="font-medium text-neutral-700 dark:text-neutral-300">{label}</span>
      {children}
    </label>
  );
}

export const inputClass =
  "min-h-11 w-full rounded-xl border border-black/10 bg-white/70 px-3 text-base outline-none transition focus:border-sky-400 focus:ring-4 focus:ring-sky-400/20 dark:border-white/12 dark:bg-white/5 sm:text-sm";
