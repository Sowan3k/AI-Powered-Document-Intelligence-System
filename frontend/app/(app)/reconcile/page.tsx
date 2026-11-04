"use client";

import { useState, type FormEvent } from "react";

import { Badge, Button, Card, Empty, ErrorBox, Field, Loading, PageTitle, inputClass } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { dateText, label, money } from "@/lib/format";
import type { DocumentSummary, Page, ReconcileSide, Reconciliation } from "@/lib/types";
import { useApi } from "@/lib/use-api";

export default function ReconcilePage() {
  const docs = useApi<Page<DocumentSummary>>("/api/documents?status=completed&limit=100");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<Reconciliation | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    try {
      setReport(
        await api<Reconciliation>("/api/reconcile", {
          method: "POST",
          body: JSON.stringify({ document_a: form.get("a"), document_b: form.get("b") }),
        }),
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Reconciliation failed.");
    } finally {
      setBusy(false);
    }
  }

  const options = docs.data?.items ?? [];
  return (
    <>
      <PageTitle title="Reconcile" />
      <p className="-mt-3 text-sm text-neutral-600 dark:text-neutral-400">
        Compare two documents, for example a supplier statement PDF against your Excel export.
        Invoices match by number first, then by supplier, date and total.
      </p>
      {docs.error && <ErrorBox message={docs.error} onRetry={docs.reload} />}
      {docs.loading && !docs.data && <Loading slow={docs.slow} />}
      {docs.data && options.length < 2 && <Empty>Process at least two documents first.</Empty>}
      {options.length >= 2 && (
        <Card>
          <form onSubmit={submit} className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
            {(["a", "b"] as const).map((side, i) => (
              <Field key={side} label={`Document ${side.toUpperCase()}`}>
                <select name={side} required className={inputClass} defaultValue={options[i]?.id}>
                  {options.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.filename} ({d.invoice_count} invoices)
                    </option>
                  ))}
                </select>
              </Field>
            ))}
            <Button type="submit" disabled={busy}>
              {busy ? "Comparing…" : "Compare"}
            </Button>
          </form>
        </Card>
      )}
      {error && <ErrorBox message={error} />}
      {report && <Report report={report} />}
    </>
  );
}

function Side({ s }: { s: ReconcileSide }) {
  return (
    <span className="text-sm">
      <span className="font-medium">{s.invoice_number ?? "no number"}</span> · {s.supplier_name ?? "?"} · {dateText(s.invoice_date)} · {money(s.total)}{" "}
      <span className="text-xs text-neutral-500">({s.where})</span>
    </span>
  );
}

function Report({ report }: { report: Reconciliation }) {
  const r = report.result;
  const s = r.summary;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2">
        <Badge tone="green">{s.matched} matched</Badge>
        <Badge tone="red">{s.mismatched} mismatched</Badge>
        <Badge tone="amber">{s.only_in_a} only in A</Badge>
        <Badge tone="amber">{s.only_in_b} only in B</Badge>
      </div>
      {r.mismatched.length > 0 && (
        <Card>
          <h2 className="mb-2 font-semibold">Mismatched</h2>
          <ul className="flex flex-col gap-3">
            {r.mismatched.map((m, i) => (
              <li key={i} className="flex flex-col gap-1">
                <Side s={m.a} />
                <ul className="ml-3 text-sm">
                  {m.differences.map((d) => (
                    <li key={d.field}>
                      <span className="font-medium">{label(d.field)}</span>: A {String(d.a ?? "empty")}, B {String(d.b ?? "empty")}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </Card>
      )}
      {(["only_in_a", "only_in_b"] as const).map((key) =>
        r[key].length > 0 ? (
          <Card key={key}>
            <h2 className="mb-2 font-semibold">{key === "only_in_a" ? "Only in A" : "Only in B"}</h2>
            <ul className="flex flex-col gap-1">
              {r[key].map((x) => (
                <li key={x.invoice_id}>
                  <Side s={x} />
                </li>
              ))}
            </ul>
          </Card>
        ) : null,
      )}
      {r.matched.length > 0 && (
        <Card>
          <h2 className="mb-2 font-semibold">Matched</h2>
          <ul className="flex flex-col gap-1">
            {r.matched.map((m, i) => (
              <li key={i} className="flex flex-wrap items-center gap-2">
                <Side s={m.a} />
                <Badge>{m.matched_on === "invoice_number" ? "by number" : "by supplier, date, total"}</Badge>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
