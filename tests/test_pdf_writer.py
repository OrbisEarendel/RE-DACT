"""Tests for redact/writers/pdf.py (PyMuPDF true redaction).

Synthetic dummy data only in accordance with AGENTS.md rules 1 and 5.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import pymupdf

from redact.entity import Entity, NormalizedDoc, Word
from redact.writers.pdf import redact_pdf, redact_pdf_pipeline


def _make_dummy_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 100), "Confidential: Dr. Ramesh Kumar, Phone: 9876543210")
    b = doc.tobytes()
    doc.close()
    return b


def test_redact_pdf_expunges_content():
    data = _make_dummy_pdf()
    from redact.extract.pdf import to_normalized

    norm_doc = to_normalized(data)
    assert "9876543210" in norm_doc.text

    # Redact phone number
    phone_start = norm_doc.text.index("9876543210")
    phone_end = phone_start + len("9876543210")
    ent = Entity(type="PHONE", start=phone_start, end=phone_end, score=1.0, source="regex")

    redacted_bytes = redact_pdf(data, [ent], norm_doc)
    assert len(redacted_bytes) > 0

    # Verify content is expunged from the new PDF
    doc_after = pymupdf.open(stream=redacted_bytes, filetype="pdf")
    text_after = doc_after[0].get_text()
    doc_after.close()

    assert "9876543210" not in text_after
    assert "Confidential:" in text_after


def test_redact_pdf_pipeline_end_to_end():
    data = _make_dummy_pdf()
    redacted_bytes, summary = redact_pdf_pipeline(data, level=1)

    assert len(redacted_bytes) > 0
    assert summary["total_redacted"] >= 1

    doc_after = pymupdf.open(stream=redacted_bytes, filetype="pdf")
    text_after = doc_after[0].get_text()
    doc_after.close()

    # Direct identifiers should be removed
    assert "9876543210" not in text_after
