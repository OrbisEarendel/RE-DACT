"""RE-DACT L1/L2 text transformer.

Consumes redact.entity.Entity spans and redact.detect.regex_types labels.
L1 masks direct identifiers. L2 additionally generalizes quasi-identifiers.
This module performs transformations only; it does not detect entities.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Mapping

from redact.entity import Entity
from redact.detect import regex_types as T
from policy.policy import canonical


L1_TYPES = {
    T.AADHAAR, T.AADHAAR_VID, T.PAN, T.PASSPORT, T.VOTER_ID,
    T.DRIVING_LICENCE, T.VEHICLE_REG, T.GSTIN, T.ABHA_ID, T.USN,
    T.PHONE, T.EMAIL, T.SOCIAL_PROFILE, T.SOCIAL_HANDLE, T.IFSC,
    T.BANK_ACCOUNT, T.UPI_ID, T.CARD_NUMBER, T.CARD_EXPIRY, T.CVV,
    T.IP_ADDRESS, T.MAC_ADDRESS, T.IMEI, T.PERSON,
}

L2_TYPES = {
    T.DATE, T.DATE_OF_BIRTH, T.AGE, T.AGE_MINOR, T.JOB_TITLE,
    T.FINANCIAL_INFO, T.GENDER, T.BLOOD_GROUP, T.RELIGION,
    T.CASTE, T.DISABILITY, T.HEALTH_INFO,
}


def _token(entity_type: str) -> str:
    return f"[{entity_type}]"


def _mask(entity_type: str, value: str) -> str:
    """Mask values, retaining only the final four digits for numeric IDs."""
    if entity_type in {T.PHONE, T.AADHAAR, T.AADHAAR_VID, T.BANK_ACCOUNT,
                       T.CARD_NUMBER, T.USN}:
        digits = re.sub(r"\D", "", value)
        if len(digits) > 4:
            return "X" * (len(digits) - 4) + digits[-4:]
    return _token(entity_type)


def _generalize(entity_type: str, value: str) -> str:
    if entity_type in {T.AGE, T.AGE_MINOR}:
        match = re.search(r"\d+", value)
        if match:
            age = int(match.group())
            if age < 18:
                return "Child"
            return f"{(age // 10) * 10}s"
        return "[AGE]"

    if entity_type in {T.DATE, T.DATE_OF_BIRTH}:
        formats = ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
                   "%Y-%m-%d", "%d/%m/%y")
        for fmt in formats:
            try:
                return datetime.strptime(value.strip(), fmt).strftime("%b %Y")
            except ValueError:
                pass
        return "[DATE]"

    if entity_type == T.JOB_TITLE:
        lowered = value.casefold()
        if any(x in lowered for x in ("doctor", "surgeon", "physician")):
            return "Doctor"
        if any(x in lowered for x in ("engineer", "developer", "programmer")):
            return "Technical Professional"
        if any(x in lowered for x in ("manager", "director", "executive")):
            return "Management Professional"
        return "Professional"

    # Sensitive quasi-identifiers are generalized to a category token.
    return f"[GENERALIZED_{entity_type}]"


def apply(text: str, ents: list[Entity], level: int,
          mapping: Mapping | None = None) -> str:
    """Transform detected spans in ``text`` for privacy level 1 or 2.

    Args:
        text: Original normalized text.
        ents: Entity spans with offsets into ``text``.
        level: 1 (mask direct identifiers) or 2 (L1 + generalization).
        mapping: Reserved by the shared project contract; unused in L1/L2.

    Returns:
        Transformed text. Replacements are applied right-to-left so offsets
        remain valid. Overlapping spans are resolved by score, then length.

    Raises:
        TypeError: If text is not a string.
        ValueError: If level or any entity offsets are invalid.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if level not in (1, 2):
        raise ValueError("levels.py currently implements L1 and L2 only")

    candidates: list[tuple[int, int, float, str]] = []
    for ent in ents:
        if not (isinstance(ent.start, int) and isinstance(ent.end, int)
                and 0 <= ent.start < ent.end <= len(text)):
            raise ValueError("Entity contains invalid text offsets")
        value = text[ent.start:ent.end]
        ctype = canonical(ent.type)
        if ctype in L1_TYPES:
            replacement = _mask(ctype, value)
        elif level >= 2 and ctype in L2_TYPES:
            replacement = _generalize(ctype, value)
        else:
            continue
        candidates.append((ent.start, ent.end, float(ent.score), replacement))

    # Highest confidence wins; for ties, prefer the longer span.
    candidates.sort(key=lambda x: (-x[2], -(x[1] - x[0]), x[0]))
    selected: list[tuple[int, int, str]] = []
    for start, end, _score, replacement in candidates:
        if any(start < old_end and end > old_start
               for old_start, old_end, _ in selected):
            continue
        selected.append((start, end, replacement))

    result = text
    for start, end, replacement in sorted(selected, key=lambda x: x[0], reverse=True):
        result = result[:start] + replacement + result[end:]
    return result
