"""Image cleanup with OpenCV and OCR with Tesseract.

Cleanup runs in a fixed order: grayscale, upscale small images, denoise,
deskew, threshold. Tesseract then returns words with a confidence each, and
the page confidence is the mean over real words (0 to 100). Phase 2 sends
pages below OCR_CONFIDENCE_THRESHOLD to Gemini vision.
"""

import logging
from dataclasses import dataclass

import cv2
import numpy as np
import pytesseract

logger = logging.getLogger(__name__)

MIN_WIDTH = 1600  # Tesseract reads small text badly; upscale narrower images
MAX_SIDE = 6000  # cap memory and time on huge images
MAX_SKEW = 10.0  # degrees searched each way
TESSERACT_CONFIG = "--oem 1 --psm 3"


BLANK_INK = 0.002  # under 0.2% dark pixels after cleanup: nothing printed on the page


@dataclass(frozen=True)
class OcrResult:
    text: str
    confidence: float | None  # 0 to 100; None for a blank page, which has nothing to read
    skew_degrees: float


def to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _resize(gray: np.ndarray) -> np.ndarray:
    h, w = gray.shape
    if max(h, w) > MAX_SIDE:
        scale = MAX_SIDE / max(h, w)
        return cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    if w < MIN_WIDTH:
        scale = min(MIN_WIDTH / w, 4.0)
        return cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
    return gray


def estimate_skew(gray: np.ndarray) -> float:
    """Angle in degrees that straightens the text lines (projection profile search).

    Rotating a straight page makes the row sums of ink sharpest, so the best
    angle maximises their variance. Runs on a small copy, coarse then fine.
    """
    h, w = gray.shape
    scale = 800 / max(h, w)
    small = cv2.resize(gray, (max(1, int(w * scale)), max(1, int(h * scale))))
    _, ink = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    if cv2.countNonZero(ink) < 50:
        return 0.0
    center = (ink.shape[1] / 2, ink.shape[0] / 2)

    def score(angle: float) -> float:
        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(ink, matrix, (ink.shape[1], ink.shape[0]), flags=cv2.INTER_NEAREST)
        return float(np.var(rotated.sum(axis=1, dtype=np.float64)))

    coarse = max(np.arange(-MAX_SKEW, MAX_SKEW + 0.01, 0.5), key=score)
    fine = max(np.arange(coarse - 0.5, coarse + 0.51, 0.1), key=score)
    return round(float(fine), 1)


def rotate(gray: np.ndarray, angle: float) -> np.ndarray:
    h, w = gray.shape
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(
        gray,
        matrix,
        (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=255,
    )


def clean_image(image: np.ndarray) -> tuple[np.ndarray, float]:
    """Return a black-on-white image ready for Tesseract, and the skew removed."""
    gray = _resize(to_gray(image))
    gray = cv2.medianBlur(gray, 3)  # removes salt-and-pepper noise, keeps edges
    angle = estimate_skew(gray)
    if abs(angle) >= 0.2:
        gray = rotate(gray, angle)
    # Adaptive threshold copes with shadows and uneven light on photos.
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15
    )
    return binary, angle


def run_tesseract(binary: np.ndarray, timeout_s: int) -> tuple[str, float]:
    """Read words, rebuild lines in reading order, and average word confidence."""
    try:
        data = pytesseract.image_to_data(
            binary,
            lang="eng",
            config=TESSERACT_CONFIG,
            output_type=pytesseract.Output.DICT,
            timeout=timeout_s,
        )
    except RuntimeError:
        # pytesseract raises RuntimeError on timeout. The page gets no text and
        # confidence 0, so Phase 2 sends it to the vision fallback.
        logger.warning("tesseract timed out after %ss", timeout_s)
        return "", 0.0

    lines: dict[tuple[int, int, int], list[str]] = {}
    confidences: list[float] = []
    for i, word in enumerate(data["text"]):
        word = word.strip()
        conf = float(data["conf"][i])
        if not word or conf < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(word)
        confidences.append(conf)

    out: list[str] = []
    previous_block = None
    for (block, _par, _line), words in lines.items():
        if previous_block is not None and block != previous_block:
            out.append("")
        out.append(" ".join(words))
        previous_block = block
    mean = sum(confidences) / len(confidences) if confidences else 0.0
    return "\n".join(out), round(mean, 2)


def is_blank(binary: np.ndarray) -> bool:
    dark = binary.size - cv2.countNonZero(binary)
    return dark / binary.size < BLANK_INK


def ocr_image(image: np.ndarray, timeout_s: int = 120) -> OcrResult:
    binary, angle = clean_image(image)
    if is_blank(binary):
        # A blank page is not a hard page: no OCR, and no vision fallback either.
        return OcrResult(text="", confidence=None, skew_degrees=angle)
    text, confidence = run_tesseract(binary, timeout_s)
    return OcrResult(text=text, confidence=confidence, skew_degrees=angle)
