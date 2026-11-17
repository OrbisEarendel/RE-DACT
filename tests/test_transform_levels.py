from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from redact.entity import Entity
from redact.detect import regex_types as T
from redact.transform.levels import apply


def test_l1_masks_person():
    text = "Name: Alan Lobo"
    assert apply(text, [Entity(T.PERSON, 6, 15)], 1) == "Name: [PERSON]"


def test_l1_masks_phone_retaining_last_four():
    text = "Phone: 9876543210"
    assert apply(text, [Entity(T.PHONE, 7, 17)], 1) == "Phone: XXXXXX3210"


def test_l2_generalizes_age():
    text = "Age: 34"
    assert apply(text, [Entity(T.AGE, 5, 7)], 2) == "Age: 30s"


def test_l2_generalizes_date():
    text = "DOB: 14/08/1992"
    assert apply(text, [Entity(T.DATE_OF_BIRTH, 5, 15)], 2) == "DOB: Aug 1992"


def test_l2_also_masks_direct_identifiers():
    text = "Alan Lobo is 34"
    ents = [Entity(T.PERSON, 0, 9), Entity(T.AGE, 13, 15)]
    assert apply(text, ents, 2) == "[PERSON] is 30s"


def test_l1_does_not_generalize_age():
    text = "Age: 34"
    assert apply(text, [Entity(T.AGE, 5, 7)], 1) == text


def test_invalid_level_rejected():
    with pytest.raises(ValueError):
        apply("text", [], 3)


def test_invalid_offsets_rejected():
    with pytest.raises(ValueError):
        apply("text", [Entity(T.PERSON, 0, 99)], 1)


def test_overlaps_choose_higher_score():
    text = "Alan Lobo"
    ents = [Entity(T.PERSON, 0, 9, score=0.9),
            Entity(T.PERSON, 0, 4, score=0.5)]
    assert apply(text, ents, 1) == "[PERSON]"
