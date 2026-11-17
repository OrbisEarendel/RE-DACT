"""Regex + checksum detectors (AGENTS.md section 7) for Indian identifiers and digital IDs.

Every hit is an Entity with source "regex". Offsets are character offsets into the text you
pass in, so run this on the FULL joined string, never on single OCR words (numbers get split
across words, see AGENTS.md section 5).

Nothing here logs, prints or stores matched text.

Format/checksum detectors live in this file. Detectors that need a context word or a
"Label: value" shape live in context_rules.py. `find()` runs both and resolves overlaps.

Scores: 1.0 = strict format and/or checksum. Lower = weaker evidence (see each detector).
Entity type names: regex_types.py.
"""
from __future__ import annotations

import ipaddress
import re
import unicodedata

from redact.entity import Entity

from . import regex_types as T
from .checksum import gstin_valid, luhn_valid, verhoeff_valid

SOURCE = "regex"
SCORE = 1.0

# ASCII digits are written as [0-9], never \d. `find()` first maps other scripts' digits
# (Kannada, Devanagari, ...) to ASCII one-for-one, so offsets stay valid.

# Separator allowed between digit groups: one space, tab or hyphen.
_SEP = r"[ \t\-]?"
_L = r"(?<![A-Za-z0-9])"   # left guard for alphanumeric tokens
_R = r"(?![A-Za-z0-9])"    # right guard for alphanumeric tokens
# Guards for digit groups: not glued to another digit group, with or without a separator.
_DL = r"(?<![0-9])(?<![0-9][ \t\-])"
_DR = r"(?![ \t\-]?[0-9])"


def _ent(etype: str, m: re.Match, score: float = SCORE, group: int | str = 0) -> Entity:
    return Entity(etype, m.start(group), m.end(group), score, SOURCE)


def _digits_only(s: str) -> str:
    return "".join(ch for ch in s if "0" <= ch <= "9")


# --------------------------------------------------------------------------- #
# Aadhaar: 12 digits, first digit 2-9, optional grouping 4-4-4, Verhoeff check.
# The guards stop it matching inside longer digit runs, such as a 16-digit card
# number written as "1234 5678 9012 3456" (the first 12 digits would pass the
# checksum 1 time in 10 by chance).
# --------------------------------------------------------------------------- #
_AADHAAR_RE = re.compile(
    r"(?<![0-9])(?<![0-9][ \t\-])"
    r"[2-9][0-9]{3}" + _SEP + r"[0-9]{4}" + _SEP + r"[0-9]{4}"
    r"(?![ \t\-]?[0-9])"
)

# --------------------------------------------------------------------------- #
# PAN: 5 letters, 4 digits, 1 letter (AGENTS.md: [A-Z]{5}\d{4}[A-Z]).
# Case-insensitive because people type it in lowercase.
# The 4th letter (holder type) is NOT enforced: the standard dummy PAN
# "ABCDE1234F" has an invalid 4th letter and would be missed.
# --------------------------------------------------------------------------- #
_PAN_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]{5}[0-9]{4}[A-Za-z](?![A-Za-z0-9])")

# --------------------------------------------------------------------------- #
# USN (VTU-style), e.g. 4SO25CS017:
#   college digit 1-4 | college letters (2) | admission year (2 digits) |
#   branch (2-3 letters) | roll number (3 digits)
# --------------------------------------------------------------------------- #
_USN_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"[1-4][A-Za-z]{2}" + _SEP + r"[0-9]{2}" + _SEP + r"[A-Za-z]{2,3}" + _SEP + r"[0-9]{3}"
    r"(?![A-Za-z0-9])"
)


def find_aadhaar(text: str) -> list[Entity]:
    out = []
    for m in _AADHAAR_RE.finditer(text):
        if verhoeff_valid(_digits_only(m.group())):
            out.append(_ent(T.AADHAAR, m))
    return out


def find_pan(text: str) -> list[Entity]:
    return [_ent(T.PAN, m) for m in _PAN_RE.finditer(text)]


def find_usn(text: str) -> list[Entity]:
    return [_ent(T.USN, m) for m in _USN_RE.finditer(text)]


