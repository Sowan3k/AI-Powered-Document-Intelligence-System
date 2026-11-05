"use client";

import { useState, type FormEvent } from "react";

import { ApproveButton } from "@/components/approve-button";
import { Badge, Button, Card, ErrorBox, Field, StatusBadge, inputClass, type Tone } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { dateText, label, money, percent, trimmed, where } from "@/lib/format";
import { EDITABLE_FIELDS, type EditableField, type FieldMeta, type InvoiceDetail } from "@/lib/types";

const MONEY: EditableField[] = ["subtotal", "tax", "total"];
// Matches FIELD_CONFIDENCE_THRESHOLD on the backend (0.7).
const LOW_CONFIDENCE = 0.7;

function metaOf(inv: InvoiceDetail, field: string): FieldMeta {
  const m = inv.field_meta[field];
  return m && typeof m === "object" ? (m as FieldMeta) : {};
}

function confidenceTone(meta: FieldMeta): Tone {
  if (meta.flags?.includes("corrected")) return "blue";
  if (meta.confidence === undefined) return "gray";
  if (meta.confidence < LOW_CONFIDENCE || meta.flags?.includes("evidence_not_found")) return "amber";
  return "green";
}

function display(inv: InvoiceDetail, field: EditableField): string {
  const value = inv[field];
  if (MONEY.includes(field)) return money(value, inv.currency);
  if (field === "invoice_date") return dateText(value);
  return value ?? "—";
}

