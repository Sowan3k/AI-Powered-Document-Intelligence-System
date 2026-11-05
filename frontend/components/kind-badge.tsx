// A small coloured tile that says what kind of file a document is.
const KINDS = {
  pdf: { text: "PDF", tone: "bg-rose-500/[0.07] text-rose-600 ring-rose-500/20 dark:text-rose-300" },
  image: { text: "IMG", tone: "bg-amber-500/[0.07] text-amber-700 ring-amber-500/20 dark:text-amber-300" },
  spreadsheet: { text: "XLS", tone: "bg-emerald-500/[0.07] text-emerald-700 ring-emerald-500/20 dark:text-emerald-300" },
  csv: { text: "CSV", tone: "bg-brass/[0.08] text-brass ring-brass/25" },
} as const;

export type Kind = keyof typeof KINDS;

export function KindBadge({ kind, className = "size-10" }: { kind: Kind | null; className?: string }) {
  const k = kind ? KINDS[kind] : { text: "FILE", tone: "bg-neutral-500/15 text-muted ring-neutral-500/25" };
  return (
    <span className={`grid shrink-0 place-items-center rounded-xl text-2xs font-bold tracking-wide ring-1 ring-inset ${k.tone} ${className}`}>
      {k.text}
    </span>
  );
}
