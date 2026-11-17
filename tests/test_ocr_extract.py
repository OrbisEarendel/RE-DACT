"""Tests for redact/extract/ocr.py and router integration.

Uses synthetic dummy data only in accordance with AGENTS.md rule 5.
Runs in-memory only in accordance with AGENTS.md rule 4.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2
import numpy as np
import pymupdf
import pytest
from PIL import Image, ImageDraw

from redact import (
    Engine,
    Format,
    NormalizedDoc,
    Word,
    extract,
    ocr,
    route,
    to_normalized,
)
from redact.extract.ocr import (
    _box_to_xywh,
    _split_line_into_words,
    words_to_normalized,
)
from redact.extract.pdf import to_normalized as pdf_to_normalized
from redact.extract.text import to_normalized as text_to_normalized


def _create_synthetic_image(text: str = "SAMPLE DUMMY 12345") -> np.ndarray:
    """Create a synthetic in-memory image with text."""
    img = np.ones((100, 450, 3), dtype=np.uint8) * 255
    cv2.putText(
        img,
        text,
        (20, 60),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        (0, 0, 0),
        2,
        cv2.LINE_AA,
    )
    return img


def test_box_to_xywh_formats():
    # 4-coordinate [x1, y1, x2, y2]
    x, y, w, h = _box_to_xywh([10, 20, 110, 60])
    assert (x, y, w, h) == (10, 20, 100, 40)

    # Inverted points
    x, y, w, h = _box_to_xywh([110, 60, 10, 20])
    assert (x, y, w, h) == (10, 20, 100, 40)

    # 4-point polygon [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
    poly = [[10, 20], [110, 20], [110, 60], [10, 60]]
    x, y, w, h = _box_to_xywh(poly)
    assert (x, y, w, h) == (10, 20, 100, 40)


def test_fallback_word_splitter():
    box = [10, 20, 110, 60]
    words = _split_line_into_words("John Doe 9999", box, conf=0.95, page=0)
    assert len(words) == 3
    assert [w.text for w in words] == ["John", "Doe", "9999"]
    for w in words:
        assert w.x >= 10
        assert w.y == 20
        assert w.h == 40
        assert w.conf == 0.95
        assert w.page == 0

    # Empty text
    assert _split_line_into_words("   ", box, 1.0, 0) == []


def test_words_to_normalized():
    w1 = Word(text="Jane", x=10, y=20, w=40, h=20, conf=0.99, page=0)
    w2 = Word(text="Smith", x=60, y=20, w=50, h=20, conf=0.98, page=0)
    w3 = Word(text="9876543210", x=10, y=50, w=100, h=20, conf=0.95, page=0)

    doc = words_to_normalized([w1, w2, w3])

    assert "Jane Smith" in doc.text
    assert "9876543210" in doc.text
    assert len(doc.spans) == 3

    # Check span character alignment
    for start, end, ref in doc.spans:
        assert doc.text[start:end] == ref.text


def test_ocr_numpy_array():
    img = _create_synthetic_image("TESTING OCR")
    words = ocr(img)
    assert len(words) >= 1
    found_texts = " ".join(w.text for w in words)
    assert "TESTING" in found_texts or "OCR" in found_texts

    for w in words:
        assert isinstance(w.text, str)
        assert w.w > 0
        assert w.h > 0
        assert 0.0 <= w.conf <= 1.0


def test_ocr_bytes_and_pil():
    img = _create_synthetic_image("PADDLE TEST")
    _, buf = cv2.imencode(".png", img)
    raw_bytes = buf.tobytes()

    # Test raw bytes
    words_from_bytes = ocr(raw_bytes)
    assert len(words_from_bytes) >= 1

    # Test PIL Image
    pil_img = Image.open(io.BytesIO(raw_bytes))
    words_from_pil = ocr(pil_img)
    assert len(words_from_pil) >= 1


def test_ocr_with_region():
    img = np.ones((200, 400, 3), dtype=np.uint8) * 255
    cv2.putText(img, "TOP TEXT", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    cv2.putText(img, "BOTTOM REGION", (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)

    # Crop only bottom half: region (0, 100, 400, 200)
    words = ocr(img, region=(0, 100, 400, 200))
    for w in words:
        assert w.y >= 100


def test_ocr_invalid_inputs():
    with pytest.raises(FileNotFoundError):
        ocr("/non/existent/path/image.png")

    with pytest.raises(ValueError):
        ocr(b"not an image data")

    with pytest.raises(TypeError):
        ocr(12345)  # type: ignore


def test_router_integration_image():
    img = _create_synthetic_image("ROUTER IMAGE 777")
    _, buf = cv2.imencode(".png", img)
    raw_bytes = buf.tobytes()

    doc, plan = extract(raw_bytes, filename="sample.png")
    assert plan.format == Format.IMAGE
    assert len(plan.ocr_units) >= 1
    assert len(doc.spans) >= 1
    assert any("ROUTER" in w.text or "IMAGE" in w.text for _, _, w in doc.spans)


def test_router_integration_plaintext():
    text_data = b"Patient Name: Dummy Patient\nAge: 40\nPhone: 9876543210"
    doc, plan = extract(text_data, filename="notes.txt")
    assert plan.format == Format.TEXT
    assert "Dummy Patient" in doc.text
    assert len(doc.spans) == 3


def test_router_integration_pdf():
    # Build a 2-page dummy PDF: page 0 native text, page 1 scanned image
    pdf_doc = pymupdf.open()

    # Page 0: Native text
    p0 = pdf_doc.new_page(width=500, height=200)
    p0.insert_text((50, 50), "Native Text Page Rahul Sharma 9876543210")

    # Page 1: Scanned image
    p1 = pdf_doc.new_page(width=500, height=200)
    img_syn = _create_synthetic_image("SCANNED OCR 555")
    _, buf = cv2.imencode(".png", img_syn)
    p1.insert_image(pymupdf.Rect(0, 0, 500, 200), stream=buf.tobytes())

    pdf_bytes = pdf_doc.tobytes()
    pdf_doc.close()

    # Extract via universal extractor connected to gate/router
    doc, plan = extract(pdf_bytes, filename="multipage.pdf")
    assert plan.format == Format.PDF
    assert len(plan.routes) == 2
    assert "Native" in doc.text or "Rahul" in doc.text
    assert len(doc.spans) >= 1
