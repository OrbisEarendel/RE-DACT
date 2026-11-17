"""Context-word and "Label: value" detectors (AGENTS.md section 7: bank account numbers, "use
context words like 'account', 'A/c'"; custom rules; Section 6 levels L2/L3 types).

These patterns are too loose to trust on their own (any 9-18 digit number is not an account
number), so each one needs a nearby keyword or a form-style label. Scores are below 1.0 to say so.

Run on normalised text (`regex_rules.normalize`) via `regex_rules.find()`. Entity offsets are
character offsets into that text. Nothing here logs, prints or stores matched text.
"""
from __future__ import annotations

import re
from datetime import date

from redact.entity import Entity

from . import regex_types as T
from .checksum import luhn_valid, verhoeff_valid
from .regex_rules import _AADHAAR_RE, _digits_only

SOURCE = "regex"


def _e(etype: str, s: int, e: int, score: float) -> Entity:
    return Entity(etype, s, e, score, SOURCE)


def _before(text: str, pos: int, window: int) -> str:
    return text[max(0, pos - window):pos]


def _near(rx: re.Pattern, text: str, s: int, e: int, before: int = 30, after: int = 0) -> bool:
    if rx.search(_before(text, s, before)):
        return True
    return bool(after and rx.search(text[e:e + after]))


# =========================================================================== #
# Identifiers that need a context word
# =========================================================================== #
_AADHAAR_CTX = re.compile(
    r"aadhaar|aadhar|adhaar|adhar|aadhr|uidai|\buid\b|आधार|ಆಧಾರ್", re.I
)


def find_aadhaar_unverified(text: str) -> list[Entity]:
    """Aadhaar-shaped number that FAILS the Verhoeff check but sits next to an Aadhaar keyword.
    Catches OCR / typing slips (one wrong digit) at a lower score, so a real number is not
    left in the output just because of a misread digit."""
    out = []
    for m in _AADHAAR_RE.finditer(text):
        if verhoeff_valid(_digits_only(m.group())):
            continue
        if _near(_AADHAAR_CTX, text, m.start(), m.end(), before=30, after=15):
            out.append(_e(T.AADHAAR, m.start(), m.end(), 0.7))
    return out


_VID_RE = re.compile(
    r"(?<![0-9])(?<![0-9][ \t\-])[2-9][0-9]{3}[ \t\-]?[0-9]{4}[ \t\-]?[0-9]{4}[ \t\-]?[0-9]{4}(?![ \t\-]?[0-9])"
)
_VID_CTX = re.compile(r"\bvid\b|virtual[ \t]+(?:id|identi)", re.I)


def find_aadhaar_vid(text: str) -> list[Entity]:
    """16-digit Aadhaar Virtual ID: Verhoeff check + the word VID / "virtual ID" before it."""
    return [
        _e(T.AADHAAR_VID, m.start(), m.end(), 0.95)
        for m in _VID_RE.finditer(text)
        if verhoeff_valid(_digits_only(m.group())) and _near(_VID_CTX, text, m.start(), m.end(), 30)
    ]


_BANK_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:(?:savings|current|salary|bank|beneficiary|customer|loan|deposit)[ \t]+)?"
    r"(?:a/c|a\.c\.?|acc(?:oun)?t)\b\.?[ \t]*(?:no\b\.?|number|num\b\.?|nbr|#)?[ \t]*(?:is[ \t]+)?"
    r"[:#=\-–]?[ \t]*(?P<n>[0-9](?:[ \t\-]?[0-9]){8,17})(?![ \t\-]?[0-9])",
    re.I,
)


def find_bank_account(text: str) -> list[Entity]:
    """9-18 digit number right after "A/c", "Account No." etc. (no checksum exists for
    Indian bank account numbers, so the keyword is the evidence)."""
    out = []
    for m in _BANK_RE.finditer(text):
        if 9 <= len(_digits_only(m.group("n"))) <= 18:
            out.append(_e(T.BANK_ACCOUNT, m.start("n"), m.end("n"), 0.85))
    return out


