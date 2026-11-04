"use client";

import Link from "next/link";

import { Badge, Card, Empty, ErrorBox, Loading, PageTitle } from "@/components/ui";
import { dateText, money } from "@/lib/format";
import type { Page, ReviewItem } from "@/lib/types";
import { useApi } from "@/lib/use-api";

export default function ReviewPage() {
  const { data, error, loading, slow, reload } = useApi<Page<ReviewItem>>("/api/review-queue?limit=100");
  return (
    <>
      <PageTitle title="Review queue" />
      <p className="-mt-3 text-sm text-neutral-600 dark:text-neutral-400">
        Invoices with at least one error: numbers that do not add up, missing required fields,
        possible duplicates, or values the model could not prove from the source.
      </p>
      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading && !data && <Loading slow={slow} />}
      {data?.items.length === 0 && <Empty>Nothing to review. Every invoice passed its checks.</Empty>}
      <ul className="flex flex-col gap-3">
        {data?.items.map((inv) => (
          <li key={inv.id}>
            <Link href={`/documents/${inv.document_id}`} className="block">
              <Card className="hover:border-sky-400">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="font-medium">{inv.invoice_number ?? "No invoice number"}</p>
                    <p className="text-sm text-neutral-600 dark:text-neutral-400">
                      {inv.supplier_name ?? "Unknown supplier"} · {dateText(inv.invoice_date)} · {money(inv.total, inv.currency)}
                    </p>
                    <p className="mt-1 break-all text-xs text-neutral-500">{inv.filename}</p>
                  </div>
                  <div className="flex gap-1">
                    <Badge tone="red">{inv.error_count} error{inv.error_count === 1 ? "" : "s"}</Badge>
                    {inv.warning_count > 0 && <Badge tone="amber">{inv.warning_count} warning{inv.warning_count === 1 ? "" : "s"}</Badge>}
                  </div>
                </div>
              </Card>
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}
