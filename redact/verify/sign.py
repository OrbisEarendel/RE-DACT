"""RE-DACT verify sign module.

HMAC-SHA256 signing for tamper-evident reports.
Conforms to AGENTS.md section 10:
  * Signed report: HMAC-SHA256 over the report JSON using REDACT_HMAC_KEY.
  * Optionally chain each report's hash to the previous one (tamper-evident log).
"""

from __future__ import annotations

import hmac
import hashlib
import json
import os
from typing import Any, Dict


def sign_report(report_dict: dict, key: bytes) -> str:
    """Compute HMAC-SHA256 over a canonical report dict.

    The report dict is serialized with sorted keys and compact separators
    so the signature is deterministic and reproducible.

    Args:
        report_dict: Report dictionary to sign.
        key: HMAC key bytes (from REDACT_HMAC_KEY env var).

    Returns:
        str: Hex HMAC-SHA256 signature.
    """
    canonical = json.dumps(report_dict, sort_keys=True, separators=(",", ":"))
    return hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()


def chain_hash(previous: str, current: str) -> str:
    """Chain the current report hash to the previous one.

    Creates a tamper-evident link by hashing the concatenation of the
    previous hash and the current report's signed hash.

    Args:
        previous: Previous report's signed_hash.
        current: Current report's signed_hash.

    Returns:
        str: Chained hash value.
    """
    combined = previous + current
    return hashlib.sha256(combined.encode()).hexdigest()