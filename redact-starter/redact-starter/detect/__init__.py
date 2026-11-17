"""Detection registry. Owner: P1.

To add a detector: write a class with detect(units) -> list[Span] and add it to DETECTORS.
All detectors run and their results are combined (union). Higher levels never detect less.
"""
import os

from core.types import Span, TextUnit
from detect.stub_detector import StubDetector

DETECTORS = [StubDetector()]  # P1: replace with a real RegexDetector (checksums, Verhoeff...)

if os.environ.get("REDACT_USE_GLINER") == "1":
    from detect.gliner_detector import GlinerDetector
    DETECTORS.append(GlinerDetector())


def run_detectors(units: list[TextUnit]) -> list[Span]:
    spans: list[Span] = []
    for d in DETECTORS:
        spans.extend(d.detect(units))
    return dedupe(spans)


def dedupe(spans: list[Span]) -> list[Span]:
    """Two detectors can find the same text. Keep one span per (unit, start, end),
    preferring rule-based findings (auditable) and then the higher confidence."""
    best: dict = {}
    for s in spans:
        key = (s.unit, s.start, s.end)
        cur = best.get(key)
        if cur is None or (s.source == "rule", s.confidence) > (cur.source == "rule", cur.confidence):
            best[key] = s
    return list(best.values())
