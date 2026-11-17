"""Tests for redact/writers/image.py and redact/detect/visual.py.

Uses synthetic dummy data in-memory only (AGENTS.md rule 4 & 5).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2
import numpy as np
import pytest

from redact import (
    Entity,
    NormalizedDoc,
    Word,
    detect_faces,
    detect_qrcodes,
    detect_visual_pii,
    redact_image,
)


def _make_canvas(w=300, h=100, fill=255) -> np.ndarray:
    """Create a solid color canvas."""
    return np.ones((h, w, 3), dtype=np.uint8) * fill


def test_redact_image_box_solid_black():
    img = _make_canvas(w=200, h=100, fill=255)  # all white canvas

    w1 = Word(text="John", x=20, y=20, w=40, h=20, conf=0.99, page=0)
    w2 = Word(text="Smith", x=70, y=20, w=40, h=20, conf=0.99, page=0)
    words = [w1, w2]

    doc = NormalizedDoc(
        text="John Smith",
        spans=[(0, 4, w1), (5, 10, w2)],
    )

    # Redact only "Smith"
    ents = [Entity(type="person", start=5, end=10, score=0.95, source="gliner")]

    redacted = redact_image(img, words, ents, doc, style="box")

    # The region for w1 ("John", x=20:60, y=20:40) should still be white
    assert np.all(redacted[20:40, 20:60] == 255)

    # The region for w2 ("Smith", x=70:110, y=20:40) must be solid black (0, 0, 0)
    assert np.all(redacted[20:40, 70:110] == 0)


def test_redact_image_photo_word():
    img = _make_canvas(w=200, h=100, fill=200)

    photo_word = Word(text="[PHOTO]", x=120, y=10, w=60, h=80, conf=0.99, page=0)
    words = [photo_word]
    doc = NormalizedDoc(text="", spans=[])
    ents: list[Entity] = []

    redacted = redact_image(img, words, ents, doc, style="box")

    # Photo box should be solid black
    assert np.all(redacted[10:90, 120:180] == 0)

    # Outside photo box should remain untouched
    assert np.all(redacted[10:90, 0:100] == 200)


def test_redact_image_blur_style():
    img = _make_canvas(w=100, h=100, fill=255)
    # Put a contrasting pattern inside the target box
    img[20:30, 20:40] = 0

    w = Word(text="Secret", x=20, y=20, w=20, h=20, conf=0.99, page=0)
    doc = NormalizedDoc(text="Secret", spans=[(0, 6, w)])
    ents = [Entity(type="secret", start=0, end=6, score=1.0, source="test")]

    redacted = redact_image(img, [w], ents, doc, style="blur")

    # The blurred area must differ from the sharp original
    assert not np.array_equal(redacted[20:40, 20:40], img[20:40, 20:40])


def test_visual_detectors_on_blank():
    img = _make_canvas(w=100, h=100, fill=255)
    faces = detect_faces(img)
    qrs = detect_qrcodes(img)
    all_vis = detect_visual_pii(img)

    assert isinstance(faces, list)
    assert isinstance(qrs, list)
    assert isinstance(all_vis, list)
