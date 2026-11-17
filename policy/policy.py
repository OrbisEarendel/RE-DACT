"""RE-DACT Policy Engine — policy/policy.py

Decides WHAT counts as PII and AT WHICH level, based on Indian law:
  - DPDP Act 2023 (No. 22 of 2023) — §2(t), §2(c), §9, §15(c)
  - IT (SPDI) Rules 2011 — Rule 3

Reference: policy/refs/PII_LEGAL_REFERENCE.md
           policy/refs/DPDP_Act_2023_Official_Gazette.pdf

Contract (AGENTS.md §5):
    def select(ents: list[Entity], level: int,
               enabled_types: set[str] | None = None) -> list[Entity]: ...

Nothing here logs, prints or stores entity text — types and counts only.
"""

from __future__ import annotations

from redact.entity import Entity

# ---------------------------------------------------------------------------
# Type normalisation: GLiNER emits lowercase strings, regex emits UPPER_CASE.
# Map GLiNER labels → canonical type names so the policy table is one list.
# ---------------------------------------------------------------------------
_GLINER_NORM: dict[str, str] = {
    "person":            "PERSON",
    "address":           "ADDRESS",
    "city":              "CITY",
    "organisation":      "ORGANIZATION",
    "organization":      "ORGANIZATION",
    "phone number":      "PHONE",
    "phone":             "PHONE",
    "email":             "EMAIL",
    "email address":     "EMAIL",
    "date":              "DATE",
    "date of birth":     "DATE_OF_BIRTH",
    "age":               "AGE",
    "job title":         "JOB_TITLE",
    "medical condition": "HEALTH_INFO",
    "health":            "HEALTH_INFO",
    "gender":            "GENDER",
    "blood group":       "BLOOD_GROUP",
    "religion":          "RELIGION",
    "caste":             "CASTE",
    "disability":        "DISABILITY",
    "financial info":    "FINANCIAL_INFO",
    "ip address":        "IP_ADDRESS",
    "url":               "SOCIAL_PROFILE",
    # visual (already canonical)
    "[PHOTO]":           "[PHOTO]",
    "[QR]":              "[QR]",
}


def canonical(entity_type: str) -> str:
    """Return the canonical upper-case type name for any entity type string."""
    return _GLINER_NORM.get(entity_type.lower(), entity_type.upper())


# ---------------------------------------------------------------------------
# PII Level Table — grounded in Indian law.
#
# Level semantics (cumulative):
#   L1 → act on L1 types only
#   L2 → act on L1 + L2 types
#   L3 → act on L1 + L2 + L3 types
#   L4 → act on everything (all types in this table)
#
# Sources per type are documented in policy/refs/PII_LEGAL_REFERENCE.md.
# ---------------------------------------------------------------------------

# L1 — Direct identifiers
#   DPDP §15(c): "unique identifier / proof of identity / proof of address issued by the State"
#   IT Rules 2011 Rule 3(ii): financial information
#   IT Rules 2011 Rule 3(vi): biometric (face, QR)
_L1 = {
    # State-issued identifiers (DPDP §15(c))
    "AADHAAR",          # 12-digit UID, Verhoeff checksum — Aadhaar Act 2016 §29 also prohibits publishing
    "AADHAAR_VID",      # 16-digit virtual ID
    "PAN",              # Permanent Account Number
    "PASSPORT",         # Indian passport number
    "VOTER_ID",         # EPIC number
    "DRIVING_LICENCE",  # DL number
    "VEHICLE_REG",      # Vehicle registration plate (traceable via VAHAN)
    "GSTIN",            # GST Identification Number
    "ABHA_ID",          # Ayushman Bharat Health Account ID
    "USN",              # University Seat Number — uniquely identifies a student
    # Contact / online identifiers (DPDP §2(t))
    "PERSON",           # Full name of an individual
    "PHONE",            # Mobile / landline number
    "EMAIL",            # Email address
    "SOCIAL_PROFILE",   # LinkedIn, GitHub, Instagram profile URL
    "SOCIAL_HANDLE",    # @username on social platforms
    # Financial (IT Rules 2011 Rule 3(ii))
    "BANK_ACCOUNT",     # Bank account number
    "CARD_NUMBER",      # Credit / debit card (Luhn)
    "CARD_EXPIRY",      # Card expiry date
    "CVV",              # Card CVV
    "UPI_ID",           # UPI payment handle (e.g. name@bank)
    "IFSC",             # Bank IFSC code
    # Digital device identifiers (DPDP §2(t) online identifiers)
    "IP_ADDRESS",
    "MAC_ADDRESS",
    "IMEI",
    # Visual biometrics (IT Rules 2011 Rule 3(vi))
    "[PHOTO]",          # Face / portrait detected via OpenCV Haar cascade
    "[QR]",             # QR code (may encode Aadhaar biometric data)
}

