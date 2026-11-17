"""Verhoeff check digit (used by Aadhaar). Pure functions, no I/O, no logging."""

# Multiplication table (dihedral group D5)
_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
# Permutation table
_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)
# Inverse table
_INV = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)

_DIGITS = frozenset("0123456789")


def _is_ascii_digits(s: str) -> bool:
    return bool(s) and all(ch in _DIGITS for ch in s)


def verhoeff_valid(number: str) -> bool:
    """True if `number` (ASCII digits only, check digit included) passes the Verhoeff check."""
    if not _is_ascii_digits(number):
        return False
    c = 0
    for i, ch in enumerate(reversed(number)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


def verhoeff_check_digit(payload: str) -> str:
    """Check digit to append to `payload` (ASCII digits, check digit NOT included)."""
    if not _is_ascii_digits(payload):
        raise ValueError("payload must be ASCII digits")
    c = 0
    for i, ch in enumerate(reversed(payload)):
        c = _D[c][_P[(i + 1) % 8][int(ch)]]
    return str(_INV[c])


# --------------------------------------------------------------------------- #
# Luhn (payment cards, IMEI)
# --------------------------------------------------------------------------- #
def luhn_valid(number: str) -> bool:
    """True if `number` (ASCII digits only, check digit included) passes the Luhn check."""
    if not _is_ascii_digits(number):
        return False
    total = 0
    for i, ch in enumerate(reversed(number)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def luhn_check_digit(payload: str) -> str:
    """Check digit to append to `payload` (ASCII digits, check digit NOT included)."""
    if not _is_ascii_digits(payload):
        raise ValueError("payload must be ASCII digits")
    for d in "0123456789":
        if luhn_valid(payload + d):
            return d
    raise AssertionError("unreachable")  # pragma: no cover


# --------------------------------------------------------------------------- #
# GSTIN check character (base-36, Luhn-mod-36 style), 15th character
# --------------------------------------------------------------------------- #
_GST_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_check_char(first14: str) -> str:
    """Check character for the first 14 characters of a GSTIN (upper-case alphanumerics)."""
    first14 = first14.upper()
    if len(first14) != 14 or any(ch not in _GST_CHARS for ch in first14):
        raise ValueError("need 14 alphanumeric characters")
    factor, total, n = 2, 0, 36
    for ch in reversed(first14):
        digit = factor * _GST_CHARS.index(ch)
        factor = 1 if factor == 2 else 2
        total += digit // n + digit % n
    return _GST_CHARS[(n - total % n) % n]


def gstin_valid(gstin: str) -> bool:
    gstin = gstin.upper()
    if len(gstin) != 15 or any(ch not in _GST_CHARS for ch in gstin):
        return False
    return gstin_check_char(gstin[:14]) == gstin[14]
