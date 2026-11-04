"""Gemini vision fallback for pages where Tesseract was not confident (D07).

The vision model transcribes the page image to text. The transcription then
goes through the same text extraction and evidence check as every other page,
so there is one extraction path, and evidence is checked against what the
vision model read.

If the vision model stays unavailable after its retries, the text model,
which also reads images, gets one try. If both fail, the page keeps its
Tesseract text: the document still goes through, and its low confidence sends
it to review (D44).
"""

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import pymupdf
from PIL import Image, ImageOps, ImageSequence

from app.extract import prompts
from app.extract.llm import ImagePart, LlmClient, LlmError, LlmUsage, Turn
from app.ingest.pdf import render_gray
from app.ingest.schemas import FileKind

logger = logging.getLogger(__name__)

MAX_SIDE = 3000  # keeps image tokens and upload size bounded


def _png(gray) -> bytes:  # type: ignore[no-untyped-def]
    h, w = gray.shape
    if max(h, w) > MAX_SIDE:
        scale = MAX_SIDE / max(h, w)
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".png", gray)
    if not ok:
        raise ValueError("page image could not be encoded")
    return buf.tobytes()


def page_images(
    path: Path, kind: FileKind, numbers: set[int], dpi: int
) -> Iterator[tuple[int, bytes]]:
    """PNG images of the wanted pages, one at a time."""
    if kind is FileKind.PDF:
        with pymupdf.open(path, filetype="pdf") as doc:
            for n in sorted(numbers):
                yield n, _png(render_gray(doc.load_page(n - 1), dpi))
        return
    import numpy as np

    with Image.open(path) as img:
        for n, frame in enumerate(ImageSequence.Iterator(img), start=1):
            if n in numbers:
                gray = np.asarray(ImageOps.exif_transpose(frame).convert("L"))
                yield n, _png(gray)


def transcribe(llm: LlmClient, model: str, png: bytes) -> tuple[str, LlmUsage]:
    reply = llm.generate(
        purpose="vision_transcribe",
        model=model,
        system=prompts.VISION_SYSTEM,
        turns=[Turn("user", [ImagePart(png), prompts.VISION_USER])],
    )
    return reply.text.strip(), reply.usage


@dataclass
class VisionResult:
    text: str | None  # None when every model failed
    model: str | None
    usage: LlmUsage | None
    errors: list[str] = field(default_factory=list)


def transcribe_with_fallback(llm: LlmClient, models: list[str | None], png: bytes) -> VisionResult:
    """Try each configured model once (each call has its own retries), in order."""
    errors: list[str] = []
    for model in dict.fromkeys(m for m in models if m):  # unique, in order
        try:
            text, usage = transcribe(llm, model, png)
        except LlmError as exc:
            logger.warning("vision transcription with %s failed: %s", model, exc)
            errors.append(f"{model}: {exc}")
            continue
        return VisionResult(text, model, usage, errors)
    return VisionResult(None, None, None, errors)
