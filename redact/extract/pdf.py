"""RE-DACT PDF extraction module: routes native vs OCR pages.

Conforms to AGENTS.md section 5:
    def to_normalized(path_or_bytes) -> NormalizedDoc: ...
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pymupdf

from redact.entity import NormalizedDoc, Word
from redact.extract.ocr import ocr, words_to_normalized
from redact.gate import Engine, RoutePlan, route
from redact.detect.visual import detect_visual_pii


def _extract_native_page_words(page: pymupdf.Page, page_index: int) -> list[Word]:
    """Extract words and bounding boxes directly from PDF text layer."""
    raw_words = page.get_text("words")  # (x0, y0, x1, y1, word_text, block_no, line_no, word_no)
    words: list[Word] = []
    for w in raw_words:
        x0, y0, x1, y1, w_text = w[:5]
        clean_text = w_text.strip()
        if not clean_text:
            continue
        x = int(round(min(x0, x1)))
        y = int(round(min(y0, y1)))
        width = max(1, int(round(abs(x1 - x0))))
        height = max(1, int(round(abs(y1 - y0))))
        words.append(
            Word(
                text=clean_text,
                x=x,
                y=y,
                w=width,
                h=height,
                conf=1.0,
                page=page_index,
            )
        )
    return words


def to_normalized(
    path_or_bytes: str | Path | bytes,
    plan: RoutePlan | None = None,
) -> NormalizedDoc:
    """Extract PDF pages into NormalizedDoc using router-directed native extraction and OCR."""
    if isinstance(path_or_bytes, (str, Path)):
        p = Path(path_or_bytes)
        if not p.exists():
            raise FileNotFoundError(f"PDF not found: {p}")
        data = p.read_bytes()
        filename = p.name
    elif isinstance(path_or_bytes, bytes):
        data = path_or_bytes
        filename = "document.pdf"
    else:
        raise TypeError(f"Unsupported input type for PDF extraction: {type(path_or_bytes)}")

    if plan is None:
        plan = route(data, filename=filename)

    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        all_words: list[Word] = []

        # Map route plans by page index
        route_map = {r.unit: r for r in plan.routes if r.locator.startswith("page:")}

        for page_idx in range(len(doc)):
            page = doc[page_idx]
            page_route = route_map.get(page_idx)

            # Native text layer extracted first whenever available
            native_words = _extract_native_page_words(page, page_idx)
            if native_words:
                all_words.extend(native_words)
                # Check for visual PII (face photos, QR codes) on the page
                pix = page.get_pixmap(dpi=150)
                img_bytes = pix.tobytes("png")
                sx = page.rect.width / max(1, pix.width)
                sy = page.rect.height / max(1, pix.height)
                v_words = detect_visual_pii(img_bytes, page=page_idx)
                for vw in v_words:
                    vw.x = int(round(vw.x * sx))
                    vw.y = int(round(vw.y * sy))
                    vw.w = max(1, int(round(vw.w * sx)))
                    vw.h = max(1, int(round(vw.h * sy)))
                all_words.extend(v_words)

                # If page is mixed (has native text AND large image regions), OCR image regions too
                if page_route and page_route.engine in (Engine.OCR, Engine.BOTH):
                    pix_ocr = page.get_pixmap(dpi=plan.ocr_dpi)
                    img_ocr = pix_ocr.tobytes("png")
                    scale_x = page.rect.width / max(1, pix_ocr.width)
                    scale_y = page.rect.height / max(1, pix_ocr.height)
                    if page_route.ocr_regions:
                        dpi_scale = plan.ocr_dpi / 72.0
                        for reg in page_route.ocr_regions:
                            rx1, ry1, rx2, ry2 = [c * dpi_scale for c in reg]
                            ocr_words = ocr(img_ocr, page=page_idx, region=(rx1, ry1, rx2, ry2))
                            for w in ocr_words:
                                w.x = int(round(w.x * scale_x))
                                w.y = int(round(w.y * scale_y))
                                w.w = max(1, int(round(w.w * scale_x)))
                                w.h = max(1, int(round(w.h * scale_y)))
                            all_words.extend(ocr_words)
            else:
                # Scanned page with no native text: rasterize in-memory and run PaddleOCR
                pix = page.get_pixmap(dpi=plan.ocr_dpi)
                img_bytes = pix.tobytes("png")
                scale_x = page.rect.width / max(1, pix.width)
                scale_y = page.rect.height / max(1, pix.height)

                page_words = ocr(img_bytes, page=page_idx)
                for w in page_words:
                    w.x = int(round(w.x * scale_x))
                    w.y = int(round(w.y * scale_y))
                    w.w = max(1, int(round(w.w * scale_x)))
                    w.h = max(1, int(round(w.h * scale_y)))
                all_words.extend(page_words)

                # Detect visual PII (photos, QR codes)
                v_words = detect_visual_pii(img_bytes, page=page_idx)
                for vw in v_words:
                    vw.x = int(round(vw.x * scale_x))
                    vw.y = int(round(vw.y * scale_y))
                    vw.w = max(1, int(round(vw.w * scale_x)))
                    vw.h = max(1, int(round(vw.h * scale_y)))
                all_words.extend(v_words)

        return words_to_normalized(all_words)
    finally:
        doc.close()
