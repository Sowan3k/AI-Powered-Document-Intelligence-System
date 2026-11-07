"use client";

import { useEffect, useRef, useState } from "react";

import { Button, ErrorBox } from "@/components/ui";
import { ApiError, apiBlob } from "@/lib/api";

// Files the API can draw page by page. Spreadsheets and CSV files download.
const PAGED = new Set(["application/pdf", "image/tiff", "image/png", "image/jpeg"]);
const FIRST = 3;
const MORE = 5;

/**
 * The uploaded file next to what was extracted from it (D65). The API draws
 * each page as an image (D83), so the original shows on any browser. A PDF in
 * a frame needs the browser's PDF viewer: most phones have none, and the app's
 * security policy blocks it as a plugin.
 */
export function OriginalFile({
  documentId,
  mimeType,
  filename,
  pageCount,
}: {
  documentId: string;
  mimeType: string | null;
  filename: string;
  pageCount: number | null;
}) {
  const [open, setOpen] = useState(false);
  const [shown, setShown] = useState(FIRST);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const paged = mimeType !== null && PAGED.has(mimeType);
  const total = Math.max(pageCount ?? 1, 1);

  async function download() {
    setBusy(true);
    setError(null);
    try {
      const href = URL.createObjectURL(await apiBlob(`/api/documents/${documentId}/file`));
      const link = document.createElement("a");
      link.href = href;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(href), 60_000);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The file could not be loaded.");
    } finally {
      setBusy(false);
    }
  }

  const pages = Array.from({ length: Math.min(shown, total) }, (_, i) => i + 1);
  return (
    <div className="flex w-full flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        {paged && (
          <Button variant="secondary" onClick={() => setOpen(!open)}>
            {open ? "Hide original" : "View original"}
          </Button>
        )}
        {(!paged || open) && (
          <Button variant={paged ? "ghost" : "secondary"} onClick={download} disabled={busy}>
            {busy ? "Loading file…" : "Download original"}
          </Button>
        )}
      </div>
      {error && <ErrorBox message={error} />}
      {open && paged && (
        <div className="flex flex-col gap-3">
          {pages.map((n) => (
            <PageImage key={n} documentId={documentId} number={n} total={total} filename={filename} />
          ))}
          {total > shown && (
            <div>
              <Button variant="secondary" onClick={() => setShown(shown + MORE)}>
                Show {Math.min(MORE, total - shown)} more {total - shown === 1 ? "page" : "pages"} ({total - shown} left)
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** One page, fetched with the token when it comes near the screen. */
function PageImage({ documentId, number, total, filename }: { documentId: string; number: number; total: number; filename: string }) {
  const box = useRef<HTMLElement>(null);
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    let url: string | null = null;
    let live = true;
    const seen = new IntersectionObserver(
      (entries) => {
        if (!entries.some((e) => e.isIntersecting)) return;
        seen.disconnect();
        apiBlob(`/api/documents/${documentId}/pages/${number}/image`)
          .then((blob) => {
            if (!live) return;
            url = URL.createObjectURL(blob);
            setSrc(url);
          })
          .catch(() => live && setFailed(true));
      },
      { rootMargin: "600px 0px" },
    );
    seen.observe(el);
    return () => {
      live = false;
      seen.disconnect();
      if (url) URL.revokeObjectURL(url);
    };
  }, [documentId, number]);

  return (
    <figure ref={box} className="flex flex-col gap-1">
      {src ? (
        // A blob URL from the API: next/image cannot optimise it, and need not.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src}
          alt={`Page ${number} of the original file, ${filename}`}
          className="w-full rounded-lg border border-black/10 bg-white dark:border-white/15"
        />
      ) : (
        <div
          className={`grid aspect-[1/1.414] w-full place-items-center rounded-lg border border-black/10 text-sm text-muted dark:border-white/15 ${failed ? "" : "animate-pulse bg-black/[0.04] dark:bg-white/[0.06]"}`}
        >
          {failed ? "This page could not be shown." : `Loading page ${number}…`}
        </div>
      )}
      {total > 1 && <figcaption className="text-center text-xs text-muted">Page {number} of {total}</figcaption>}
    </figure>
  );
}
