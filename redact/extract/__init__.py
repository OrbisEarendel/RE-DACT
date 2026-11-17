"""RE-DACT extraction package.

Connects Alan's router/gate to format-specific extractors:
- Plaintext / CSV: native text extraction
- Image (PNG, JPG, HEIC): PaddleOCR extraction
- PDF: router-directed native text extraction and/or page OCR
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from redact.entity import NormalizedDoc, Word
from redact.extract.image import to_normalized as image_to_normalized
from redact.extract.ocr import ocr, words_to_normalized
from redact.extract.pdf import to_normalized as pdf_to_normalized
from redact.extract.text import to_normalized as text_to_normalized
from redact.gate import Format, RoutePlan, route, route_path


def to_normalized(
    path_or_bytes: str | Path | bytes,
    filename: str | None = None,
) -> NormalizedDoc:
    """Universal extractor: routes input with Alan's gate and extracts to NormalizedDoc."""
    doc, _ = extract(path_or_bytes, filename=filename)
    return doc


def extract(
    path_or_bytes: str | Path | bytes,
    filename: str | None = None,
) -> tuple[NormalizedDoc, RoutePlan]:
    """Route input using the gate and extract content into a NormalizedDoc."""
    if isinstance(path_or_bytes, (str, Path)):
        p = Path(path_or_bytes)
        if not p.exists():
            raise FileNotFoundError(f"Input file not found: {p}")
        data = p.read_bytes()
        fname = filename or p.name
    elif isinstance(path_or_bytes, bytes):
        data = path_or_bytes
        fname = filename or "input.bin"
    else:
        raise TypeError(f"Unsupported input type: {type(path_or_bytes)}")

    plan = route(data, filename=fname)

    if plan.format == Format.IMAGE:
        doc = image_to_normalized(data)
    elif plan.format == Format.PDF:
        doc = pdf_to_normalized(data, plan=plan)
    elif plan.format in (Format.TEXT, Format.CSV, Format.JSON):
        doc = text_to_normalized(data, encoding=plan.encoding or "utf-8")
    else:
        # Fallback to plain text decode if supported
        doc = text_to_normalized(data, encoding=plan.encoding or "utf-8")

    return doc, plan


__all__ = [
    "extract",
    "image_to_normalized",
    "ocr",
    "pdf_to_normalized",
    "text_to_normalized",
    "to_normalized",
    "words_to_normalized",
]
