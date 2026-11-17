"""RE-DACT detection package.

Conforms to AGENTS.md section 5:
    def detect(doc_text: str, threshold: float = 0.4) -> list[Entity]: ...
    # runs all detectors + merge()
"""

from __future__ import annotations

from redact.entity import Entity
from redact.detect.gliner_ner import detect_gliner
from redact.detect.merge import merge

from redact.detect.regex_rules import find as find_regex


def detect(doc_text: str, threshold: float = 0.4) -> list[Entity]:
    """Run all active detectors on document text and merge overlapping spans.

    Signature contract: def detect(doc_text: str, threshold: float = 0.4) -> list[Entity]
    """
    if not doc_text or not doc_text.strip():
        return []

    all_ents: list[Entity] = []

    # 1. Zero-shot GLiNER detector (names, places, orgs, dates, ages, etc.)
    gliner_ents = detect_gliner(doc_text, threshold=threshold)
    all_ents.extend(gliner_ents)

    # 2. Regex + checksum + context-word detector (Alan's module)
    regex_ents = find_regex(doc_text)
    all_ents.extend(regex_ents)

    # 3. Merge overlapping spans (higher score wins, then longer span)
    return merge(all_ents)


__all__ = ["DEFAULT_LABELS", "IGNORE_LABELS", "detect", "detect_gliner", "merge"]
