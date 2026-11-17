"""Integration tests: detect() combining GLiNER + regex/checksum together.

Synthetic dummy data only. No real PII. AGENTS.md rules 1 and 5.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from redact.detect import detect


def test_regex_phone_surfaced_by_detect():
    """A synthetic Indian phone number must be caught by the combined detector."""
    text = "Call me at 9876543210 for more details."
    ents = detect(text, threshold=0.4)
    types = {e.type for e in ents}
    assert "PHONE" in types, f"Expected PHONE in {types}"


def test_regex_email_surfaced_by_detect():
    """A dummy email address must be caught by the combined detector."""
    text = "Send all documents to test.user@example.com before the deadline."
    ents = detect(text, threshold=0.4)
    types = {e.type for e in ents}
    assert "EMAIL" in types, f"Expected EMAIL in {types}"


def test_regex_pan_surfaced_by_detect():
    """A dummy PAN-format string must be caught by the combined detector."""
    text = "PAN card number ABCDE1234F was submitted."
    ents = detect(text, threshold=0.4)
    types = {e.type for e in ents}
    assert "PAN" in types, f"Expected PAN in {types}"


def test_regex_entities_have_correct_source():
    """Regex-sourced entities must have source='regex'."""
    text = "Contact: 9876543210"
    ents = detect(text, threshold=0.4)
    regex_ents = [e for e in ents if e.source == "regex"]
    assert regex_ents, "Expected at least one regex-sourced entity"


def test_detect_no_overlap_in_output():
    """detect() must return non-overlapping spans after merge."""
    text = "Dr. Ramesh Kumar, phone 9876543210, email test@example.com, PAN ABCDE1234F."
    ents = detect(text, threshold=0.4)
    for i, a in enumerate(ents):
        for j, b in enumerate(ents):
            if i != j:
                assert not (a.start < b.end and b.start < a.end), (
                    f"Overlap between {a} and {b}"
                )


def test_regex_and_gliner_both_contribute():
    """Both sources must appear in a rich document."""
    text = (
        "Student Priya Sharma can be reached at priya.sharma@college.edu "
        "or on 9123456780. She is studying at Mumbai University."
    )
    ents = detect(text, threshold=0.4)
    sources = {e.source for e in ents}
    assert "regex" in sources, "Regex detector did not contribute"
    assert "gliner" in sources, "GLiNER detector did not contribute"
