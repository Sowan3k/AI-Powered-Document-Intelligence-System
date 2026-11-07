// Choosing files on a phone: what the picker offers, what each file is, and
// photos the server cannot read turned into JPEG (D84). Used by the upload box
// and by the re-upload button (D85).

// File types as well as extensions: Android's picker hides whatever is not on
// this list, and some pickers ignore a list of extensions alone. Every image is
// offered, so a phone photo always shows in the folder (D84).
export const ACCEPT = [
  "application/pdf", ".pdf",
  "image/*", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".heic", ".heif",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx",
  "application/vnd.ms-excel", ".xls",
  "text/csv", ".csv",
].join(",");
// Server limit (MAX_FILE_MB). The server checks again by content.
export const MAX_MB = 50;
// A phone photo larger than this is drawn smaller before upload: mobile browsers
// cannot make a bigger canvas, and OCR needs far fewer pixels.
const MAX_PIXELS = 16_000_000;

const KINDS: Record<string, string> = {
  pdf: "PDF", jpg: "Photo", jpeg: "Photo", png: "Photo", tif: "TIFF", tiff: "TIFF",
  xlsx: "Excel", xls: "Excel", csv: "CSV",
};
// Android often names a picked photo with no extension, so the file type counts too.
const KINDS_BY_TYPE: Record<string, string> = {
  "application/pdf": "PDF",
  "image/jpeg": "Photo",
  "image/png": "Photo",
  "image/tiff": "TIFF",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "Excel",
  "application/vnd.ms-excel": "Excel",
  "text/csv": "CSV",
  "text/comma-separated-values": "CSV",
};

export type Picked = { key: string; file: File; kind: string | null; problem: string | null; marked: boolean; note?: string };

function kindOf(file: File): string | null {
  const ext = file.name.includes(".") ? (file.name.split(".").pop()?.toLowerCase() ?? "") : "";
  return KINDS[ext] ?? KINDS_BY_TYPE[file.type] ?? null;
}

function describe(file: File, key: string, note?: string): Picked {
  const kind = kindOf(file);
  const problem = !kind
    ? "not a supported type"
    : file.size === 0
      ? "empty file"
      : file.size > MAX_MB * 1024 * 1024
        ? `over ${MAX_MB} MB`
        : null;
  return { key, file, kind, problem, marked: problem === null, note };
}

function isOtherImage(file: File): boolean {
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  return file.type.startsWith("image/") || ["webp", "heic", "heif", "avif", "gif", "bmp"].includes(ext);
}

/** A photo the server cannot read (WEBP, AVIF, HEIC where the browser decodes it) as a JPEG. */
async function toJpeg(file: File): Promise<File | null> {
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, Math.sqrt(MAX_PIXELS / (bitmap.width * bitmap.height)));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.fillStyle = "#fff"; // a transparent image gets a white page, not black
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    const blob = await new Promise<Blob | null>((done) => canvas.toBlob(done, "image/jpeg", 0.92));
    if (!blob) return null;
    const base = file.name.includes(".") ? file.name.slice(0, file.name.lastIndexOf(".")) : file.name;
    return new File([blob], `${base || "photo"}.jpg`, { type: "image/jpeg", lastModified: file.lastModified });
  } catch {
    return null;
  }
}

export async function prepare(file: File): Promise<Picked> {
  const key = `${file.name}:${file.size}:${file.lastModified}`;
  if (kindOf(file) || !isOtherImage(file)) return describe(file, key);
  const jpeg = await toJpeg(file);
  if (jpeg) return describe(jpeg, key, `converted from ${file.name.split(".").pop()?.toUpperCase() || "image"} to JPEG`);
  const heic = /\.(heic|heif)$/i.test(file.name) || /hei[cf]/.test(file.type);
  return {
    key,
    file,
    kind: "Photo",
    marked: false,
    problem: heic
      ? "this browser cannot read HEIC photos. Share the photo as JPEG, or turn off high-efficiency pictures in the camera settings"
      : "this image could not be read",
  };
}
