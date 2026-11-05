"""Turn digital pages into degraded scans (rotation, blur, noise, JPEG artefacts)
and into phone photos (perspective, uneven light, a desk around the page)."""

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


# How hard each phone photo is. "scale" shrinks the final image, like a photo
# taken from further away; "shadow" darkens part of the page, like a hand or the
# phone itself in the light; "motion" is the length of a shake blur in pixels.
PHOTO_LEVELS: dict[str, dict] = {
    "mild": {"tilt": 0.05, "falloff": (0.25, 0.4), "blur": (0.8, 1.2), "noise": (4, 6),
             "scale": 1.0, "shadow": 0.0, "motion": 0, "jpeg": (65, 75)},
    "medium": {"tilt": 0.08, "falloff": (0.35, 0.5), "blur": (1.1, 1.4), "noise": (6, 9),
               "scale": 0.6, "shadow": 0.35, "motion": 0, "jpeg": (50, 60)},
    "hard": {"tilt": 0.10, "falloff": (0.45, 0.6), "blur": (1.2, 1.6), "noise": (8, 12),
             "scale": 0.45, "shadow": 0.5, "motion": 7, "jpeg": (35, 45)},
}  # fmt: skip


def photo(gray: np.ndarray, rng: random.Random, level: str = "mild") -> np.ndarray:
    """A phone photo of a printed page: paper on a desk, seen at an angle, lit from
    one side, slightly out of focus, with sensor noise. Returns a colour image."""
    opt = PHOTO_LEVELS[level]
    noise = np.random.default_rng(rng.randint(0, 2**31))
    h, w = gray.shape
    # Warm paper, darker than pure white.
    paper = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR).astype(np.float32)
    paper *= np.array([0.86, 0.92, 0.97], dtype=np.float32)
    # The desk around the page.
    pad = int(0.08 * max(h, w))
    big_h, big_w = h + 2 * pad, w + 2 * pad
    desk = np.empty((big_h, big_w, 3), np.float32)
    desk[:] = [rng.uniform(40, 70), rng.uniform(60, 90), rng.uniform(90, 120)]
    desk += noise.normal(0, 8, desk.shape)
    # Perspective: each corner of the page moves by up to `tilt` of its width.
    j = opt["tilt"] * w
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[x + pad + rng.uniform(-j, j), y + pad + rng.uniform(-j, j)] for x, y in src])
    matrix = cv2.getPerspectiveTransform(src, dst)
    page = cv2.warpPerspective(paper, matrix, (big_w, big_h))
    mask = cv2.warpPerspective(np.ones((h, w), np.float32), matrix, (big_w, big_h))[..., None]
    out = desk * (1 - mask) + page * mask
    # Light from one side, falling off across the frame, and a soft vignette.
    angle = rng.uniform(0, 2 * np.pi)
    yy, xx = np.mgrid[0:big_h, 0:big_w].astype(np.float32)
    side = (xx - big_w / 2) * np.cos(angle) + (yy - big_h / 2) * np.sin(angle)
    side /= np.abs(side).max()
    light = 1 - rng.uniform(*opt["falloff"]) * (side + 1) / 2
    radius = np.sqrt(((xx - big_w / 2) / (big_w / 2)) ** 2 + ((yy - big_h / 2) / (big_h / 2)) ** 2)
    light *= 1 - 0.15 * np.clip(radius - 0.6, 0, None)
    # A shadow with a soft edge over one part of the page.
    if opt["shadow"]:
        turn = rng.uniform(0, 2 * np.pi)
        edge = (xx - big_w / 2) * np.cos(turn) + (yy - big_h / 2) * np.sin(turn)
        edge /= np.abs(edge).max()
        shade = (edge > rng.uniform(-0.2, 0.4)).astype(np.float32)
        shade = cv2.GaussianBlur(shade, (0, 0), 0.02 * big_w)
        light *= 1 - opt["shadow"] * shade
    out *= light[..., None]
    # Soft focus, a hand shake, distance, and sensor noise.
    out = cv2.GaussianBlur(out, (0, 0), rng.uniform(*opt["blur"]))
    if opt["motion"]:
        k = np.zeros((opt["motion"], opt["motion"]), np.float32)
        k[opt["motion"] // 2, :] = 1 / opt["motion"]
        turn = cv2.getRotationMatrix2D(
            (opt["motion"] / 2 - 0.5, opt["motion"] / 2 - 0.5), rng.uniform(0, 180), 1.0
        )
        k = cv2.warpAffine(k, turn, k.shape[::-1])
        out = cv2.filter2D(out, -1, k / k.sum())
    if opt["scale"] != 1.0:
        out = cv2.resize(out, None, fx=opt["scale"], fy=opt["scale"], interpolation=cv2.INTER_AREA)
    out += noise.normal(0, rng.uniform(*opt["noise"]), out.shape)
    return np.clip(out, 0, 255).astype(np.uint8)


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