_PASSPORT_RE = re.compile(
    r"(?<![A-Za-z0-9])[A-PR-WYa-pr-wy][1-9][0-9][ ]?[0-9]{4}[1-9](?![A-Za-z0-9])"
)
_PASSPORT_CTX = re.compile(r"passport|travel[ \t]+document|\bppt\b|पासपोर्ट", re.I)


def find_passport(text: str) -> list[Entity]:
    return [
        _e(T.PASSPORT, m.start(), m.end(), 0.95)
        for m in _PASSPORT_RE.finditer(text)
        if _near(_PASSPORT_CTX, text, m.start(), m.end(), 30, 12)
    ]


_VOTER_RE = re.compile(r"(?<![A-Za-z0-9])(?-i:[A-Z]{3})[0-9]{7}(?![A-Za-z0-9])", re.I)
_VOTER_CTX = re.compile(r"voter|\bepic\b|election|elector|मतदाता", re.I)


def find_voter_id(text: str) -> list[Entity]:
    """EPIC number: 3 capitals + 7 digits. 0.95 with a voter keyword nearby, 0.6 without it
    (the bare shape also fits product codes)."""
    out = []
    for m in _VOTER_RE.finditer(text):
        ctx = _near(_VOTER_CTX, text, m.start(), m.end(), 40, 15)
        out.append(_e(T.VOTER_ID, m.start(), m.end(), 0.95 if ctx else 0.6))
    return out


_ABHA_RE = re.compile(
    r"(?<![0-9])(?<![0-9][ \t\-])[0-9]{2}[ \t\-]?[0-9]{4}[ \t\-]?[0-9]{4}[ \t\-]?[0-9]{4}(?![ \t\-]?[0-9])"
)
_ABHA_CTX = re.compile(r"abha|health[ \t]*(?:id|account)|ayushman|\bpmjay\b", re.I)


def find_abha_number(text: str) -> list[Entity]:
    return [
        _e(T.ABHA_ID, m.start(), m.end(), 0.9)
        for m in _ABHA_RE.finditer(text)
        if _near(_ABHA_CTX, text, m.start(), m.end(), 30)
    ]


_IMEI_RE = re.compile(
    r"(?<![0-9])(?<![0-9][ \t\-])[0-9]{2}[ \t\-]?[0-9]{6}[ \t\-]?[0-9]{6}[ \t\-]?[0-9](?![ \t\-]?[0-9])"
)
_IMEI_CTX = re.compile(r"imei|device[ \t]*id|handset|serial", re.I)


def find_imei(text: str) -> list[Entity]:
    return [
        _e(T.IMEI, m.start(), m.end(), 0.95)
        for m in _IMEI_RE.finditer(text)
        if luhn_valid(_digits_only(m.group())) and _near(_IMEI_CTX, text, m.start(), m.end(), 25)
    ]


_PIN_RE = re.compile(r"(?<![0-9])(?<![0-9][ \t\-])[1-9][0-9]{2}[ ]?[0-9]{3}(?![ \t\-]?[0-9])")
_PIN_CTX = re.compile(r"\bpin(?:[ \t\-]?code)?\b[ \t]*[:\-=#.]*[ \t]*$|postal[ \t]*code[ \t:\-]*$|\bzip(?:[ \t]*code)?\b[ \t:\-]*$|पिन[ \t:\-]*$", re.I)


def find_pin_code(text: str) -> list[Entity]:
    """6-digit postal code, only right after "PIN", "PIN code", "Postal code" or "ZIP"."""
    return [
        _e(T.PIN_CODE, m.start(), m.end(), 0.85)
        for m in _PIN_RE.finditer(text)
        if _PIN_CTX.search(_before(text, m.start(), 20))
    ]


_CVV_RE = re.compile(r"(?<![A-Za-z])(?:cvv2?|cvc2?|security[ \t]+code)[ \t]*[:#=\-]?[ \t]*(?P<n>[0-9]{3,4})(?![0-9])", re.I)
_EXPIRY_RE = re.compile(
    r"(?<![A-Za-z])(?:exp(?:iry|ires|\.)?(?:[ \t]+date)?|valid[ \t]*(?:thru|through|till|upto|until))[ \t]*[:#=\-]?[ \t]*"
    r"(?P<d>(?:0[1-9]|1[0-2])[ \t]*/[ \t]*(?:[0-9]{2}|20[0-9]{2}))(?![0-9])",
    re.I,
)