# --------------------------------------------------------------------------- #
# Phone (AGENTS.md: [6-9]\d{4}\s?\d{5}), widened for real-world writing:
#   optional +91 / 0091 / 91 / 0 prefix, groupings 5-5, 4-6, 3-3-4, hyphens or spaces.
# Landline: STD code + number with a separator (or brackets), 10 digits after the leading 0.
# --------------------------------------------------------------------------- #
_PHONE_RE = re.compile(
    _DL
    + r"(?:(?:\+|00)[ \t]?91[ \t\-]?|91[ \t\-]|91(?=[6-9][0-9]{9}(?![0-9]))|0[ \t\-]?)?"
    + r"(?:[6-9][0-9]{4}[ \t\-]?[0-9]{5}"
    + r"|[6-9][0-9]{3}[ \t\-][0-9]{6}"
    + r"|[6-9][0-9]{2}[ \t\-][0-9]{3}[ \t\-][0-9]{4})"
    + _DR
)
_LANDLINE_RE = re.compile(
    _DL
    + r"(?:\(0[1-9][0-9]{1,3}\)[ \t\-]?|0[1-9][0-9]{1,3}[ \t\-])[0-9]{6,8}"
    + _DR
)


def find_phone(text: str) -> list[Entity]:
    out = [_ent(T.PHONE, m) for m in _PHONE_RE.finditer(text)]
    for m in _LANDLINE_RE.finditer(text):
        if len(_digits_only(m.group())) == 11:      # leading 0 + 10 digits
            out.append(_ent(T.PHONE, m, 0.95))
    return out


# --------------------------------------------------------------------------- #
# Email. Plain form, plus the "name [at] host [dot] com" form people use to dodge scrapers.
# --------------------------------------------------------------------------- #
_EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9][A-Za-z0-9._%+\-]*@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,}(?![A-Za-z0-9])"
)
_EMAIL_OBF_RE = re.compile(
    r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9][A-Za-z0-9._%+\-]*[ \t]*[\[\(\{][ \t]*at[ \t]*[\]\)\}][ \t]*"
    r"[A-Za-z0-9\-]+(?:[ \t]*[\[\(\{][ \t]*dot[ \t]*[\]\)\}][ \t]*[A-Za-z0-9\-]+)+(?![A-Za-z0-9])",
    re.I,
)


def find_email(text: str) -> list[Entity]:
    out = [_ent(T.EMAIL, m) for m in _EMAIL_RE.finditer(text)]
    out += [_ent(T.EMAIL, m) for m in _EMAIL_OBF_RE.finditer(text)]
    return out


# --------------------------------------------------------------------------- #
# IFSC (AGENTS.md: [A-Z]{4}0[A-Z0-9]{6}). Case-insensitive.
# --------------------------------------------------------------------------- #
_IFSC_RE = re.compile(_L + r"[A-Za-z]{4}0[A-Za-z0-9]{6}" + _R)


def find_ifsc(text: str) -> list[Entity]:
    return [_ent(T.IFSC, m) for m in _IFSC_RE.finditer(text)]


# --------------------------------------------------------------------------- #
# UPI ID: handle@bank. Only well-known UPI handles (no dot in the handle), so ordinary
# emails (which always have a dotted domain) are not touched. ABHA address: name@abdm / @sbx.
# --------------------------------------------------------------------------- #
_UPI_HANDLES = (
    "okhdfcbank|okicici|oksbi|okaxis|ybl|ibl|axl|paytm|apl|upi|sbi|axisbank|icici|hdfcbank|"
    "pnb|boi|cnrb|barodampay|fbl|ikwik|jupiteraxis|airtel|postbank|freecharge|pingpay|yesbank|"
    "yesg|rbl|idfcbank|kotak|dbs|unionbank|aubank|indus|federal|slice|naviaxis|waicici|"
    "wahdfcbank|wasbi|waaxis|abfspay|axisb|csbpay|hsbc|ptsbi|ptyes|pthdfc|ptaxis|okbizaxis|"
    "tapicici|sliceaxis|jio|bandhan|kmbl|idbi|iob|uco|psb|sib|kvb|tmb"
)
_UPI_RE = re.compile(
    r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9][A-Za-z0-9._\-]{1,}@(?:" + _UPI_HANDLES + r")"
    r"(?![A-Za-z0-9\-])(?!\.[A-Za-z])",
    re.I,
)
_ABHA_ADDR_RE = re.compile(
    r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9][A-Za-z0-9._]{3,}@(?:abdm|sbx)(?![A-Za-z0-9\-])(?!\.[A-Za-z])",
    re.I,
)


def find_upi(text: str) -> list[Entity]:
    out = [_ent(T.UPI_ID, m) for m in _UPI_RE.finditer(text)]
    out += [_ent(T.ABHA_ID, m) for m in _ABHA_ADDR_RE.finditer(text)]
    return out


