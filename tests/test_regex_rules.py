"""USN, Aadhaar and PAN detectors. Dummy data only: Aadhaar-shaped numbers are generated
from obviously fake payloads, never real ones."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from redact.detect.checksum import verhoeff_check_digit  # noqa: E402
from redact.detect.regex_rules import find, find_aadhaar, find_pan, find_usn  # noqa: E402
from redact.entity import Entity  # noqa: E402


def make_aadhaar(payload11: str, group: str = " ") -> str:
    n = payload11 + verhoeff_check_digit(payload11)
    return group.join([n[:4], n[4:8], n[8:]])


A1 = make_aadhaar("22222222222")            # 2222 2222 2226-style dummy
A2 = make_aadhaar("23456789012", "")        # 12 contiguous digits
A3 = make_aadhaar("98765432101", "-")       # hyphen grouped


def spans(text, ents):
    return [(e.type, text[e.start:e.end]) for e in ents]


# ---------------------------------------------------------------- Entity shape

def test_entity_fields():
    text = f"x {A1} y"
    (e,) = find_aadhaar(text)
    assert isinstance(e, Entity)
    assert (e.type, e.score, e.source) == ("AADHAAR", 1.0, "regex")
    assert text[e.start:e.end] == A1


# ---------------------------------------------------------------------- Aadhaar

@pytest.mark.parametrize("num", [A1, A2, A3])
def test_aadhaar_true_positive_all_groupings(num):
    text = f"Aadhaar: {num}."
    assert spans(text, find_aadhaar(text)) == [("AADHAAR", num)]


def test_aadhaar_invalid_checksum_not_matched():
    bad_last = "0" if A1[-1] != "0" else "1"
    assert find_aadhaar(f"No {A1[:-1] + bad_last} here") == []


@pytest.mark.parametrize("text", [
    "0123 4567 8901",                       # starts with 0
    "1234 5678 9012",                       # starts with 1
    "9876543210",                           # 10-digit phone
    "+91 98765 43210",                      # phone with country code
    "2345 6789 012",                        # only 11 digits
    "98765432109876",                       # 14 digits in a row
    # The next four contain a checksum-valid Aadhaar next to other digits. They must not match,
    # otherwise 16-digit card numbers and similar would be reported as Aadhaar.
    f"{A1} 4567",                           # card-style 16-digit number
    f"12 {A1}",                             # digit group glued on the left
    f"ref 12 {A1} 7",                       # glued on both sides
    f"7-{A1}",                              # hyphen-joined to a digit on the left
])
def test_aadhaar_near_misses(text):
    assert find_aadhaar(text) == []


def test_aadhaar_messy_context():
    text = f"UID:{A1}, alt ({A2}); also {A3}\nNext line"
    assert [t for _, t in spans(text, find_aadhaar(text))] == [A1, A2, A3]


def test_aadhaar_inside_longer_digit_run_is_ignored():
    # 12 valid digits glued to extra digits must not match.
    assert find_aadhaar("9" + A2) == []
    assert find_aadhaar(A2 + "9") == []


def test_aadhaar_unicode_digits_not_matched():
    kannada = "".join(chr(0x0CE6 + int(d)) for d in A2)
    assert find_aadhaar(kannada) == []


# ------------------------------------------------------------------------- PAN

@pytest.mark.parametrize("pan", ["ABCDE1234F", "AAAPL1234C", "BNZPM2501F"])
def test_pan_true_positive(pan):
    text = f"PAN: {pan}"
    assert spans(text, find_pan(text)) == [("PAN", pan)]


def test_pan_lowercase_and_mixed_case():
    text = "pan abcde1234f / AbCdE1234f"
    assert [t for _, t in spans(text, find_pan(text))] == ["abcde1234f", "AbCdE1234f"]


@pytest.mark.parametrize("text", [
    "ABCD1234E",          # 4 letters
    "ABCDE123F",          # 3 digits
    "ABCDE12345",         # no final letter
    "ABCDE1234FG",        # trailing letter
    "XABCDE1234F",        # leading extra letter
    "ABCDE-1234-F",       # split by hyphens
    "12345ABCDE",         # wrong order
])
def test_pan_near_misses(text):
    assert find_pan(text) == []


def test_pan_messy_context():
    text = "(ABCDE1234F),PAN=BNZPM2501F\tand\nAAAPL1234C."
    assert [t for _, t in spans(text, find_pan(text))] == ["ABCDE1234F", "BNZPM2501F", "AAAPL1234C"]


# ------------------------------------------------------------------------- USN

@pytest.mark.parametrize("usn", ["4SO25CS017", "4so25cs017", "1BM19CS001", "1RV21ISE045", "4SO24MBA012"])
def test_usn_true_positive(usn):
    text = f"USN: {usn}"
    assert spans(text, find_usn(text)) == [("USN", usn)]


@pytest.mark.parametrize("usn", ["4SO 25 CS 017", "4SO-25-CS-017", "4so25 cs017"])
def test_usn_with_separators(usn):
    text = f"Student {usn} passed"
    assert spans(text, find_usn(text)) == [("USN", usn)]


@pytest.mark.parametrize("text", [
    "4SO25CS17",          # roll number has 2 digits
    "4SO25CS0178",        # roll number has 4 digits
    "5SO25CS017",         # college digit outside 1-4
    "0SO25CS017",
    "4SO25C017",          # 1 branch letter
    "4SO25CSEE017",       # 4 branch letters
    "4S25CS017",          # 1 college letter
    "14SO25CS017",        # glued to a leading digit
    "X4SO25CS017",        # glued to a leading letter
    "4SO25CS017X",        # trailing letter
    "4SO2025CS017",       # 4-digit year
])
def test_usn_near_misses(text):
    assert find_usn(text) == []


def test_usn_messy_context():
    text = "Name:Rahul;USN=4so25cs017,roll (1BM19CS001).\nmail 4so25cs017@college.example"
    assert [t for _, t in spans(text, find_usn(text))] == ["4so25cs017", "1BM19CS001", "4so25cs017"]


# -------------------------------------------------------------------- combined

def test_find_returns_all_types_sorted_with_correct_offsets():
    text = f"Rahul 4SO25CS017 | PAN ABCDE1234F | Aadhaar {A1} | phone 9876543210"
    ents = find(text)
    assert [e.type for e in ents] == ["USN", "PAN", "AADHAAR", "PHONE"]
    assert [e.start for e in ents] == sorted(e.start for e in ents)
    assert [text[e.start:e.end] for e in ents] == ["4SO25CS017", "ABCDE1234F", A1, "9876543210"]


def test_no_overlaps_between_detectors_on_mixed_text():
    text = f"4SO25CS017 ABCDE1234F {A1} {A2}"
    ents = find(text)
    for a, b in zip(ents, ents[1:]):
        assert a.end <= b.start


def test_empty_and_plain_text():
    assert find("") == []
    assert find("Nothing sensitive in this sentence at all.") == []


def test_detectors_do_not_mutate_or_log(capsys):
    text = f"USN 4SO25CS017 PAN ABCDE1234F Aadhaar {A1}"
    before = text
    find(text)
    out = capsys.readouterr()
    assert text == before and out.out == "" and out.err == ""