def find_card_extras(text: str) -> list[Entity]:
    out = [_e(T.CVV, m.start("n"), m.end("n"), 0.9) for m in _CVV_RE.finditer(text)]
    out += [_e(T.CARD_EXPIRY, m.start("d"), m.end("d"), 0.9) for m in _EXPIRY_RE.finditer(text)]
    return out


_HANDLE_RE = re.compile(r"(?<![A-Za-z0-9._%+\-@/])@[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*(?![A-Za-z0-9_@])")
_HANDLE_CTX = re.compile(
    r"(?:instagram|insta|twitter|telegram|snapchat|tiktok|handle|follow[ \t]+me|user[ \t]*name|dm[ \t]+me|socials?)"
    r"[ \t:\-=(]*$",
    re.I,
)


def find_social_handle(text: str) -> list[Entity]:
    """@handle, only with a social-media word just before it (so code decorators like
    @dataclass are not reported)."""
    return [
        _e(T.SOCIAL_HANDLE, m.start(), m.end(), 0.85)
        for m in _HANDLE_RE.finditer(text)
        if 4 <= len(m.group()) <= 31 and _HANDLE_CTX.search(_before(text, m.start(), 30))
    ]


_GEO_RE = re.compile(
    r"(?<![0-9.])(?P<lat>-?[0-9]{1,2}\.[0-9]{4,})[ \t]*,[ \t]*(?P<lon>-?[0-9]{1,3}\.[0-9]{4,})(?![0-9])"
)
_GEO_CTX = re.compile(r"\blat|\blng\b|\blon\b|latitude|longitude|coordinate|\bgps\b|location|\bgeo", re.I)


def find_geo(text: str) -> list[Entity]:
    """lat, lon with 4+ decimals. Needs a location word nearby, or to fall inside India's
    bounding box (lat 6-38, lon 68-98)."""
    out = []
    for m in _GEO_RE.finditer(text):
        lat, lon = float(m.group("lat")), float(m.group("lon"))
        if abs(lat) > 90 or abs(lon) > 180:
            continue
        in_india = 6.0 <= lat <= 38.0 and 68.0 <= lon <= 98.0
        if in_india or _near(_GEO_CTX, text, m.start(), m.end(), 25):
            out.append(_e(T.GEO_COORDINATES, m.start(), m.end(), 0.9))
    return out


# =========================================================================== #
# Dates and ages (AGENTS.md level L2)
# =========================================================================== #
_MONTHS = (
    "jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
    "sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)
_MONTH_NUM = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}

_DATE_NUM_DMY = re.compile(r"(?<![0-9A-Za-z])([0-9]{1,2})([/.\-])([0-9]{1,2})\2((?:19|20)[0-9]{2})(?![0-9A-Za-z])")
_DATE_NUM_YMD = re.compile(r"(?<![0-9A-Za-z])((?:19|20)[0-9]{2})([/.\-])([0-9]{1,2})\2([0-9]{1,2})(?![0-9])")
_DATE_NUM_DMY2 = re.compile(r"(?<![0-9A-Za-z])([0-9]{1,2})([/.\-])([0-9]{1,2})\2([0-9]{2})(?![0-9A-Za-z])")
_DATE_TXT_DMY = re.compile(
    r"(?<![0-9A-Za-z])([0-9]{1,2})(?:st|nd|rd|th)?[ \t\-/.,]*(?:of[ \t]+)?(" + _MONTHS + r")[ \t\-/.,]*((?:19|20)[0-9]{2})(?![0-9A-Za-z])",
    re.I,
)
_DATE_TXT_MDY = re.compile(
    r"(?<![A-Za-z])(" + _MONTHS + r")[ \t.]*([0-9]{1,2})(?:st|nd|rd|th)?,?[ \t]*((?:19|20)[0-9]{2})(?![0-9A-Za-z])",
    re.I,
)
_DOB_CTX = re.compile(
    r"(?:d\.?[ \t]?o\.?[ \t]?b\.?|date[ \t]+of[ \t]+birth|birth[ \t]*date|born(?:[ \t]+on)?|b'?day|birthday|जन्म[ \t]*तिथि)[ \t:\-=(]*$",
    re.I,
)


