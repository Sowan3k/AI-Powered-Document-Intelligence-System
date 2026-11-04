"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { useActivity } from "@/components/activity";
import { ChevronIcon, SparkIcon, CheckIcon } from "@/components/icons";
import { ProcessFlow } from "@/components/process-flow";

/**
 * Live processing on every screen. A small pill shows how many files are moving;
 * tap it to watch each one go through Upload, Read, AI extract, Check and Done.
 * Finished files stay for a little while, then the dock hides itself.
 */
export function ActivityDock() {
  const { activity } = useActivity();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const active = activity?.active ?? [];
  const recent = (activity?.recent ?? []).slice(0, 5);
  // Home shows the same flow in full, so the dock would only cover it.
  if (pathname === "/documents" || (active.length === 0 && recent.length === 0)) return null;
  const busy = active.length > 0;
  const working = active.filter((a) => a.stage !== "queued");
  const waiting = active.length - working.length;

  return (
    <div className="dock-in fixed inset-x-3 bottom-20 z-30 sm:inset-x-auto sm:right-4 sm:bottom-4 sm:w-96">
      {open && (
        <div className="mb-2 max-h-[60vh] overflow-y-auto rounded-2xl border border-black/10 bg-white p-3 shadow-xl dark:border-white/15 dark:bg-neutral-900">
          <ul className="flex flex-col gap-3">
            {[...active, ...recent].map((item) => (
              <li key={item.document_id}>
                <Link href={`/documents/${item.document_id}`} onClick={() => setOpen(false)} className="block">
                  <p className="mb-1 truncate text-sm font-medium">{item.filename}</p>
                  <ProcessFlow item={item} compact />
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className={`flex w-full items-center gap-3 rounded-full px-4 py-3 text-left text-sm font-medium shadow-lg ${busy ? "bg-sky-600 text-white" : "bg-emerald-600 text-white"}`}
      >
        <span className="relative grid size-6 place-items-center">
          {busy && <span className="absolute inset-0 animate-ping rounded-full bg-white/40 motion-reduce:hidden" />}
          {busy ? <SparkIcon className="size-4" /> : <CheckIcon className="size-4" />}
        </span>
        <span className="min-w-0 flex-1 truncate">
          {busy
            ? working.length > 0
              ? `${working[0].stage_label}: ${working[0].filename}${active.length > 1 ? ` (+${active.length - 1} more${waiting ? `, ${waiting} waiting` : ""})` : ""}`
              : `${waiting} file${waiting === 1 ? "" : "s"} waiting to start`
            : `${recent.length} file${recent.length === 1 ? "" : "s"} finished`}
        </span>
        <ChevronIcon className={`size-4 transition-transform ${open ? "" : "rotate-180"}`} />
      </button>
    </div>
  );
}
