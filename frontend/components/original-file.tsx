"use client";

import { useEffect, useState } from "react";

import { Button, ErrorBox } from "@/components/ui";
import { ApiError, apiBlob } from "@/lib/api";

const INLINE = new Set(["application/pdf", "image/png", "image/jpeg"]);

// Shows the uploaded file next to what was extracted from it (D65). PDFs and
// photos open in the page; spreadsheets and TIFFs download.
export function OriginalFile({ documentId, mimeType, filename }: { documentId: string; mimeType: string | null; filename: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inline = mimeType !== null && INLINE.has(mimeType);

  useEffect(() => {
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [url]);

  async function load(): Promise<string | null> {
    if (url) return url;
    setBusy(true);
    setError(null);
    try {
      const blob = await apiBlob(`/api/documents/${documentId}/file`);
      const next = URL.createObjectURL(blob);
      setUrl(next);
      return next;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The file could not be loaded.");
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function toggle() {
    if (open) return setOpen(false);
    if (await load()) setOpen(true);
  }

  async function download() {
    const href = await load();
    if (!href) return;
    const link = document.createElement("a");
    link.href = href;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  return (
    <div className="flex w-full flex-col gap-2">
      <div>
        <Button variant="secondary" onClick={inline ? toggle : download} disabled={busy}>
          {busy ? "Loading file…" : inline ? (open ? "Hide original" : "View original") : "Download original"}
        </Button>
      </div>
      {error && <ErrorBox message={error} />}
      {open && url && mimeType === "application/pdf" && (
        <div className="flex flex-col gap-1">
          <iframe src={url} title={`Original file: ${filename}`} className="h-[70vh] w-full rounded-lg border border-black/10 dark:border-white/15" />
          <a href={url} target="_blank" rel="noopener noreferrer" className="text-sm underline">
            Open in a new tab
          </a>
        </div>
      )}
      {open && url && mimeType?.startsWith("image/") && (
        // A blob URL from the API: next/image cannot optimise it, and need not.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url} alt={`Original file: ${filename}`} className="max-h-[80vh] w-full rounded-lg border border-black/10 object-contain dark:border-white/15" />
      )}
    </div>
  );
}
