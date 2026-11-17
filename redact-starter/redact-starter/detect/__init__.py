"""Detection registry. Owner: P1.

To add a detector: write a class with detect(units) -> list[Span] and add it to DETECTORS.
All detectors run and their results are combined (union). Higher levels never detect less.
"""
from core.types import Span, TextUnit
from detect.stub_detector import StubDetector

DETECTORS = [StubDetector()]  # P1: add RegexDetector, NerDetector, ContextRules here


def run_detectors(units: list[TextUnit]) -> list[Span]:
    spans: list[Span] = []
    for d in DETECTORS:
        spans.extend(d.detect(units))
    return spans