# L2 — Quasi-identifiers + Sensitive attributes
#   DPDP §2(t): identifiable by combination
#   IT Rules 2011 Rule 3(iii): physical/physiological/mental health
#   IT Rules 2011 Rule 3(iv): sexual orientation
#   IT Rules 2011 Rule 3(v): medical records and history
#   DPDP §2(c) + §9: children (AGE_MINOR) — parental consent required
_L2 = {
    "DATE",             # Generic dates (can narrow identity by combination)
    "DATE_OF_BIRTH",    # DOB specifically
    "AGE",              # Age (quasi-identifier by combination)
    "AGE_MINOR",        # Age < 18 — DPDP §2(c), §9: child, highest risk flag
    "JOB_TITLE",        # Professional role (quasi-identifier)
    "FINANCIAL_INFO",   # General financial context (IT Rules Rule 3(ii))
    "GENDER",           # Gender / sexual orientation (IT Rules Rule 3(iv))
    "BLOOD_GROUP",      # Physical health condition (IT Rules Rule 3(iii))
    "HEALTH_INFO",      # Medical condition / history (IT Rules Rule 3(iii)(v))
    "DISABILITY",       # DPDP §2(j)(ii), §9: person with disability
    "RELIGION",         # Religion (identifiable by combination, DPDP §2(t))
    "CASTE",            # Caste / community (identifiable by combination)
}

# L3 — Location / Organisational quasi-identifiers
#   DPDP §15(c): "proof of address"
#   DPDP §2(t): identifiable by combination with L1/L2 data
_L3 = {
    "ADDRESS",          # Street / residential address (DPDP §15(c) proof of address)
    "CITY",             # City / district (narrows identity by combination)
    "PIN_CODE",         # Postal / PIN code
    "GEO_COORDINATES",  # Latitude / longitude
    "ORGANIZATION",     # Employer / institution (narrows identity by combination)
}

# L4 — Everything: same as L1+L2+L3, synthesised with realistic fake values
# (No new types — L4 changes the TRANSFORM, not the selection)

# Fast lookup: type → minimum level at which it is acted on
LEVEL_TABLE: dict[str, int] = {}
for _t in _L1:
    LEVEL_TABLE[_t] = 1
for _t in _L2:
    LEVEL_TABLE[_t] = 2
for _t in _L3:
    LEVEL_TABLE[_t] = 3

# AGE_MINOR override: always at L1 risk even though it triggers at L2
# (we still need level >= 2 to act on it, but it gets a warning flag at any level)
CHILD_TYPES = {"AGE_MINOR"}

# Types that are explicitly NOT PII — ignore list (family relations, common words etc.)
# GLiNER is configured to suppress "family relation" at detection time,
# but keep this here as a final gate.
IGNORE_TYPES = {"family relation", "FAMILY_RELATION"}

# All known PII types (for UI checkboxes)
ALL_PII_TYPES: frozenset[str] = frozenset(LEVEL_TABLE.keys())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def select(
    ents: list[Entity],
    level: int,
    enabled_types: set[str] | None = None,
) -> list[Entity]:
    """Filter entities to those that should be redacted at the given level.

    Args:
        ents:          All entities from detect().
        level:         Redaction level 1–4 (cumulative: L2 includes L1 types).
        enabled_types: Optional UI override — set of canonical type names the
                       user has ticked. If None, use the full level table.
                       If provided, only types in this set AND within the level
                       are acted on.

    Returns:
        Subset of ents to redact, in original order.
    """
    if not ents:
        return []
    if not 1 <= level <= 4:
        raise ValueError(f"level must be 1–4, got {level!r}")

    result = []
    for e in ents:
        # Normalise to canonical type name
        ctype = canonical(e.type)

        # Hard ignore list — never redact
        if ctype in IGNORE_TYPES or e.type in IGNORE_TYPES:
            continue

        # Level filter: type must have minimum level <= current level
        min_level = LEVEL_TABLE.get(ctype, 99)
        if min_level > level:
            continue

        # UI checkbox override: if the user specified types, honour them
        if enabled_types is not None and ctype not in enabled_types:
            continue

        result.append(e)

    return result


def describe(level: int) -> dict:
    """Return a human-readable summary of what is acted on at this level.
    Used by the Streamlit UI and the audit report.
    """
    names = {
        1: "L1 — Light (direct identifiers only)",
        2: "L2 — Medium (+ quasi-identifiers & sensitive attributes)",
        3: "L3 — Strong (+ location & organisational data)",
        4: "L4 — Synthetic (everything, fully synthesised)",
    }
    active = sorted(t for t, lv in LEVEL_TABLE.items() if lv <= level)
    return {
        "level": level,
        "name": names.get(level, f"L{level}"),
        "active_types": active,
        "count": len(active),
        "legal_basis": [
            "DPDP Act 2023 (No. 22 of 2023) §2(t), §2(c), §9, §15(c)",
            "IT (SPDI) Rules 2011, Rule 3",
        ],
    }