def _valid(y: int, m: int, d: int) -> bool:
    try:
        date(y, m, d)
        return True
    except ValueError:
        return False


def find_dates(text: str) -> list[Entity]:
    """Calendar dates (real dates only). "DATE_OF_BIRTH" when a birth keyword sits right
    before it (that one also accepts 2-digit years), otherwise "DATE"."""
    hits: list[tuple[int, int]] = []
    two_digit: list[tuple[int, int]] = []
    for m in _DATE_NUM_DMY.finditer(text):
        a, b, y = int(m.group(1)), int(m.group(3)), int(m.group(4))
        if _valid(y, b, a) or _valid(y, a, b):
            hits.append((m.start(), m.end()))
    for m in _DATE_NUM_YMD.finditer(text):
        if _valid(int(m.group(1)), int(m.group(3)), int(m.group(4))):
            hits.append((m.start(), m.end()))
    for m in _DATE_TXT_DMY.finditer(text):
        if _valid(int(m.group(3)), _MONTH_NUM[m.group(2)[:3].lower()], int(m.group(1))):
            hits.append((m.start(), m.end()))
    for m in _DATE_TXT_MDY.finditer(text):
        if _valid(int(m.group(3)), _MONTH_NUM[m.group(1)[:3].lower()], int(m.group(2))):
            hits.append((m.start(), m.end()))
    for m in _DATE_NUM_DMY2.finditer(text):
        a, b, y = int(m.group(1)), int(m.group(3)), 2000 + int(m.group(4))
        if _valid(y, b, a) or _valid(y, a, b):
            two_digit.append((m.start(), m.end()))
    out = []
    for s, e in hits:
        dob = bool(_DOB_CTX.search(_before(text, s, 40)))
        out.append(_e(T.DATE_OF_BIRTH if dob else T.DATE, s, e, 0.95 if dob else 0.8))
    for s, e in two_digit:      # only with a birth keyword, otherwise it is too ambiguous
        if _DOB_CTX.search(_before(text, s, 40)):
            out.append(_e(T.DATE_OF_BIRTH, s, e, 0.9))
    return out


_AGE_LABEL_RE = re.compile(
    r"(?<![A-Za-z])(?:age[d]?(?:[ \t]+about)?|age[ \t]+of|age[ \t]*[/&][ \t]*(?:sex|gender))[ \t]*[:=\-]?[ \t]*(?:is[ \t]+)?"
    r"(?P<n>[0-9]{1,3})(?![0-9])(?![ \t]*(?:%|[0-9]|months?|days?|weeks?))",
    re.I,
)
_AGE_OLD_RE = re.compile(
    r"(?<![0-9.\-])(?P<n>[0-9]{1,3})(?:[ \t]*-[ \t]*|[ \t]*)"
    r"(?:(?:years?|yrs?)(?:[ \t]*-[ \t]*|[ \t]*)old|y/o|yo)(?![A-Za-z])",
    re.I,
)
_AGE_NOT_PERSONAL = re.compile(
    r"(?:under|over|above|below|than|least|most|minimum|maximum|min|max|upto|up[ \t]+to|between|and|to|older|younger|from)[ \t]*$",
    re.I,
)


def find_age(text: str) -> list[Entity]:
    """Age in years, only in "Age: 34", "aged 34", "age of 34", "34 years old", "34-year-old",
    "34 yo" shapes. The span is the number alone. Ages under 18 are "AGE_MINOR" (DPDP s.2(f)).
    Ranges and rules such as "under 18 years old" are skipped."""
    out = []
    seen = set()
    for rx in (_AGE_LABEL_RE, _AGE_OLD_RE):
        for m in rx.finditer(text):
            s, e = m.start("n"), m.end("n")
            n = int(m.group("n"))
            if (s, e) in seen or n > 120:
                continue
            if _AGE_NOT_PERSONAL.search(_before(text, m.start(), 14)):
                continue
            seen.add((s, e))
            out.append(_e(T.AGE_MINOR if n < 18 else T.AGE, s, e, 0.9))
    return out


