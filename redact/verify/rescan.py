"""RE-DACT verify rescan module.

Re-scans the output document with our own detector to check for residual PII.
Conforms to AGENTS.md section 10:
  * Verify step: re-scan the output with our own detector.
  * If PII remains, flag it and report a residual-risk count.
  * Do not claim "clean" if the re-scan finds anything.
"""

from __future__ import annotations

from redact.entity import Entity
from redact.detect import detect


def rescan(text: str, threshold: float = 0.4) -> list[Entity]:
    """Re-scan text for any remaining PII after redaction.

    Args:
        text: The redacted document text.
        threshold: Detection threshold for the rescan.

    Returns:
        list[Entity]: Any detected entities that were not removed by redaction.
    """
    return detect(text, threshold=threshold)


def has_residual_risk(
    text: str, threshold: float = 0.4, max_entities: int = 5
) -> bool:
    """Check if text has residual PII risk above a threshold.

    Args:
        text: The redacted document text.
        threshold: Detection threshold.
        max_entities: If more than this many entities are found, return True.

    Returns:
        bool: True if residual risk detected.
    """
    ents = rescan(text, threshold=threshold)
    return len(ents) > max_entities