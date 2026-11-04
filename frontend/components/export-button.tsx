"use client";

import { useState } from "react";

import { Button } from "@/components/ui";
import { ApiError, api } from "@/lib/api";

// Downloads every extracted invoice as a CSV that opens in Excel. The API
// needs the bearer token, so the file is fetched and saved through a blob
// instead of a plain link.
export function ExportButton() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function download() {
    setBusy(true);
    setError(null);
    try {
      const text = await api<string>("/api/export/invoices.csv");
      // response.text() drops the byte order mark; Excel needs it for Bengali text.
      const blob = new Blob(["﻿", text], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `docintel-invoices-${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The download failed. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-start gap-1">
      <Button variant="secondary" onClick={download} disabled={busy}>
        {busy ? "Preparing file…" : "Download invoices for Excel"}
      </Button>
      {error && (
        <p role="alert" className="text-xs text-red-700 dark:text-red-400">
          {error}
        </p>
      )}
    </div>
  );
}