# =========================================================================== #
# "Label: value" fields (forms, ID cards, letters)
# =========================================================================== #
# A name word is "Rahul", "D'Souza", "Anne-Marie", an initial with a dot ("R.") or a lone capital
# ("K"). It never swallows a sentence-final dot, and a single space joins words (a tab or a
# double space is a column break).
_NAME_TOKEN = r"(?:[A-Za-z]\.|[A-Za-z][A-Za-z'’\-]+|(?-i:[A-Z])(?![A-Za-z'’\-/.]))"
_NAME_RUN = _NAME_TOKEN + r"(?:[ ]" + _NAME_TOKEN + r"){0,5}"
_CAP_TOKEN = r"(?-i:(?:[A-Z]\.|[A-Z][A-Za-z'’\-]+|[A-Z](?![A-Za-z'’\-/.])))"
_CAP_RUN = _CAP_TOKEN + r"(?:[ ]" + _CAP_TOKEN + r"){0,3}"

# Words that start the NEXT form field; a name never continues into them.
_STOP_LABELS = frozenset(
    "usn dob age phone mobile mob email e-mail address aadhaar aadhar pan gender sex class roll "
    "branch dept department sem semester section year id no number contact city date father "
    "mother guardian name company designation blood religion caste nationality marital ph tel "
    "reg regd registration course batch college university school salary income ctc stipend "
    "diagnosis disease allergy allergies occupation profession emi balance category disability "
    "height weight hobbies status district town village taluk taluka tehsil state pin pincode country".split()
)
_LOWER_STOP = frozenset(
    "is was and the a an who has of from at in on for with studies works lives to by as are were "
    "will he she they".split()
)
_PARTICLES = frozenset("bin bint de van von al el la da di du ibn".split())
_NULLS = frozenset("na n/a nil none null unknown not xxx xx x tbd nill no false".split())
_BUSINESS = frozenset(
    "residency nilaya nivas enterprises stores traders bhavan hotel lodge mess garden complex "
    "apartment apartments layout nagar temple mutt kshetra tiffins sweets restaurant mahal "
    "towers heights park villa villas hospital clinic college school university institute "
    "foundation trust group industries motors agencies associates laboratories labs".split()
)


def _word_span(value: str, base: int, *, name_rules: bool, max_tokens: int, business: bool = False):
    """Pick the leading words of `value` that belong to the field, cutting at the next form
    label. Returns (start, end) absolute offsets or None."""
    toks = [(m.group(), m.start(), m.end()) for m in re.finditer(_NAME_TOKEN, value)]
    if not toks:
        return None
    first_lower = toks[0][0][0].islower()
    kept = []
    for tok, s, e in toks:
        low = tok.lower().rstrip(".'’-")
        if low in _STOP_LABELS:
            break
        if business and low in _BUSINESS:
            return None
        if name_rules:
            if first_lower:
                if low in _LOWER_STOP or len(kept) >= 3:
                    break
            elif tok[0].islower() and low not in _PARTICLES:
                break
        if len(kept) >= max_tokens:
            break
        kept.append((tok, s, e))
    if not kept:
        return None
    if kept[0][0].lower().rstrip(".") in _NULLS:
        return None
    s, e = kept[0][1], kept[-1][2]
    # drop a sentence-final dot (but keep initials such as "R.")
    while e > s and value[e - 1] in ".,'’-" and not (value[e - 1] == "." and len(kept[-1][0]) <= 2):
        e -= 1
    if sum(ch.isalpha() for ch in value[s:e]) < 3:
        return None
    return base + s, base + e


_LABEL_PREFIX = frozenset(
    "blood date roll phone mobile contact father mother job account registration annual monthly "
    "current permanent employee student full first last".split()
)


