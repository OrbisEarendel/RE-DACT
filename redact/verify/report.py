"""RE-DACT verify report module.

Builds audit reports with HMAC signature.
Conforms to AGENTS.md section 10:
  * Audit log / report stores types, counts, level, and SHA-256 hashes of input
    and output. No raw values.
  * Signed report: HMAC-SHA256 over the report JSON using REDACT_HMAC_KEY.
  * Optionally chain each report's hash to the previous one (tamper-evident log).
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Report:
    """Audit report for a redaction session."""

    input_hash: str          # SHA-256 of input
    output_hash: str         # SHA-256 of output
    level: int               # Redaction level (1-4)
    total_entities: int      # Total entities redacted
    entities_by_type: Dict[str, int]  # Count per type
    residual_risk: int       # Count of residual PII entities found on re-scan
    signed_hash: str         # HMAC-SHA256 of the report
    previous_chain_hash: Optional[str] = None  # For tamper-evident chain

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary for JSON serialization."""
        return {
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "level": self.level,
            "total_entities": self.total_entities,
            "entities_by_type": self.entities_by_type,
            "residual_risk": self.residual_risk,
            "signed_hash": self.signed_hash,
        }

    def to_json(self) -> str:
        """Serialize report to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


def input_hash(text: bytes) -> str:
    """Compute SHA-256 hash of input bytes.

    Args:
        text: Input bytes (document content).

    Returns:
        str: Hex SHA-256 hash.
    """
    return hashlib.sha256(text).hexdigest()


def output_hash(text: bytes) -> str:
    """Compute SHA-256 hash of output bytes.

    Args:
        text: Output bytes (redacted document content).

    Returns:
        str: Hex SHA-256 hash.
    """
    return hashlib.sha256(text).hexdigest()


def build_report(
    input_text: bytes,
    output_text: bytes,
    level: int,
    ents: list[Entity],
    residual: int = 0,
    previous_chain_hash: Optional[str] = None,
    hmac_key: Optional[bytes] = None,
) -> dict:
    """Build a signed audit report.

    Args:
        input_text: Original input bytes.
        output_text: Redacted output bytes.
        level: Redaction level (1-4).
        ents: List of entities that were redacted.
        residual: Count of residual PII found on re-scan.
        previous_chain_hash: Previous report's signed_hash for chaining.
        hmac_key: HMAC key from .env. If None, reads REDACT_HMAC_KEY env var.

    Returns:
        dict: Report dictionary (ready for JSON serialization).
    """
    # Compute hashes
    ih = input_hash(input_text)
    oh = output_hash(output_text)

    # Count entities by type
    entities_by_type: Dict[str, int] = {}
    for e in ents:
        etype = e.type
        entities_by_type[etype] = entities_by_type.get(etype, 0) + 1

    # Build report dict (no raw PII values, only types and counts)
    report_dict: Dict[str, Any] = {
        "input_hash": ih,
        "output_hash": oh,
        "level": level,
        "total_entities": len(ents),
        "entities_by_type": entities_by_type,
        "residual_risk": residual,
    }

    # Sign with HMAC-SHA256
    key = hmac_key or os.environ.get("REDACT_HMAC_KEY", "").encode()
    if key:
        signed = hmac_signed(report_dict, key)
        report_dict["signed_hash"] = signed
    else:
        report_dict["signed_hash"] = ""

    # Chain to previous report hash
    if previous_chain_hash:
        report_dict["previous_chain_hash"] = previous_chain_hash

    return report_dict


def hmac_signed(report_dict: dict, key: bytes) -> str:
    """Compute HMAC-SHA256 over a canonical report dict.

    Args:
        report_dict: Report dictionary (ordered keys).
        key: HMAC key bytes.

    Returns:
        str: Hex HMAC-SHA256 signature.
    """
    # Sort keys for canonical ordering
    canonical = json.dumps(report_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode(key if isinstance(key, bytes) else key.encode())).hexdigest()