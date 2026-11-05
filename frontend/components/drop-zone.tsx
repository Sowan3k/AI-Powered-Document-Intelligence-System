"use client";

import { useEffect, useRef, useState, type DragEvent } from "react";

import { useActivity } from "@/components/activity";
import { UploadIcon } from "@/components/icons";
import { Button, ErrorBox } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { bytes } from "@/lib/format";
import type { UploadResponse } from "@/lib/types";

const ACCEPT = ".pdf,.jpg,.jpeg,.png,.tif,.tiff,.xlsx,.xls,.csv";
// Server limits (MAX_FILES_PER_BATCH, MAX_FILE_MB). The server checks again by content.
const BATCH = 20;
const MAX_MB = 50;

const KINDS: Record<string, string> = {
  pdf: "PDF", jpg: "Photo", jpeg: "Photo", png: "Photo", tif: "TIFF", tiff: "TIFF",
  xlsx: "Excel", xls: "Excel", csv: "CSV",
};

type Picked = { key: string; file: File; kind: string | null; problem: string | null; marked: boolean };

function describe(file: File): Picked {
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  const kind = KINDS[ext] ?? null;
  const problem = !kind
    ? "not a supported type"
    : file.size === 0
      ? "empty file"
      : file.size > MAX_MB * 1024 * 1024
        ? `over ${MAX_MB} MB`
        : null;
  return { key: `${file.name}:${file.size}:${file.lastModified}`, file, kind, problem, marked: problem === null };
}

/**
 * Add files of any supported type, from several places if needed (on a phone,
 * photos and documents come from different pickers), mark the ones to send,
 * and upload them together (D66). More than 20 go in batches of 20.
 */