def _cut_at_next_label(v: str) -> str:
    """Cut `v` where the next "Label:" starts (the label is the 1-2 words before a colon)."""
    m = re.search(r"([A-Za-z][A-Za-z/]*)[ \t]*[:=]", v)
    if not m:
        return v
    cut = m.start(1)
    prev = re.search(r"([A-Za-z']+)[ \t]+$", v[:cut])
    if prev and prev.group(1).lower().rstrip("'s") in _LABEL_PREFIX:
        cut = prev.start(1)
    return v[:cut]


def _line_span(value: str, base: int, stop_at_comma: bool = False):
    """Trim a free-text value; reject empty / null-ish ones."""
    value = _cut_at_next_label(value)
    if stop_at_comma:
        value = value.split(",")[0]
    v = value.strip(" \t.,;:-–")
    if not v or v.lower() in _NULLS or re.fullmatch(r"(?:not[ \t]+(?:applicable|available)|-+|\.+)", v, re.I):
        return None
    if sum(ch.isalnum() for ch in v) < 3:
        return None
    s = base + value.index(v)
    return s, s + len(v)


_LINE_VALUE = r"(?P<v>(?:[^\n\r;|\t ]|[ ](?![ ]))+)"


def _label_re(generic: str, compound: str, value: str) -> re.Pattern:
    labels = "|".join(p for p in (compound, generic) if p)
    return re.compile(
        r"(?<![A-Za-z0-9])(?P<lbl>" + labels + r")(?P<sep>[ \t]*[:=][ \t]*|[ \t]+[\-–][ \t]+)" + value,
        re.I | re.M,
    )


def _label_ok(text: str, m: re.Match, excl: frozenset) -> bool:
    """A dash separator only counts when the label starts its line, and the word just before
    the label must not turn it into something else ("file name:", "email address:")."""
    ls = m.start("lbl")
    line_start = text.rfind("\n", 0, ls) + 1
    at_line_start = not text[line_start:ls].strip()
    if m.group("sep").strip() in ("-", "–") and not at_line_start:
        return False
    if excl and not at_line_start:
        prev = re.search(r"([A-Za-z\-]+)[ \t]*$", text[max(0, ls - 20):ls])
        if prev and prev.group(1).lower() in excl:
            return False
    return True


_NAME_EXCL = frozenset(
    "file user host domain product brand column field sheet dataset folder table variable class "
    "function parameter param display nick screen team project event type service server node "
    "package module app tag key label company organisation organization institute institution "
    "university college school firm employer workplace city town district village bank branch "
    "street road area hospital clinic department dept subject course model device".split()
)
_ADDR_EXCL = frozenset("email e-mail mail ip mac web url wallet memory return bitcoin ipv4 ipv6 postal".split())
_NONE = frozenset()


_REL = (
    r"student|candidate|applicant|employee|patient|customer|member|account[ \t]+holder|"
    r"card[ \t]*holder|nominee|beneficiary|passenger|owner|author|complainant|witness|guardian|"
    r"parent|father|mother|spouse|husband|wife|mentor|guide|faculty|teacher|principal|hod|"
    r"manager|contact(?:[ \t]+person)?|referee|emergency[ \t]+contact"
)

