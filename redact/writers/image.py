"""RE-DACT image redaction writer.

Conforms to AGENTS.md section 5:
    def redact_image(image, words: list[Word], ents: list[Entity], doc: NormalizedDoc, style="box"): ...

Rules:
  * In-memory only: does not write original or temporary files to disk.
  * True redaction: obliterated pixels (solid blackout or heavy blur) so content cannot be recovered.
  * Preserves all non-redacted areas pixel-for-pixel.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np
from PIL import Image

from redact.entity import Entity, NormalizedDoc, Word
from redact.detect.visual import _ensure_bgr_image, detect_visual_pii
from redact.extract.ocr import to_normalized
from redact.detect import detect


def _find_words_for_entities(
    ents: Sequence[Entity],
    doc: NormalizedDoc,
) -> list[tuple[Word, str]]:
    """Match detected Entity char ranges against NormalizedDoc.spans to find corresponding OCR words."""
    matched: list[tuple[Word, str]] = []
    for ent in ents:
        for span_start, span_end, ref in doc.spans:
            if not isinstance(ref, Word):
                continue
            # Overlap check between [span_start, span_end) and [ent.start, ent.end)
            if max(span_start, ent.start) < min(span_end, ent.end):
                matched.append((ref, ent.type.upper()))
    return matched


def redact_image(
    image: str | Path | bytes | Image.Image | np.ndarray,
    words: list[Word],
    ents: list[Entity],
    doc: NormalizedDoc,
    style: str = "box",
) -> np.ndarray:
    """Redact sensitive words and visual entities on an image.

    Signature contract:
        def redact_image(image, words: list[Word], ents: list[Entity], doc: NormalizedDoc, style="box")

    Args:
        image: Original input image.
        words: List of all recognized OCR Word objects.
        ents: List of detected sensitive Entity objects to redact.
        doc: NormalizedDoc containing text and span mappings.
        style: Redaction style - 'box' (solid black), 'blur' (heavy blur), or 'label' (black box with label text).

    Returns:
        np.ndarray: Redacted BGR image array.
    """
    img_out = _ensure_bgr_image(image).copy()
    img_h, img_w = img_out.shape[:2]

    # 1. Collect target bounding boxes from text entities
    targets: list[tuple[int, int, int, int, str]] = []
    text_matches = _find_words_for_entities(ents, doc)
    for w, label in text_matches:
        targets.append((w.x, w.y, w.w, w.h, label))

    # 2. Collect any visual PII words (faces, QR codes) passed in words list
    for w in words:
        if w.text in ("[PHOTO]", "[QR]"):
            targets.append((w.x, w.y, w.w, w.h, w.text[1:-1]))

    # Deduplicate boxes
    seen_boxes: set[tuple[int, int, int, int]] = set()

    for x, y, w, h, label in targets:
        # Clip coordinates to image boundary
        x1 = max(0, min(x, img_w - 1))
        y1 = max(0, min(y, img_h - 1))
        x2 = max(0, min(x + w, img_w))
        y2 = max(0, min(y + h, img_h))

        if x2 <= x1 or y2 <= y1:
            continue

        box_key = (x1, y1, x2, y2)
        if box_key in seen_boxes:
            continue
        seen_boxes.add(box_key)

        box_w = x2 - x1
        box_h = y2 - y1

        if style == "blur":
            # Apply strong Gaussian blur
            roi = img_out[y1:y2, x1:x2]
            # Kernel dimensions must be positive odd integers
            kw = max(3, (box_w // 2) * 2 + 1)
            kh = max(3, (box_h // 2) * 2 + 1)
            blurred = cv2.GaussianBlur(roi, (kw, kh), 30)
            img_out[y1:y2, x1:x2] = blurred
        else:
            # Solid black rectangle
            cv2.rectangle(img_out, (x1, y1), (x2, y2), (0, 0, 0), thickness=-1)

            if style == "label" and box_w >= 30 and box_h >= 14:
                font_scale = min(0.45, max(0.25, box_h / 30.0))
                cv2.putText(
                    img_out,
                    label[:10],
                    (x1 + 2, y1 + int(box_h * 0.7)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    font_scale,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )

    return img_out


def redact_image_pipeline(
    image: str | Path | bytes | Image.Image | np.ndarray,
    style: str = "box",
    detect_visual: bool = True,
    threshold: float = 0.4,
) -> tuple[np.ndarray, dict[str, Any]]:
    """End-to-end image redaction pipeline: OCR + GLiNER + Visual PII + Redaction.

    Returns:
        tuple[np.ndarray, dict]: (redacted_bgr_image, audit_stats)
    """
    img_bgr = _ensure_bgr_image(image)

    # 1. OCR -> NormalizedDoc
    doc = to_normalized(img_bgr)
    words: list[Word] = [ref for _, _, ref in doc.spans if isinstance(ref, Word)]

    # 2. Text PII detection via GLiNER / Regex
    ents = detect(doc.text, threshold=threshold)

    # 3. Visual PII detection (Face photos + QR codes) via OpenCV
    visual_words: list[Word] = []
    if detect_visual:
        visual_words = detect_visual_pii(img_bgr)
        words.extend(visual_words)

    # 4. Redact image
    redacted = redact_image(img_bgr, words, ents, doc, style=style)

    # Compile non-PII audit statistics
    stats: dict[str, int] = {}
    for e in ents:
        stats[e.type] = stats.get(e.type, 0) + 1
    for vw in visual_words:
        v_type = vw.text.strip("[]").lower()
        stats[v_type] = stats.get(v_type, 0) + 1

    return redacted, {
        "total_redactions": len(ents) + len(visual_words),
        "types": stats,
    }
