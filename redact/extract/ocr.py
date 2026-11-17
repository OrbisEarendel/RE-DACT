"""RE-DACT PaddleOCR extraction module.

Conforms to AGENTS.md section 5:
    def ocr(image) -> list[Word]: ...   # PaddleOCR inside, nothing else leaks out
    def to_normalized(path_or_bytes) -> NormalizedDoc: ...

Rules (AGENTS.md section 2 & 9):
  * Offline: no outbound network calls, models loaded from local cache.
  * In-memory only: no temporary files holding original data.
  * No raw PII in logs or error messages.
  * Returns word-level boxes (Word dataclass).
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np
from PIL import Image

from redact.entity import NormalizedDoc, Word

# Enforce offline mode for PaddleX / PaddleOCR
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

_OCR_ENGINE = None


def get_ocr_engine(lang: str = "en"):
    """Lazy singleton for PaddleOCR engine to avoid re-initializing weights on every call."""
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        from paddleocr import PaddleOCR

        _OCR_ENGINE = PaddleOCR(
            lang=lang,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
    return _OCR_ENGINE


def _to_numpy_image(image: str | Path | bytes | Image.Image | np.ndarray) -> np.ndarray:
    """Convert any supported image input into an in-memory BGR numpy array without writing to disk."""
    if isinstance(image, (str, Path)):
        img_path = str(image)
        if not os.path.exists(img_path):
            raise FileNotFoundError(f"Image file does not exist: {img_path}")
        img = cv2.imread(img_path)
        if img is None:
            raise ValueError(f"Failed to read image from path: {img_path}")
        return img

    if isinstance(image, bytes):
        arr = np.frombuffer(image, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Failed to decode image from in-memory bytes.")
        return img

    if isinstance(image, Image.Image):
        rgb = np.array(image.convert("RGB"))
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    if isinstance(image, np.ndarray):
        if image.ndim == 2:  # Grayscale
            return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        if image.ndim == 3 and image.shape[2] == 4:  # RGBA
            return cv2.cvtColor(image, cv2.COLOR_RGBA2BGR)
        return image

    raise TypeError(f"Unsupported image input type: {type(image)}")


def _box_to_xywh(box: Sequence[Any]) -> tuple[int, int, int, int]:
    """Convert 4-point polygon [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] or 4-value [x1,y1,x2,y2] to (x, y, w, h)."""
    if len(box) == 4 and all(isinstance(v, (int, float, np.integer, np.floating)) for v in box):
        x1, y1, x2, y2 = box
        x = int(round(min(x1, x2)))
        y = int(round(min(y1, y2)))
        w = max(1, int(round(abs(x2 - x1))))
        h = max(1, int(round(abs(y2 - y1))))
        return x, y, w, h

    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    x = int(round(min(xs)))
    y = int(round(min(ys)))
    w = max(1, int(round(max(xs) - min(xs))))
    h = max(1, int(round(max(ys) - min(ys))))
    return x, y, w, h


def _split_line_into_words(
    line_text: str,
    box: Sequence[Any],
    conf: float,
    page: int,
) -> list[Word]:
    """Fallback word-level splitter: horizontally partitions line box proportionally by character span."""
    line_text = line_text.strip()
    if not line_text:
        return []

    x, y, w, h = _box_to_xywh(box)
    raw_words = line_text.split()
    if len(raw_words) <= 1:
        return [Word(text=line_text, x=x, y=y, w=w, h=h, conf=conf, page=page)]

    words: list[Word] = []
    total_len = len(line_text)
    curr_idx = 0

    for word in raw_words:
        w_start = line_text.find(word, curr_idx)
        if w_start == -1:
            w_start = curr_idx
        w_end = w_start + len(word)
        curr_idx = w_end

        wx = x + int(round(w * (w_start / total_len)))
        ww = max(1, int(round(w * (len(word) / total_len))))
        words.append(Word(text=word, x=wx, y=y, w=ww, h=h, conf=conf, page=page))

    return words


def ocr(
    image: str | Path | bytes | Image.Image | np.ndarray,
    page: int = 0,
    region: tuple[float, float, float, float] | None = None,
) -> list[Word]:
    """Run PaddleOCR on an image and return word-level bounding boxes.

    Signature contract: def ocr(image) -> list[Word]

    Args:
        image: Path, raw bytes, PIL Image, or numpy array.
        page: Page index (defaults to 0).
        region: Optional crop bounding box (x1, y1, x2, y2) to OCR a specific sub-region.

    Returns:
        list[Word]: Word objects containing text, bounding box (x, y, w, h), confidence and page.
    """
    img_np = _to_numpy_image(image)

    offset_x = 0
    offset_y = 0
    if region is not None:
        rx1, ry1, rx2, ry2 = map(int, region)
        h_img, w_img = img_np.shape[:2]
        rx1 = max(0, min(rx1, w_img))
        rx2 = max(0, min(rx2, w_img))
        ry1 = max(0, min(ry1, h_img))
        ry2 = max(0, min(ry2, h_img))
        if rx2 > rx1 and ry2 > ry1:
            img_np = img_np[ry1:ry2, rx1:rx2]
            offset_x = rx1
            offset_y = ry1

    engine = get_ocr_engine()
    results = engine.predict(img_np, return_word_box=True)

    words: list[Word] = []

    for page_res in results:
        data = page_res.json() if callable(getattr(page_res, "json", None)) else page_res.json
        if isinstance(data, str):
            data = json.loads(data)

        res = data.get("res", data) if isinstance(data, dict) else {}

        rec_texts = res.get("rec_texts", [])
        rec_boxes = res.get("rec_boxes", [])
        rec_scores = res.get("rec_scores", [])
        text_word = res.get("text_word", [])
        text_word_boxes = res.get("text_word_boxes", [])

        has_native_words = bool(text_word and text_word_boxes)

        if has_native_words:
            for line_idx, line_tokens in enumerate(text_word):
                line_boxes = text_word_boxes[line_idx] if line_idx < len(text_word_boxes) else []
                conf = float(rec_scores[line_idx]) if line_idx < len(rec_scores) else 1.0

                for token_idx, token_text in enumerate(line_tokens):
                    clean_text = token_text.strip()
                    if not clean_text:
                        continue  # Skip spaces and empty tokens

                    if token_idx < len(line_boxes):
                        t_box = line_boxes[token_idx]
                        x, y, w, h = _box_to_xywh(t_box)
                        words.append(
                            Word(
                                text=clean_text,
                                x=x + offset_x,
                                y=y + offset_y,
                                w=w,
                                h=h,
                                conf=conf,
                                page=page,
                            )
                        )
        else:
            # Fallback when native word boxes are not returned
            for line_idx, line_text in enumerate(rec_texts):
                if not line_text.strip():
                    continue
                box = rec_boxes[line_idx] if line_idx < len(rec_boxes) else [0, 0, 1, 1]
                conf = float(rec_scores[line_idx]) if line_idx < len(rec_scores) else 1.0
                line_words = _split_line_into_words(line_text, box, conf, page)
                for w in line_words:
                    w.x += offset_x
                    w.y += offset_y
                    words.append(w)

    return words


def words_to_normalized(words: list[Word]) -> NormalizedDoc:
    """Connect OCR words to NormalizedDoc position map (AGENTS.md section 5).

    Joins words into one full document string, tracking the (start, end)
    character offset of each Word in `spans`.
    Words on consecutive lines (or different pages) are separated by newlines;
    words within the same line are separated by spaces.
    """
    if not words:
        return NormalizedDoc(text="", spans=[])

    doc_text_parts: list[str] = []
    spans: list[tuple[int, int, Any]] = []
    curr_offset = 0

    prev_word: Word | None = None

    for word in words:
        if prev_word is not None:
            # Check if this word belongs to a new line or a new page
            is_new_page = word.page != prev_word.page
            line_height = max(prev_word.h, word.h, 10)
            is_new_line = is_new_page or (abs(word.y - prev_word.y) > line_height * 0.6) or (word.x < prev_word.x)

            sep = "\n" if is_new_line else " "
            doc_text_parts.append(sep)
            curr_offset += len(sep)

        start = curr_offset
        w_text = word.text
        end = start + len(w_text)

        doc_text_parts.append(w_text)
        curr_offset = end

        spans.append((start, end, word))
        prev_word = word

    full_text = "".join(doc_text_parts)
    return NormalizedDoc(text=full_text, spans=spans)


def to_normalized(path_or_bytes: str | Path | bytes | Image.Image | np.ndarray) -> NormalizedDoc:
    """Direct conversion of an image to NormalizedDoc via PaddleOCR."""
    words = ocr(path_or_bytes)
    return words_to_normalized(words)
