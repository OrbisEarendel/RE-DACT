"""STUB detector so the pipeline runs on day one. Owner: P1 will replace/extend this."""
import re

from core.types import EMAIL, ID_NUMBER, PHONE, Span, TextUnit

PATTERNS = [
    (EMAIL, "email-basic", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    (PHONE, "phone-intl", re.compile(r"\+\d{1,3}[ -]?\d{5}[ -]?\d{5}")),
    (ID_NUMBER, "id-12-digit", re.compile(r"\b\d{4} \d{4} \d{4}\b")),
]


class StubDetector:
    def detect(self, units: list[TextUnit]) -> list[Span]:
        spans = []
        for i, unit in enumerate(units):
            for etype, rule_id, pattern in PATTERNS:
                for m in pattern.finditer(unit.text):
                    spans.append(Span(text=m.group(), start=m.start(), end=m.end(),
                                      type=etype, unit=i, source="rule", rule_id=rule_id))
        return spans