# (type, regex, kind, score).  kind: "name", "line", "words<N>", or "regex" (value group used as is)
_FIELDS: list[tuple[str, re.Pattern, str, float, frozenset]] = [
    (T.PERSON, _label_re(
        r"name",
        r"full[ \t]+name|first[ \t]+name|last[ \t]+name|middle[ \t]+name|sur[ \t]?name|"
        r"(?:" + _REL + r")(?:['’]s)?[ \t]+name|"
        r"name[ \t]+of[ \t]+(?:the[ \t]+)?(?:" + _REL + r")|"
        r"father(?:['’]s)?|mother(?:['’]s)?|guardian(?:['’]s)?|spouse|nominee|husband|wife",
        r"(?P<v>" + _NAME_RUN + r")"), "name", 0.85, _NAME_EXCL),
    (T.ADDRESS, _label_re(
        r"address(?:[ \t]*line[ \t]*[12])?|addr|residence",
        r"(?:permanent|current|residential|correspondence|present|postal|mailing|home|office|billing|"
        r"shipping|delivery|communication|temporary)[ \t]+address(?:[ \t]*line[ \t]*[12])?",
        _LINE_VALUE), "line", 0.85, _ADDR_EXCL),
    (T.CITY, _label_re(
        r"city|town|district|village|taluk|taluka|tehsil|hometown|native[ \t]+place",
        r"place[ \t]+of[ \t]+(?:birth|residence|work)|home[ \t]*town",
        r"(?P<v>" + _NAME_RUN + r")"), "words4", 0.8, _NAME_EXCL),
    (T.ORGANIZATION, _label_re(
        r"company|organi[sz]ation|employer|institute|institution|university|college|school|workplace|firm",
        r"(?:company|organi[sz]ation|employer|institute|institution|university|college|school|firm|workplace)[ \t]+name|"
        r"name[ \t]+of[ \t]+(?:the[ \t]+)?(?:company|organi[sz]ation|employer|institute|institution|university|college|school|firm)|"
        r"(?:current|previous|present)[ \t]+(?:company|employer|organi[sz]ation)",
        _LINE_VALUE), "line1", 0.8, _NAME_EXCL - {"company", "organisation", "organization", "institute", "institution", "university", "college", "school", "firm", "employer", "workplace"}),
    (T.JOB_TITLE, _label_re(
        r"designation|occupation|profession|job[ \t]+title|job[ \t]+role|position",
        r"(?:current|present)[ \t]+(?:designation|role|position|job)",
        _LINE_VALUE), "line1", 0.8, frozenset("current present previous".split()) - frozenset()),
    (T.GENDER, _label_re(
        r"gender|sex", "",
        r"(?P<v>(?:male|female|transgender|trans|non[ \-]?binary|other|m|f)(?![A-Za-z]))"), "regex", 0.9, _NONE),
    (T.BLOOD_GROUP, _label_re(
        "", r"blood[ \t]+(?:group|type)",
        r"(?P<v>(?:AB|A|B|O)[ \t]*(?:\+|-|positive|negative|ve)(?![A-Za-z]))"), "regex", 0.9, _NONE),
    (T.RELIGION, _label_re("religion", "", r"(?P<v>" + _NAME_RUN + r")"), "words2", 0.85, _NONE),
    (T.CASTE, _label_re(r"caste|sub[ \-]?caste", "", r"(?P<v>" + _NAME_RUN + r")"), "words3", 0.85, _NONE),
    (T.CASTE, _label_re(
        "category", "",
        r"(?P<v>(?:SC|ST|OBC|EWS|GENERAL|GEN|GM|CAT[ \-]?[0-9A-Z]{1,2})(?![A-Za-z]))"), "regex", 0.8, _NONE),
    (T.DISABILITY, _label_re(
        r"disabilit(?:y|ies)(?:[ \t]+(?:type|status|details))?", "", _LINE_VALUE), "line1", 0.85, _NONE),
    (T.HEALTH_INFO, _label_re(
        r"diagnosis|disease|ailment|illness|allerg(?:y|ies)|medications?|prescription|symptoms?",
        r"medical[ \t]+(?:condition|conditions|history)|health[ \t]+(?:condition|issues?|status)|"
        r"chronic[ \t]+(?:condition|illness|disease)|current[ \t]+medications?",
        _LINE_VALUE), "line1", 0.8, _NONE),
    (T.FINANCIAL_INFO, _label_re(
        r"salary|ctc|income|stipend|emi|balance|outstanding|net[ \t]+worth|cibil|credit[ \t]+score",
        r"(?:annual|monthly|family|gross|net|current|expected|basic)[ \t]+(?:salary|income|ctc|pay)|"
        r"loan[ \t]+amount|(?:cibil|credit)[ \t]+score|account[ \t]+balance|outstanding[ \t]+(?:amount|balance)",
        r"(?P<v>(?:₹|rs\.?|inr|usd|\$)?[ \t]*[0-9][0-9,]*(?:\.[0-9]+)?"
        r"(?:[ \t]*(?:lakhs?|lacs?|lpa|crores?|cr|k|/-|per[ \t]+(?:month|annum|year)|pm|pa))?(?![A-Za-z0-9]))"),
        "regex", 0.8, _NONE),
]