export function InvoiceCard({ invoice, onSaved }: { invoice: InvoiceDetail; onSaved: (inv: InvoiceDetail) => void }) {
  const [editing, setEditing] = useState(false);
  const [focus, setFocus] = useState<string | null>(null);
  const fix = (field: string | null) => {
    setFocus(field && (EDITABLE_FIELDS as readonly string[]).includes(field) ? field : null);
    setEditing(true);
  };
  const errors = invoice.issues.filter((i) => i.severity === "error");
  const warnings = invoice.issues.filter((i) => i.severity !== "error");

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="type-card">{invoice.invoice_number ?? "Invoice without a number"}</h3>
          <p className="text-xs text-neutral-600 dark:text-neutral-400">{where(invoice)}</p>
        </div>
        <StatusBadge status={invoice.review_status} />
      </div>

      {invoice.issues.length > 0 && (
        <ul className="mt-3 flex flex-col gap-1.5 text-sm">
          {[...errors, ...warnings].map((issue, i) => (
            <li key={i} className="flex gap-2">
              <Badge tone={issue.severity === "error" ? "red" : "amber"}>{issue.rule_code}</Badge>
              <span className="min-w-0 flex-1">
                {issue.field && <span className="font-medium">{label(issue.field)}: </span>}
                {issue.message}
              </span>
              {!editing && issue.field && (EDITABLE_FIELDS as readonly string[]).includes(issue.field) && (
                <button onClick={() => fix(issue.field)} className="link shrink-0 text-xs">
                  Fix
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {editing ? (
        <EditForm invoice={invoice} focus={focus} onCancel={() => setEditing(false)} onSaved={(inv) => {
          setEditing(false);
          onSaved(inv);
        }} />
      ) : (
        <>
          <dl className="mt-4 grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
            {EDITABLE_FIELDS.map((field) => {
              const meta = metaOf(invoice, field);
              return (
                <div key={field} className="min-w-0">
                  <dt className="flex items-center gap-2 text-xs text-neutral-600 dark:text-neutral-400">
                    {label(field)}
                    <Badge tone={confidenceTone(meta)}>
                      {meta.flags?.includes("corrected") ? "corrected" : percent(meta.confidence)}
                    </Badge>
                  </dt>
                  <dd className="mt-0.5 break-words font-medium">{display(invoice, field)}</dd>
                  {meta.evidence && !meta.flags?.includes("corrected") && (
                    <p className="mt-0.5 break-words text-xs text-neutral-500" title="Evidence from the source text">
                      “{meta.evidence}”
                    </p>
                  )}
                  {meta.flags && meta.flags.filter((f) => f !== "corrected").length > 0 && (
                    <p className="mt-0.5 text-xs text-amber-700 dark:text-amber-400">
                      {meta.flags.filter((f) => f !== "corrected").join(", ").replaceAll("_", " ")}
                    </p>
                  )}
                </div>
              );
            })}
          </dl>
          {invoice.adjustments.length > 0 && (
            <div className="mt-3 rounded-lg bg-neutral-50 p-3 text-sm dark:bg-neutral-800">
              <p className="text-xs text-neutral-600 dark:text-neutral-400">Discounts and charges, counted in the total check</p>
              <ul className="mt-1 flex flex-col gap-0.5">
                {invoice.adjustments.map((a, i) => (
                  <li key={i} className="flex justify-between gap-3">
                    <span className="min-w-0 break-words">{a.label}</span>
                    <span className={`tabular-nums ${a.amount === null ? "text-amber-700 dark:text-amber-400" : ""}`}>
                      {a.amount === null ? "unreadable" : money(a.amount)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="mt-4 flex flex-wrap gap-2">
            {invoice.review_status === "needs_review" && (
              <ApproveButton invoiceId={invoice.id} onDone={onSaved} label="Looks right, approve" />
            )}
            <Button variant="secondary" onClick={() => fix(null)}>
              Correct fields
            </Button>
          </div>
        </>
      )}

      {invoice.line_items.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-96 text-left text-sm">
            <thead className="text-xs text-neutral-600 dark:text-neutral-400">
              <tr>
                <th className="py-1 pr-2 font-medium">Item</th>
                <th className="py-1 pr-2 text-right font-medium">Qty</th>
                <th className="py-1 pr-2 text-right font-medium">Unit price</th>
                <th className="py-1 text-right font-medium">Amount</th>
              </tr>
            </thead>
            <tbody>
              {invoice.line_items.map((li) => (
                <tr key={li.position} className="border-t border-black/5 dark:border-white/10">
                  <td className="py-1 pr-2">{li.description ?? "—"}</td>
                  <td className="py-1 pr-2 text-right tabular-nums">{trimmed(li.quantity)}</td>
                  <td className="py-1 pr-2 text-right tabular-nums">{trimmed(li.unit_price, 2)}</td>
                  <td className="py-1 text-right tabular-nums">{money(li.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {invoice.corrections.length > 0 && (
        <details className="mt-4 text-sm">
          <summary className="cursor-pointer text-neutral-600 dark:text-neutral-400">
            {invoice.corrections.length} correction{invoice.corrections.length === 1 ? "" : "s"}
          </summary>
          <ul className="mt-2 flex flex-col gap-1">
            {invoice.corrections.map((c, i) => (
              <li key={i}>
                {label(c.field)}: {String(c.old_value ?? "empty")} → {String(c.new_value ?? "empty")}{" "}
                <span className="text-neutral-500">
                  by {c.username}, {dateText(c.created_at)}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </Card>
  );
}

function EditForm({
  invoice,
  focus,
  onCancel,
  onSaved,
}: {
  invoice: InvoiceDetail;
  focus: string | null;
  onCancel: () => void;
  onSaved: (inv: InvoiceDetail) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const patch: Record<string, string | boolean | null> = {};
    for (const field of EDITABLE_FIELDS) {
      const value = String(form.get(field) ?? "").trim();
      const old = invoice[field] ?? "";
      if (value !== old) patch[field] = value === "" ? null : value;
    }
    patch.mark_reviewed = form.get("mark_reviewed") === "on";
    setBusy(true);
    setError(null);
    try {
      const saved = await api<InvoiceDetail>(`/api/invoices/${invoice.id}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      });
      onSaved(saved);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Saving failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mt-4 flex flex-col gap-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {EDITABLE_FIELDS.map((field) => (
          <Field key={field} label={label(field)}>
            <input
              name={field}
              defaultValue={invoice[field] ?? ""}
              autoFocus={focus === field}
              type={field === "invoice_date" ? "date" : "text"}
              inputMode={MONEY.includes(field) ? "decimal" : undefined}
              placeholder={MONEY.includes(field) ? "0.00" : field === "currency" ? "USD" : ""}
              pattern={MONEY.includes(field) ? "-?\\d+(\\.\\d{1,2})?" : field === "currency" ? "[A-Za-z]{3}" : undefined}
              title={MONEY.includes(field) ? "A number with up to two decimals, no separators" : undefined}
              className={inputClass}
            />
          </Field>
        ))}
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" name="mark_reviewed" defaultChecked className="size-4" />
        Mark as reviewed
      </label>
      {error && <ErrorBox message={error} />}
      <div className="flex gap-2">
        <Button type="submit" disabled={busy}>
          {busy ? "Saving…" : "Save"}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
