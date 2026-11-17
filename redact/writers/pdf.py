"""RE-DACT PDF Redaction Writer.

Conforms to AGENTS.md sections 4 & 5:
    PDF: PyMuPDF - True redaction (content physically removed, not covered).
    Repo layout: redact/writers/pdf.py

Rules:
  * In-memory only: does not write temporary files with raw PII to disk.
  * True redaction: uses PyMuPDF's page.apply_redactions() to expunge text & graphics.
  * Preserves original vector formatting, fonts, and layout outside redacted bounds.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Sequence

import pymupdf

from redact.entity import Entity, NormalizedDoc, Word


def _find_words_for_entities(
    ents: Sequence[Entity],
    doc: NormalizedDoc,
) -> list[tuple[Word, str]]:
    """Match detected Entity char ranges against NormalizedDoc.spans to find corresponding Word boxes."""
    matched: list[tuple[Word, str]] = []
    for ent in ents:
        for span_start, span_end, ref in doc.spans:
            if not isinstance(ref, Word):
                continue
            if max(span_start, ent.start) < min(span_end, ent.end):
                matched.append((ref, ent.type.upper()))
    return matched


def redact_pdf(
    pdf: str | Path | bytes,
    ents: list[Entity],
    norm_doc: NormalizedDoc,
    fill_color: tuple[float, float, float] = (0, 0, 0),
) -> bytes:
    """Apply true redactions to a PDF document using PyMuPDF.

    Args:
        pdf: PDF path, bytes, or file-like object.
        ents: List of Entity objects to redact.
        norm_doc: The NormalizedDoc produced from the PDF containing Word spans.
        fill_color: RGB tuple (0.0 to 1.0) for the redaction box (default solid black).

    Returns:
        Redacted PDF binary bytes with sensitive content expunged.
    """
    if isinstance(pdf, (str, Path)):
        p = Path(pdf)
        if not p.exists():
            raise FileNotFoundError(f"PDF not found: {p}")
        data = p.read_bytes()
    elif isinstance(pdf, bytes):
        data = pdf
    else:
        raise TypeError(f"Unsupported PDF input type: {type(pdf)}")

    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        # Match entities to word boxes
        word_matches = _find_words_for_entities(ents, norm_doc)

        # Group redaction rects by page
        page_rects: dict[int, list[pymupdf.Rect]] = {}
        for word, _ in word_matches:
            pg = word.page
            if pg not in page_rects:
                page_rects[pg] = []
            # Word coordinates (x, y, w, h)
            rect = pymupdf.Rect(word.x, word.y, word.x + word.w, word.y + word.h)
            page_rects[pg].append(rect)

        # Apply redactions to each page
        for pg_idx, rects in page_rects.items():
            if 0 <= pg_idx < len(doc):
                page = doc[pg_idx]
                for r in rects:
                    # True redaction annotation
                    page.add_redact_annot(r, fill=fill_color)
                page.apply_redactions()

        return doc.tobytes(garbage=4, deflate=True)
    finally:
        doc.close()


def redact_pdf_pipeline(
    pdf: str | Path | bytes,
    level: int = 1,
    enabled_types: set[str] | None = None,
    threshold: float = 0.4,
) -> tuple[bytes, dict]:
    """End-to-end PDF redaction: extraction -> detection -> policy filtering -> true redaction.

    Returns:
        tuple[bytes, dict]: (redacted_pdf_bytes, summary_dict)
    """
    from redact.extract.pdf import to_normalized
    from redact.detect import detect
    from policy.policy import select

    if isinstance(pdf, (str, Path)):
        data = Path(pdf).read_bytes()
    else:
        data = pdf

    # 1. Extract to NormalizedDoc
    norm_doc = to_normalized(data)

    # 2. Detect all PII entities
    raw_ents = detect(norm_doc.text, threshold=threshold)

    # 3. Filter entities through policy
    selected_ents = select(raw_ents, level=level, enabled_types=enabled_types)

    # 4. Apply true redaction
    redacted_bytes = redact_pdf(data, selected_ents, norm_doc)

    return redacted_bytes, {
        "total_detected": len(raw_ents),
        "total_redacted": len(selected_ents),
        "before_preview": norm_doc.text[:200] + ("..." if len(norm_doc.text) > 200 else ""),
        "after_preview": f"{len(selected_ents)} items expunged from PDF",
    }