export function DropZone() {
  const input = useRef<HTMLInputElement>(null);
  const zone = useRef<HTMLButtonElement>(null);
  const { refresh } = useActivity();
  const [picked, setPicked] = useState<Picked[]>([]);
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rejected, setRejected] = useState<UploadResponse["documents"]>([]);
  const [sent, setSent] = useState<number | null>(null);

  // The light around the border runs only while the box is on screen (D79).
  useEffect(() => {
    const el = zone.current;
    if (!el) return;
    const observer = new IntersectionObserver(([entry]) => {
      el.style.setProperty("--glow-play", entry.isIntersecting ? "running" : "paused");
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  function add(list: FileList | null) {
    // Copy now: the FileList is live and empties when the input is reset.
    const files = list ? Array.from(list) : [];
    if (files.length === 0) return;
    setSent(null);
    setPicked((current) => {
      const seen = new Set(current.map((p) => p.key));
      const fresh = files.map(describe).filter((p) => !seen.has(p.key));
      return [...current, ...fresh];
    });
  }

  const marked = picked.filter((p) => p.marked);
  const counts = marked.reduce<Record<string, number>>((acc, p) => {
    acc[p.kind ?? "?"] = (acc[p.kind ?? "?"] ?? 0) + 1;
    return acc;
  }, {});
  const allMarked = picked.some((p) => !p.problem) && picked.every((p) => p.marked || p.problem);

  function setAll(on: boolean) {
    setPicked((list) => list.map((p) => ({ ...p, marked: on && !p.problem })));
  }

  async function upload() {
    if (marked.length === 0) return;
    setError(null);
    setRejected([]);
    const refused: UploadResponse["documents"] = [];
    let accepted = 0;
    const done = new Set<string>();
    try {
      for (let start = 0; start < marked.length; start += BATCH) {
        const batch = marked.slice(start, start + BATCH);
        setProgress(
          marked.length > BATCH
            ? `Uploading ${start + 1} to ${start + batch.length} of ${marked.length}…`
            : `Uploading ${marked.length} file${marked.length === 1 ? "" : "s"}…`,
        );
        const form = new FormData();
        for (const p of batch) form.append("files", p.file);
        const body = await api<UploadResponse>("/api/documents", { method: "POST", body: form });
        refused.push(...body.documents.filter((d) => d.job_id === null));
        accepted += body.accepted;
        batch.forEach((p) => done.add(p.key));
        refresh(); // the live steps pick the new files up at once
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed.");
    } finally {
      setPicked((list) => list.filter((p) => !done.has(p.key)));
      setRejected(refused);
      setSent(accepted);
      setProgress(null);
    }
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    add(event.dataTransfer.files);
  }

  return (
    <div className="flex flex-col gap-2">
      <button
        ref={zone}
        type="button"
        data-active={dragging}
        onClick={() => input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        disabled={progress !== null}
        className={`glow-border flex w-full flex-col items-center gap-2 rounded-2xl px-4 ${picked.length ? "py-4" : "py-8"} text-center transition ${dragging ? "scale-[1.01] bg-brass/10" : "hover:bg-foreground/[0.03]"}`}
      >
        {/* A light that travels around the border, with a soft glow. */}
        <span aria-hidden className="glow-halo">
          <span className="glow-ring" />
        </span>
        <span aria-hidden className="glow-ring" />
        <span className="grid size-12 place-items-center rounded-full bg-foreground text-background shadow-[0_8px_24px_-10px_rgb(15_27_45/0.6)]">
          <UploadIcon className="size-6" />
        </span>
        <span className="text-base font-semibold">{picked.length ? "Add more files" : "Tap to add files"}</span>
        <span className="text-sm text-neutral-600 dark:text-neutral-400">
          or drop them here. PDF, photos (JPG, PNG, TIFF), Excel or CSV, mixed freely. Add from several places, then upload together.
        </span>
      </button>
      <input
        ref={input}
        type="file"
        multiple
        accept={ACCEPT}
        className="sr-only"
        aria-label="Add files"
        onChange={(e) => {
          add(e.target.files);
          e.target.value = "";
        }}
      />

      {picked.length > 0 && (
        <section aria-label="Files to upload" className="surface flex flex-col gap-2 rounded-2xl p-3">
          <div className="flex items-center justify-between gap-2">
            <label className="flex items-center gap-2 text-sm font-medium">
              <input type="checkbox" checked={allMarked} onChange={(e) => setAll(e.target.checked)} className="size-4" />
              {marked.length} of {picked.length} marked
            </label>
            <button type="button" onClick={() => setPicked([])} className="text-sm text-neutral-600 underline dark:text-neutral-400">
              Clear
            </button>
          </div>
          <ul className="flex max-h-72 flex-col divide-y divide-black/5 overflow-y-auto dark:divide-white/10">
            {picked.map((p) => (
              <li key={p.key} className="flex items-center gap-3 py-2">
                <input
                  type="checkbox"
                  aria-label={`Upload ${p.file.name}`}
                  checked={p.marked}
                  disabled={p.problem !== null}
                  onChange={(e) =>
                    setPicked((list) => list.map((x) => (x.key === p.key ? { ...x, marked: e.target.checked } : x)))
                  }
                  className="size-4 shrink-0"
                />
                <span className="w-12 shrink-0 rounded bg-neutral-100 px-1.5 py-0.5 text-center text-2xs font-medium dark:bg-neutral-800">
                  {p.kind ?? "?"}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm">{p.file.name}</span>
                  <span className={`block text-xs ${p.problem ? "text-red-700 dark:text-red-400" : "text-neutral-500"}`}>
                    {p.problem ? `Cannot upload: ${p.problem}` : bytes(p.file.size)}
                  </span>
                </span>
                <button
                  type="button"
                  aria-label={`Remove ${p.file.name}`}
                  onClick={() => setPicked((list) => list.filter((x) => x.key !== p.key))}
                  className="rounded px-2 text-neutral-500 hover:bg-neutral-100 dark:hover:bg-neutral-800"
                >
                  ✕
                </button>
              </li>
            ))}
          </ul>
          {marked.length > 0 && (
            <p className="text-xs text-neutral-600 dark:text-neutral-400">
              {Object.entries(counts)
                .map(([kind, n]) => `${n} ${kind}`)
                .join(" · ")}
              {marked.length > BATCH ? ` · sent in batches of ${BATCH}` : ""}
            </p>
          )}
          <Button onClick={upload} disabled={marked.length === 0 || progress !== null}>
            {progress ?? `Upload ${marked.length} file${marked.length === 1 ? "" : "s"}`}
          </Button>
        </section>
      )}

      {sent !== null && sent > 0 && progress === null && (
        <p role="status" className="text-sm text-emerald-700 dark:text-emerald-400">
          {sent} file{sent === 1 ? "" : "s"} uploaded. You can follow each one below.
          {picked.length > 0 ? " Files you did not mark stay in the list." : ""}
        </p>
      )}
      {error && <ErrorBox message={error} />}
      {rejected.length > 0 && (
        <div className="relative">
          <ErrorBox
            message={`Not accepted: ${rejected.map((r) => `${r.filename} (${r.error_message ?? r.error_code})`).join("; ")}`}
          />
          <button
            onClick={() => setRejected([])}
            aria-label="Dismiss"
            className="absolute top-2 right-2 rounded px-2 text-red-800 hover:bg-red-100 dark:text-red-300 dark:hover:bg-red-900"
          >
            ✕
          </button>
        </div>
      )}
    </div>
  );
}
