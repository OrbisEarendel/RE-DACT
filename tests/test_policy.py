"""Tests for policy/policy.py

Covers: level filtering, type normalisation, enabled_types override,
        ignore list, describe(), and child-type edge cases.
Synthetic dummy data only. AGENTS.md rules 1 and 5.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from redact.entity import Entity
from policy.policy import select, describe, canonical, ALL_PII_TYPES, LEVEL_TABLE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ent(type_: str, source: str = "regex", score: float = 1.0) -> Entity:
    return Entity(type=type_, start=0, end=5, score=score, source=source)


# ---------------------------------------------------------------------------
# canonical() — type normalisation
# ---------------------------------------------------------------------------

def test_canonical_uppercase_passthrough():
    assert canonical("AADHAAR") == "AADHAAR"
    assert canonical("PERSON") == "PERSON"
    assert canonical("[PHOTO]") == "[PHOTO]"


def test_canonical_gliner_lowercase():
    assert canonical("person") == "PERSON"
    assert canonical("phone number") == "PHONE"
    assert canonical("address") == "ADDRESS"
    assert canonical("medical condition") == "HEALTH_INFO"
    assert canonical("date of birth") == "DATE_OF_BIRTH"
    assert canonical("job title") == "JOB_TITLE"


def test_canonical_unknown_uppercases():
    # Unknown types are upper-cased as-is so they fall through gracefully
    assert canonical("some_custom_type") == "SOME_CUSTOM_TYPE"


# ---------------------------------------------------------------------------
# select() — level filtering
# ---------------------------------------------------------------------------

def test_l1_only_at_level_1():
    ents = [
        ent("AADHAAR"),       # L1
        ent("PAN"),           # L1
        ent("DATE"),          # L2 — should be excluded
        ent("ORGANIZATION"),  # L3 — should be excluded
    ]
    result = select(ents, level=1)
    types = {e.type for e in result}
    assert "AADHAAR" in types
    assert "PAN" in types
    assert "DATE" not in types
    assert "ORGANIZATION" not in types


def test_l2_includes_l1_and_l2():
    ents = [
        ent("PHONE"),        # L1
        ent("AGE"),          # L2
        ent("CITY"),         # L3 — excluded
    ]
    result = select(ents, level=2)
    types = {e.type for e in result}
    assert "PHONE" in types
    assert "AGE" in types
    assert "CITY" not in types


def test_l3_includes_all_up_to_l3():
    ents = [ent("EMAIL"), ent("DATE"), ent("ADDRESS"), ent("ORGANIZATION")]
    result = select(ents, level=3)
    types = {e.type for e in result}
    assert types == {"EMAIL", "DATE", "ADDRESS", "ORGANIZATION"}


def test_l4_includes_everything():
    all_ents = [ent(t) for t in LEVEL_TABLE]
    result = select(all_ents, level=4)
    assert len(result) == len(all_ents)


def test_empty_input_returns_empty():
    assert select([], level=1) == []
    assert select([], level=4) == []


def test_invalid_level_raises():
    with pytest.raises(ValueError):
        select([ent("PERSON")], level=0)
    with pytest.raises(ValueError):
        select([ent("PERSON")], level=5)


# ---------------------------------------------------------------------------
# Type normalisation through select()
# ---------------------------------------------------------------------------

def test_gliner_lowercase_types_normalised():
    """GLiNER emits 'person', 'phone number' — policy must still select them."""
    ents = [
        ent("person", source="gliner", score=0.95),
        ent("phone number", source="gliner", score=0.90),
        ent("date", source="gliner", score=0.80),   # L2
    ]
    result_l1 = select(ents, level=1)
    result_l2 = select(ents, level=2)

    l1_types = {e.type for e in result_l1}
    l2_types = {e.type for e in result_l2}

    assert "person" in l1_types       # original type preserved on Entity
    assert "phone number" in l1_types
    assert "date" not in l1_types
    assert "date" in l2_types


def test_visual_pii_at_level_1():
    """[PHOTO] and [QR] are L1 (IT Rules 2011 Rule 3(vi) biometric)."""
    ents = [ent("[PHOTO]"), ent("[QR]")]
    result = select(ents, level=1)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Ignore list
# ---------------------------------------------------------------------------

def test_family_relation_ignored():
    ents = [ent("family relation", source="gliner"), ent("PERSON")]
    result = select(ents, level=4)
    types = {e.type for e in result}
    assert "family relation" not in types
    assert "PERSON" in types


# ---------------------------------------------------------------------------
# enabled_types override
# ---------------------------------------------------------------------------

def test_enabled_types_restricts_selection():
    ents = [ent("AADHAAR"), ent("PAN"), ent("PHONE")]
    # User only ticked Aadhaar
    result = select(ents, level=1, enabled_types={"AADHAAR"})
    assert len(result) == 1
    assert result[0].type == "AADHAAR"


def test_enabled_types_none_uses_level_table():
    ents = [ent("AADHAAR"), ent("PAN"), ent("DATE")]
    result = select(ents, level=1, enabled_types=None)
    types = {e.type for e in result}
    # DATE is L2, should be excluded; AADHAAR + PAN included
    assert "AADHAAR" in types
    assert "PAN" in types
    assert "DATE" not in types


def test_enabled_types_empty_set_selects_nothing():
    ents = [ent("AADHAAR"), ent("PHONE")]
    result = select(ents, level=4, enabled_types=set())
    assert result == []


# ---------------------------------------------------------------------------
# describe()
# ---------------------------------------------------------------------------

def test_describe_returns_active_types():
    d = describe(1)
    assert d["level"] == 1
    assert "AADHAAR" in d["active_types"]
    assert "DATE" not in d["active_types"]    # L2
    assert "ORGANIZATION" not in d["active_types"]  # L3


def test_describe_l3_includes_l1_and_l2():
    d = describe(3)
    assert "AADHAAR" in d["active_types"]     # L1
    assert "DATE" in d["active_types"]        # L2
    assert "ORGANIZATION" in d["active_types"]  # L3


def test_describe_has_legal_basis():
    for level in range(1, 5):
        d = describe(level)
        assert len(d["legal_basis"]) >= 1
        assert any("DPDP" in b for b in d["legal_basis"])