# --------------------------------------------------------------------------- #
# Payment card: 13-19 digits (single spaces / hyphens allowed anywhere), Luhn check and a
# known issuer range (Visa 4, Mastercard 51-55 / 2221-2720, Amex 34/37, Diners/JCB 30/35/36/38,
# Discover/RuPay 60/65/81/82/508). The digit guards keep Aadhaar and phone numbers out.
# --------------------------------------------------------------------------- #
_CARD_RE = re.compile(_DL + r"[0-9](?:[ \t\-]?[0-9]){12,18}" + _DR)
_CARD_PREFIX_RE = re.compile(
    r"^(?:4|5[0-5]|2(?:2[2-9][0-9]|[3-6][0-9]{2}|7[01][0-9]|720)|3[0-9]|6[0-9]|508|81|82)"
)


def find_card(text: str) -> list[Entity]:
    out = []
    for m in _CARD_RE.finditer(text):
        d = _digits_only(m.group())
        if 13 <= len(d) <= 19 and _CARD_PREFIX_RE.match(d) and luhn_valid(d):
            out.append(_ent(T.CARD_NUMBER, m))
    return out


# --------------------------------------------------------------------------- #
# GSTIN: 2-digit state, PAN, entity no., "Z", check character (base-36 checksum).
# The embedded PAN is part of the GSTIN span, so it is not reported twice.
# --------------------------------------------------------------------------- #
_GSTIN_RE = re.compile(
    _L + r"[0-9]{2}[A-Za-z]{5}[0-9]{4}[A-Za-z][1-9A-Za-z][Zz][0-9A-Za-z]" + _R
)


def find_gstin(text: str) -> list[Entity]:
    return [_ent(T.GSTIN, m) for m in _GSTIN_RE.finditer(text) if gstin_valid(m.group())]


# --------------------------------------------------------------------------- #
# Vehicle registration (state code must be a real one, written in capitals) and BH series.
# Driving licence: state + RTO + 4-digit year + 7 digits (e.g. KA01 20110012345).
# --------------------------------------------------------------------------- #
_STATES = (
    "AN|AP|AR|AS|BR|CG|CH|DD|DL|DN|GA|GJ|HP|HR|JH|JK|KA|KL|LA|LD|MH|ML|MN|MP|MZ|NL|OD|OR|PB|"
    "PY|RJ|SK|TN|TR|TS|UK|UP|WB"
)
_VEHICLE_RE = re.compile(
    _L + r"(?-i:" + _STATES + r")[ \t\-]?[0-9]{1,2}[ \t\-]?[A-Za-z]{1,3}[ \t\-]?[0-9]{4}" + _R
)
_VEHICLE_BH_RE = re.compile(
    _L + r"[0-9]{2}[ \t\-]?(?-i:BH)[ \t\-]?[0-9]{4}[ \t\-]?[A-HJ-NP-Za-hj-np-z]{1,2}" + _R
)
_DL_RE = re.compile(
    _L + r"(?-i:" + _STATES + r")[ \t\-]?[0-9]{2}[ \t\-]?(?:19|20)[0-9]{2}[ \t\-]?[0-9]{7}" + _R
)


def find_vehicle_and_licence(text: str) -> list[Entity]:
    out = [_ent(T.VEHICLE_REG, m, 0.9) for m in _VEHICLE_RE.finditer(text)]
    out += [_ent(T.VEHICLE_REG, m, 0.9) for m in _VEHICLE_BH_RE.finditer(text)]
    out += [_ent(T.DRIVING_LICENCE, m, 0.95) for m in _DL_RE.finditer(text)]
    return out


# --------------------------------------------------------------------------- #
# Network identifiers: IPv4, IPv6 (validated with the stdlib), MAC address.
# --------------------------------------------------------------------------- #
_OCT = r"(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])"
_IPV4_RE = re.compile(r"(?<![0-9.A-Za-z])" + _OCT + r"(?:\." + _OCT + r"){3}(?![0-9A-Za-z]|\.[0-9])")
_VERSION_CTX = re.compile(r"(?:version|ver\.?|release|build|\bv)[ \t:=]*$", re.I)
_IPV6_RE = re.compile(r"(?<![0-9A-Za-z:])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![0-9A-Za-z:])")
_MAC_RE = re.compile(r"(?<![0-9A-Za-z:\-])(?:[0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}(?![0-9A-Za-z:\-])")


def find_network_ids(text: str) -> list[Entity]:
    out = [
        _ent(T.IP_ADDRESS, m, 0.9)
        for m in _IPV4_RE.finditer(text)
        if not _VERSION_CTX.search(text[max(0, m.start() - 12):m.start()])
    ]
    for m in _IPV6_RE.finditer(text):
        try:
            ipaddress.IPv6Address(m.group())
        except ValueError:
            continue
        out.append(_ent(T.IP_ADDRESS, m, 0.9))
    out += [_ent(T.MAC_ADDRESS, m, 0.9) for m in _MAC_RE.finditer(text)]
    return out


