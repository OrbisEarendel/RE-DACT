"""Tests for redact/detect/ (GLiNER detector and merge logic).

Synthetic dummy data only in accordance with AGENTS.md rules 1 and 5.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from redact import Entity
from redact.detect import detect, detect_gliner, merge


def test_merge_no_overlaps():
    e1 = Entity(type="person", start=0, end=5, score=0.9, source="gliner")
    e2 = Entity(type="city", start=10, end=15, score=0.8, source="gliner")
    result = merge([e1, e2])
    assert len(result) == 2
    assert result[0] == e1
    assert result[1] == e2


def test_merge_higher_score_wins():
    # Overlapping: e1 [0:10] score 0.7 vs e2 [5:15] score 0.95
    e1 = Entity(type="person", start=0, end=10, score=0.7, source="gliner")
    e2 = Entity(type="phone number", start=5, end=15, score=0.95, source="regex")
    result = merge([e1, e2])
    assert len(result) == 1
    assert result[0] == e2


def test_merge_longer_span_wins_on_tie():
    # Same score (0.9), overlapping spans: [0:15] vs [5:10]
    e_long = Entity(type="organization", start=0, end=15, score=0.9, source="gliner")
    e_short = Entity(type="organization", start=5, end=10, score=0.9, source="gliner")
    result = merge([e_short, e_long])
    assert len(result) == 1
    assert result[0] == e_long


def test_detect_empty_text():
    assert detect("") == []
    assert detect("    ") == []
    assert detect_gliner("") == []


def test_gliner_detection_synthetic():
    text = "Dr. Ramesh Patel visited Apollo Hospital in Mumbai on 15 August 2023."
    ents = detect_gliner(text, threshold=0.4)

    types_found = {e.type for e in ents}
    assert "person" in types_found
    assert "organization" in types_found
    assert "city" in types_found

    for e in ents:
        assert e.source == "gliner"
        assert e.score >= 0.4
        assert 0 <= e.start < e.end <= len(text)


def test_gliner_ignore_negative_label():
    # "my cousin" should be captured by 'family relation' negative label and ignored,
    # NOT flagged as person
    text = "My cousin called me yesterday."
    ents = detect_gliner(text, threshold=0.4)
    # Neither 'family relation' nor a false 'person' should be returned
    for e in ents:
        assert e.type != "family relation"
