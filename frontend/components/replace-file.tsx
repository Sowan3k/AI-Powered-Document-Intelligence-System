"use client";

import { useRef, useState } from "react";

import { Button } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { ACCEPT, prepare } from "@/lib/files";

const PHOTO = new Set(["image/jpeg", "image/png"]);

/**
 * Put a new file in place of a document's file and read it again (D85). For a
 * photo too blurred to read: retake it, and the document keeps its place and
 * history. On a phone the picker also offers the camera.
 */
export function ReplaceFile({
  documentId,
  filename,
  mimeType,
  onDone,
  onError,
  variant = "secondary",
  className = "",
}: {
  documentId: string;
  filename: string;
  mimeType: string | null;
  onDone: (message: string) => void;
  onError: (message: string) => void;
  variant?: "primary" | "secondary" | "ghost";
  className?: string;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const photo = mimeType !== null && PHOTO.has(mimeType);

  async function send(list: FileList | null) {
    const file = list?.[0]; // read now: the input is cleared right after
    if (!file) return;
    const picked = await prepare(file);
    if (picked.problem) return onError(`Cannot upload ${picked.file.name}: ${picked.problem}.`);
    const ask = `Replace ${filename} with ${picked.file.name}? Its invoices are read again from the new file, and earlier corrections to them are dropped.`;
    if (!window.confirm(ask)) return;
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", picked.file);
      await api(`/api/documents/${documentId}/replace`, { method: "POST", body: form });
      onDone(`${picked.file.name} is uploaded in place of ${filename} and is being read now.`);
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "The upload failed. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button variant={variant} onClick={() => input.current?.click()} disabled={busy} className={className}>
        {busy ? "Uploading…" : photo ? "Retake photo" : "Re-upload"}
      </Button>
      <input
        ref={input}
        type="file"
        accept={ACCEPT}
        className="sr-only"
        aria-label={`New file for ${filename}`}
        onChange={(e) => {
          send(e.target.files);
          e.target.value = "";
        }}
      />
    </>
  );
}
