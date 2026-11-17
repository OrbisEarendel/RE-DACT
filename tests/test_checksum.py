import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from redact.detect.checksum import verhoeff_check_digit, verhoeff_valid  # noqa: E402


def test_known_vector():
    # Classic worked example: check digit of 236 is 3.
    assert verhoeff_check_digit("236") == "3"
    assert verhoeff_valid("2363")
    assert not verhoeff_valid("2364")


@pytest.mark.parametrize("payload", ["22222222222", "23456789012", "98765432101", "7", "10000000000"])
def test_generated_numbers_validate(payload):
    assert verhoeff_valid(payload + verhoeff_check_digit(payload))


def test_every_single_digit_error_is_caught():
    good = "22222222222" + verhoeff_check_digit("22222222222")
    for i in range(len(good)):
        for d in "0123456789":
            if d != good[i]:
                assert not verhoeff_valid(good[:i] + d + good[i + 1:])


def test_every_adjacent_transposition_is_caught():
    good = "23456789012" + verhoeff_check_digit("23456789012")
    for i in range(len(good) - 1):
        if good[i] != good[i + 1]:
            swapped = good[:i] + good[i + 1] + good[i] + good[i + 2:]
            assert not verhoeff_valid(swapped)


def test_rejects_non_ascii_digits_and_junk():
    assert not verhoeff_valid("")
    assert not verhoeff_valid("23 63")
    assert not verhoeff_valid("236a")
    assert not verhoeff_valid("२३६३")  # Devanagari digits
    with pytest.raises(ValueError):
        verhoeff_check_digit("12a")


# ------------------------------------------------------------------ Luhn / GSTIN
from redact.detect.checksum import (  # noqa: E402
    gstin_check_char, gstin_valid, luhn_check_digit, luhn_valid,
)


def test_luhn_known_vectors():
    # Public payment-network test numbers (not real accounts).
    for good in ["4111111111111111", "5555555555554444", "378282246310005", "490154203237518"]:
        assert luhn_valid(good)
    assert not luhn_valid("4111111111111112")


@pytest.mark.parametrize("payload", ["411111111111111", "37828224631000", "1", "79927398713"[:-1]])
def test_luhn_generated_numbers_validate(payload):
    assert luhn_valid(payload + luhn_check_digit(payload))


def test_luhn_catches_every_single_digit_error():
    good = "4111111111111111"
    for i in range(len(good)):
        for d in "0123456789":
            if d != good[i]:
                assert not luhn_valid(good[:i] + d + good[i + 1:])


def test_luhn_rejects_junk():
    assert not luhn_valid("")
    assert not luhn_valid("4111 1111")
    assert not luhn_valid("௪௧௧௧")  # Tamil digits
    with pytest.raises(ValueError):
        luhn_check_digit("12a")


def test_gstin_checksum():
    first14 = "27AAPFU0939F1Z"
    assert gstin_valid(first14 + gstin_check_char(first14))
    assert gstin_valid("27AAPFU0939F1ZV")
    assert not gstin_valid("27AAPFU0939F1ZW")
    assert not gstin_valid("27AAPFU0939F1Z")          # too short
    assert gstin_valid(("27aapfu0939f1z" + gstin_check_char(first14)).lower())  # case-insensitive
    with pytest.raises(ValueError):
        gstin_check_char("short")