def find_labelled_fields(text: str) -> list[Entity]:
    """"Label: value" fields: names, address, city, organisation, job title, gender, blood group,
    religion, caste, disability, health info, financial amounts. The value only is reported."""
    out = []
    for etype, rx, kind, score, excl in _FIELDS:
        pos = 0
        while True:
            m = rx.search(text, pos)
            if not m:
                break
            sp = None
            if _label_ok(text, m, excl):
                v, base = m.group("v"), m.start("v")
                if kind == "name":
                    sp = _word_span(v, base, name_rules=True, max_tokens=6)
                elif kind.startswith("words"):
                    sp = _word_span(v, base, name_rules=False, max_tokens=int(kind[5:]))
                elif kind in ("line", "line1"):
                    sp = _line_span(v, base, stop_at_comma=(kind == "line1"))
                    if sp and etype == T.DISABILITY and text[sp[0]:sp[1]].lower() in _NULLS:
                        sp = None
                else:
                    sp = (base, m.end("v"))
            if sp and sp[1] > sp[0]:
                out.append(_e(etype, sp[0], sp[1], score))
                pos = max(sp[1], m.start("lbl") + 1)    # resume right after the value, so a
            else:                                         # second label on the same line is seen
                pos = m.end("sep") if m.end("sep") > m.start("lbl") else m.end()
    return out


_HONORIFIC_RE = re.compile(
    r"(?<![A-Za-z])(?:Mr|Mrs|Ms|Miss|Mx|Dr|Prof|Shri|Shree|Smt|Sri|Kum|Kumari|Er)\.?[ \t]+(?P<v>" + _CAP_RUN + r")",
    re.I,
)
_RELATION_RE = re.compile(
    r"(?<![A-Za-z])(?:S/o|D/o|W/o|C/o|H/o|S\.o\.?|D\.o\.?|W\.o\.?|C\.o\.?|son[ \t]+of|daughter[ \t]+of|"
    r"wife[ \t]+of|husband[ \t]+of)[ \t:.\-]*(?P<v>" + _NAME_RUN + r")",
    re.I,
)


def find_titled_names(text: str) -> list[Entity]:
    """Names after an honorific (Mr., Dr., Smt., Shri ...) or after S/o, D/o, W/o, C/o.
    Names containing a business word ("Sri Residency", "Sri Krishna Bhavan") are not treated
    as people (AGENTS.md known weak spot)."""
    rel = []
    for m in _RELATION_RE.finditer(text):
        sp = _word_span(m.group("v"), m.start("v"), name_rules=True, max_tokens=5, business=True)
        if sp:
            rel.append(sp)
    out = [_e(T.PERSON, s, e, 0.85) for s, e in rel]
    for m in _HONORIFIC_RE.finditer(text):
        sp = _word_span(m.group("v"), m.start("v"), name_rules=True, max_tokens=4, business=True)
        if not sp or any(s <= sp[0] and sp[1] <= e for s, e in rel):
            continue
        prev = re.search(r"([A-Za-z]+)[ \t]+$", text[max(0, m.start() - 20):m.start()])
        if prev and prev.group(1).lower() in _BUSINESS:
            continue
        out.append(_e(T.PERSON, sp[0], sp[1], 0.8))
    return out


_DETECTORS = (
    find_aadhaar_unverified, find_aadhaar_vid, find_bank_account, find_passport, find_voter_id,
    find_abha_number, find_imei, find_pin_code, find_card_extras, find_social_handle, find_geo,
    find_dates, find_age, find_labelled_fields, find_titled_names,
)


def find_context(text: str) -> list[Entity]:
    """All context-dependent hits (unresolved overlaps). `text` should be normalised."""
    out: list[Entity] = []
    for fn in _DETECTORS:
        out += fn(text)
    return out
