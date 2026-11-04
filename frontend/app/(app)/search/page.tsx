"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { Badge, Button, Card, Empty, ErrorBox, Field, Loading, PageTitle, StatusBadge, inputClass } from "@/components/ui";
import { query } from "@/lib/api";
import { dateText, money } from "@/lib/format";
import type { SearchResponse } from "@/lib/types";
import { useApi } from "@/lib/use-api";

type Form = Record<string, string>;

export default function SearchPage() {
  return (
    <Suspense fallback={<Loading />}>
      <SearchView />
    </Suspense>
  );
}

function SearchView() {
  const params = useSearchParams();
  const initial = params.get("q") ?? "";
  // Best match (hybrid, D68) by default: exact codes and loose descriptions both work.
  const [mode, setMode] = useState<"hybrid" | "keyword" | "semantic">("hybrid");
  // A search typed on Home runs at once.
  const [path, setPath] = useState<string | null>(initial ? `/api/search${query({ mode: "hybrid", limit: 50, q: initial })}` : null);
  const { data, error, loading, slow } = useApi<SearchResponse>(path);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = Object.fromEntries(new FormData(event.currentTarget)) as Form;
    // With no words, best match lists everything that fits the filters.
    const effective = mode === "hybrid" && !form.q?.trim() ? "keyword" : mode;
    setPath(`/api/search${query({ mode: effective, limit: 50, ...form })}`);
  }

  return (
    <>
      <PageTitle title="Search" />
      <Card>
        <form onSubmit={submit} className="flex flex-col gap-3">
          <div role="radiogroup" aria-label="Search mode" className="flex gap-1 rounded-lg bg-neutral-100 p-1 text-sm dark:bg-neutral-800">
            {(["hybrid", "keyword", "semantic"] as const).map((m) => (
              <button
                key={m}
                type="button"
                role="radio"
                aria-checked={mode === m}
                onClick={() => setMode(m)}
                className={`flex-1 rounded-md px-3 py-2 ${mode === m ? "bg-white font-medium shadow-sm dark:bg-neutral-950" : ""}`}
              >
                {m === "hybrid" ? "Best match" : m === "keyword" ? "Exact words" : "By meaning"}
              </button>
            ))}
          </div>
          <Field label={mode === "keyword" ? "Words, numbers or names" : mode === "semantic" ? "Describe what you are looking for" : "Numbers, names or a description"}>
            <input
              name="q"
              defaultValue={initial}
              className={inputClass}
              required={mode === "semantic"}
              placeholder={mode === "keyword" ? 'INV-2026-00007, "toner cartridge", acme -delivery' : mode === "semantic" ? "printer supplies bought in spring" : "INV-2026-00007 or printer supplies"}
            />
          </Field>
          <details>
            <summary className="cursor-pointer text-sm font-medium">Filters</summary>
            <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Field label="Supplier">
                <input name="supplier" className={inputClass} />
              </Field>
              <Field label="Currency">
                <input name="currency" className={inputClass} placeholder="USD" pattern="[A-Za-z]{3}" />
              </Field>
              <Field label="Date from">
                <input name="date_from" type="date" className={inputClass} />
              </Field>
              <Field label="Date to">
                <input name="date_to" type="date" className={inputClass} />
              </Field>
              <Field label="Total at least">
                <input name="amount_min" inputMode="decimal" className={inputClass} />
              </Field>
              <Field label="Total at most">
                <input name="amount_max" inputMode="decimal" className={inputClass} />
              </Field>
              <Field label="Review status">
                <select name="status" className={inputClass} defaultValue="">
                  <option value="">Any</option>
                  <option value="ok">OK</option>
                  <option value="needs_review">Needs review</option>
                  <option value="reviewed">Reviewed</option>
                </select>
              </Field>
            </div>
          </details>
          <Button type="submit">Search</Button>
        </form>
      </Card>

      {error && <ErrorBox message={error} />}
      {loading && <Loading slow={slow} what="Searching" />}
      {data && !loading && (
        <>
          <p className="text-sm text-neutral-600 dark:text-neutral-400">
            {data.total} result{data.total === 1 ? "" : "s"}
            {data.mode === "semantic" && ", closest meaning first"}
            {data.mode === "hybrid" && ", best matches first (words and meaning combined)"}
          </p>
          {data.items.length === 0 && <Empty>Nothing matched. Try fewer words or wider filters.</Empty>}
          <ul className="flex flex-col gap-3">
            {data.items.map((hit) => (
              <li key={hit.id}>
                <Link href={`/documents/${hit.document_id}`} className="block">
                  <Card className="hover:border-sky-400">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="font-medium">{hit.invoice_number ?? "No invoice number"}</p>
                        <p className="text-sm text-neutral-600 dark:text-neutral-400">
                          {hit.supplier_name ?? "Unknown supplier"} · {dateText(hit.invoice_date)} · {money(hit.total, hit.currency)}
                        </p>
                        {hit.line_items.length > 0 && (
                          <p className="mt-1 truncate text-xs text-neutral-500">
                            {hit.line_items.map((li) => li.description).filter(Boolean).join(", ")}
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-1">
                        {hit.score !== null && data.mode !== "hybrid" && <Badge tone="blue">{data.mode === "semantic" ? `${Math.round(hit.score * 100)}% match` : `rank ${hit.score.toFixed(2)}`}</Badge>}
                        <StatusBadge status={hit.review_status} />
                      </div>
                    </div>
                  </Card>
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}
