"use client";

import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useState } from "react";

import { ApproveButton } from "@/components/approve-button";
import { Badge, Card, Empty, ErrorBox, Loading, PageTitle } from "@/components/ui";
import { dateText, money } from "@/lib/format";
import type { Page, ReviewItem } from "@/lib/types";
import { useApi } from "@/lib/use-api";

export default function ReviewPage() {
  const { data, error, loading, slow, reload } = useApi<Page<ReviewItem>>("/api/review-queue?limit=100");
  const [done, setDone] = useState<string[]>([]);
  const items = (data?.items ?? []).filter((i) => !done.includes(i.id));
  return (
    <>
      <PageTitle title="Review" />
      <p className="-mt-3 text-sm text-muted">
        These invoices have a problem: numbers that do not add up, a missing field, a possible
        duplicate, or a value the AI could not prove. Approve it if it is right, or open it to fix it.
      </p>
      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading && !data && <Loading slow={slow} />}
      {data && items.length === 0 && <Empty>All clear. Nothing needs review.</Empty>}
      <ul className="flex flex-col gap-3">
        <AnimatePresence initial={false}>
        {items.map((inv, i) => (
          <motion.li
            key={inv.id}
            layout
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0, transition: { delay: Math.min(i, 8) * 0.03 } }}
            exit={{ opacity: 0, x: 80, scale: 0.96, transition: { duration: 0.25 } }}
            transition={{ type: "spring", stiffness: 380, damping: 34 }}
          >
            <Card>
              <Link href={`/documents/${inv.document_id}`} className="block">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="font-medium">{inv.invoice_number ?? "No invoice number"}</p>
                    <p className="text-sm text-neutral-600 dark:text-neutral-400">
                      {inv.supplier_name ?? "Unknown supplier"} · {dateText(inv.invoice_date)} · {money(inv.total, inv.currency)}
                    </p>
                    <p className="mt-1 break-all text-xs text-neutral-500">{inv.filename}</p>
                    {inv.top_issue && (
                      <p className="mt-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800 dark:bg-red-950/40 dark:text-red-300">
                        {inv.top_issue}
                      </p>
                    )}
                  </div>
                  <div className="flex gap-1">
                    <Badge tone="red">{inv.error_count} problem{inv.error_count === 1 ? "" : "s"}</Badge>
                    {inv.warning_count > 0 && <Badge tone="amber">{inv.warning_count} note{inv.warning_count === 1 ? "" : "s"}</Badge>}
                  </div>
                </div>
              </Link>
              <div className="mt-3 flex gap-2">
                <Link href={`/documents/${inv.document_id}`} className="inline-flex min-h-10 flex-1 items-center justify-center rounded-lg border border-black/15 px-4 text-sm font-medium sm:flex-none dark:border-white/20">
                  Open and fix
                </Link>
                <ApproveButton invoiceId={inv.id} onDone={() => setDone((d) => [...d, inv.id])} />
              </div>
            </Card>
          </motion.li>
        ))}
        </AnimatePresence>
      </ul>
    </>
  );
}
