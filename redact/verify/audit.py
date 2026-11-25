"""RE-DACT verify audit module.

Audit log storage - types, counts, level, and SHA-256 hashes only.
Conforms to AGENTS.md section 10:
  * Audit log / report stores types, counts, level, and SHA-256 hashes of input
    and output. No raw values.
"""

from __future__ import annotations

from redact.entity import Entity
from redact.verify.report import build_report, input_hash, output_hash


def audit_log(
    input_bytes: bytes,
    output_bytes: bytes,
    level: int,
    ents: list[Entity],
    residual: int = 0,
) -> dict:
    """Create an audit log entry (types and counts only, no raw PII).

    Args:
        input_bytes: Original input document bytes.
        output_bytes: Redacted output document bytes.
        level: Redaction level (1-4).
        ents: List of entities that were redacted.
        residual: Count of residual PII found on re-scan.

    Returns:
        dict: Audit log entry with hashes, level, counts - no raw values.
    """
    return build_report(
        input_text=input_bytes,
        output_text=output_bytes,
        level=level,
        ents=ents,
        residual=residual,
    )