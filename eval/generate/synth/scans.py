"""Turn digital pages into degraded scans: rotation, blur, noise, JPEG artefacts."""

import random

import cv2
import numpy as np
import pymupdf
from PIL import Image


def render(page: pymupdf.Page, dpi: int = 200) -> np.ndarray:
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, alpha=False)
    return (
        np.frombuffer(pix.samples, dtype=np.uint8)
        .reshape(pix.height, pix.stride)[:, : pix.width]
        .copy()
    )


def degrade(gray: np.ndarray, rng: random.Random, level: str = "light") -> np.ndarray:
    """light: small tilt and noise; heavy: more tilt, blur, noise and strong JPEG."""
    angle = rng.uniform(1.0, 2.5) * rng.choice([-1, 1]) if level == "light" else rng.uniform(3, 5)
    h, w = gray.shape
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    out = cv2.warpAffine(gray, matrix, (w, h), borderValue=255)
    if level == "heavy":
        out = cv2.GaussianBlur(out, (5, 5), 1.2)
    noise = np.random.default_rng(rng.randint(0, 2**31)).normal(
        0, 12 if level == "light" else 30, out.shape
    )
    out = np.clip(out.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    quality = 70 if level == "light" else 25
    ok, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, quality])
    assert ok
    return cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)


def scanned_pdf(images: list[np.ndarray], dpi: int = 200) -> pymupdf.Document:
    """A PDF whose pages are only images, like a scanner makes."""
    doc = pymupdf.open()
    for gray in images:
        ok, buf = cv2.imencode(".jpg", gray, [cv2.IMWRITE_JPEG_QUALITY, 85])
        assert ok
        h, w = gray.shape
        page = doc.new_page(width=w * 72 / dpi, height=h * 72 / dpi)
        page.insert_image(page.rect, stream=buf.tobytes())
    return doc


def save_tiff(images: list[np.ndarray], path: str, dpi: int = 200) -> None:
    frames = [Image.fromarray(g) for g in images]
    frames[0].save(
        path, save_all=True, append_images=frames[1:], compression="tiff_deflate", dpi=(dpi, dpi)
    )