# --------------------------------------------------------------------------- #
# Personal profile URLs on well-known sites.
# --------------------------------------------------------------------------- #
_PROFILE_RE = re.compile(
    r"(?<![A-Za-z0-9@.\-])(?:https?://)?(?:www\.)?"
    r"(?:linkedin\.com/(?:in|pub)|facebook\.com|fb\.com|instagram\.com|twitter\.com|x\.com|"
    r"github\.com|t\.me|wa\.me|youtube\.com/@)/?"
    r"[A-Za-z0-9_\-]+(?:[./][A-Za-z0-9_\-]+)*",
    re.I,
)


def find_profile_urls(text: str) -> list[Entity]:
    return [_ent(T.SOCIAL_PROFILE, m, 0.9) for m in _PROFILE_RE.finditer(text)]


# --------------------------------------------------------------------------- #
# Offset-preserving normalisation, then everything together.
# --------------------------------------------------------------------------- #
_SPACE_LIKE = {0x00A0, 0x1680, 0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006,
               0x2007, 0x2008, 0x2009, 0x200A, 0x202F, 0x205F, 0x3000}
_DASH_LIKE = {0x2010, 0x2011, 0x2012, 0x2013, 0x2212}


def normalize(text: str) -> str:
    """Map non-ASCII digits (Kannada, Devanagari, fullwidth, ...), odd spaces and dashes to
    ASCII, one character for one character, so offsets into the result are valid offsets
    into `text`."""
    if text.isascii():
        return text
    out = []
    for ch in text:
        o = ord(ch)
        if o < 128:
            out.append(ch)
        elif o in _SPACE_LIKE:
            out.append(" ")
        elif o in _DASH_LIKE:
            out.append("-")
        elif ch.isdecimal():
            out.append(str(unicodedata.decimal(ch)))
        else:
            out.append(ch)
    return "".join(out)


_FORMAT_DETECTORS = (
    find_aadhaar, find_pan, find_usn, find_phone, find_email, find_ifsc, find_upi, find_card,
    find_gstin, find_vehicle_and_licence, find_network_ids, find_profile_urls,
)

# Free-text types: when a higher-scoring entity sits inside one of these, the free-text span is
# cut around it instead of being dropped, so e.g. an address stays redacted at L3 while the
# phone number inside it is still caught at L1.
_CARVABLE = {T.ADDRESS, T.ORGANIZATION, T.HEALTH_INFO, T.DISABILITY, T.FINANCIAL_INFO,
             T.CITY, T.JOB_TITLE}
_PRIO = {t: i for i, t in enumerate(T.PRIORITY)}


def _overlaps(a: Entity, b: Entity) -> bool:
    return a.start < b.end and b.start < a.end


def resolve(ents: list[Entity], text: str) -> list[Entity]:
    """Remove overlaps: higher score wins, then longer span, then type priority (same rule as
    AGENTS.md `merge()`). Free-text spans that lose are cut around the winners, not discarded."""
    order = sorted(ents, key=lambda e: (-e.score, -(e.end - e.start), _PRIO.get(e.type, 99), e.start))
    kept: list[Entity] = []
    for e in order:
        clash = [k for k in kept if _overlaps(e, k)]
        if not clash:
            kept.append(e)
            continue
        if e.type not in _CARVABLE:
            continue
        # carve: remaining pieces of e outside every winner
        pieces, cur = [], e.start
        for k in sorted(clash, key=lambda k: k.start):
            if k.start > cur:
                pieces.append((cur, min(k.start, e.end)))
            cur = max(cur, k.end)
        if cur < e.end:
            pieces.append((cur, e.end))
        for s, t in pieces:
            # trim whitespace / separators at the edges
            while s < t and text[s] in " \t,;:-/.":
                s += 1
            while t > s and text[t - 1] in " \t,;:-/.":
                t -= 1
            if sum(ch.isalnum() for ch in text[s:t]) >= 3:
                kept.append(Entity(e.type, s, t, e.score, e.source))
    kept.sort(key=lambda e: (e.start, e.end))
    return kept


def find_all(text: str) -> list[Entity]:
    """Every raw hit from every regex and context detector, overlaps NOT resolved.
    Offsets refer to `text` as given."""
    from . import context_rules  # local import: context_rules imports this module

    norm = normalize(text)
    ents: list[Entity] = []
    for fn in _FORMAT_DETECTORS:
        ents += fn(norm)
    ents += context_rules.find_context(norm)
    return ents


def find(text: str) -> list[Entity]:
    """All regex / checksum / context entities in `text`, no overlaps, sorted by start offset."""
    if not text:
        return []
    return resolve(find_all(text), normalize(text))
