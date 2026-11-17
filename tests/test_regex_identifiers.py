"""Format/checksum detectors beyond USN / Aadhaar / PAN. Dummy data only: card, IMEI, GSTIN and
Aadhaar-shaped numbers are generated from obviously fake payloads, never real ones.

Per detector (AGENTS.md section 10): a true positive, near-misses, and a messy-context case."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from redact.detect.checksum import gstin_check_char, luhn_check_digit, verhoeff_check_digit  # noqa: E402
from redact.detect.regex_rules import (  # noqa: E402
    find, find_all, find_card, find_email, find_gstin, find_ifsc, find_network_ids, find_phone,
    find_profile_urls, find_upi, find_vehicle_and_licence, normalize,
)
from redact.entity import Entity  # noqa: E402


def texts(ents, text):
    return [(e.type, text[e.start:e.end]) for e in ents]


def card(payload15: str, group="") -> str:
    n = payload15 + luhn_check_digit(payload15)
    return group.join([n[i:i + 4] for i in range(0, len(n), 4)]) if group else n


VISA = card("411111111111111")                   # 16 digits
VISA_SP = card("411111111111111", " ")
MC = card("555555555555444")
AMEX = "37828224631000" + luhn_check_digit("37828224631000")   # 15 digits
GSTIN = "27AAPFU0939F1Z" + gstin_check_char("27AAPFU0939F1Z")


# ------------------------------------------------------------------------- phone

@pytest.mark.parametrize("num", [
    "9876543210", "98765 43210", "98765-43210", "+91 98765 43210", "+91-9876543210",
    "+919876543210", "0091 98765 43210", "91 9876543210", "09876543210", "0 98765 43210",
    "987 654 3210", "9876 543210", "6000000000", "7012345678", "8123456789",
])
def test_phone_true_positive(num):
    text = f"Call {num} now"
    assert texts(find_phone(text), text) == [("PHONE", num)]


@pytest.mark.parametrize("num", ["080-23456789", "0824 2345678", "(080) 23456789", "011-23456789"])
def test_landline_true_positive(num):
    text = f"Office: {num}."
    assert texts(find_phone(text), text) == [("PHONE", num)]


@pytest.mark.parametrize("text", [
    "5876543210",              # starts with 5, not a mobile number
    "987654321",               # 9 digits
    "98765432101",             # 11 digits glued
    "12 9876543210",           # digit group glued on the left
    "9876543210 12",           # digit group glued on the right
    "1234 5678 9876 5432",     # card-like
    "080-2345678",             # landline one digit short
    "2023-09-18",              # date
    "98765.43210",             # dot is not a separator
])
def test_phone_near_misses(text):
    assert find_phone(text) == []


def test_phone_messy_context():
    text = "ph:9876543210,alt(98765 43210);wa.me/+91 9876543210\nFax 080-23456789"
    assert [t for _, t in texts(find_phone(text), text)] == [
        "9876543210", "98765 43210", "+91 9876543210", "080-23456789"]


def test_phone_with_91_prefix_and_valid_aadhaar_shape_prefers_aadhaar():
    # 12 contiguous digits that pass Verhoeff are reported once, as Aadhaar (same span, same score).
    payload = "91987654321"
    full = payload + verhoeff_check_digit(payload)
    ents = find(f"id {full} end")
    assert [e.type for e in ents] == ["AADHAAR"]


# ------------------------------------------------------------------------- email

@pytest.mark.parametrize("mail", [
    "rahul.s@example.com", "a_b-c+tag@mail.example.co.in", "4so25cs017@college.example.edu",
    "R@EXAMPLE.ORG", "x1@sub.domain.example",
])
def test_email_true_positive(mail):
    text = f"mail {mail}."
    assert texts(find_email(text), text) == [("EMAIL", mail)]


def test_email_obfuscated():
    text = "write to rahul [at] example [dot] com or rahul(at)example(dot)co(dot)in"
    assert [t for _, t in texts(find_email(text), text)] == [
        "rahul [at] example [dot] com", "rahul(at)example(dot)co(dot)in"]


@pytest.mark.parametrize("text", [
    "user@localhost", "@handle", "a@b", "a@b.c", "x @ y.com", "name at example dot com",
    "see example.com", "foo@.com",
])
def test_email_near_misses(text):
    assert find_email(text) == []


def test_email_messy_context():
    text = "(a.b@x.in),<c@y.org>;'d@z.net'\nmailto:e@w.com"
    assert [t for _, t in texts(find_email(text), text)] == ["a.b@x.in", "c@y.org", "d@z.net", "e@w.com"]


# -------------------------------------------------------------------------- IFSC

@pytest.mark.parametrize("code", ["SBIN0001234", "hdfc0abc123", "ICIC0000001"])
def test_ifsc_true_positive(code):
    text = f"IFSC: {code}"
    assert texts(find_ifsc(text), text) == [("IFSC", code)]


@pytest.mark.parametrize("text", ["SBIN1001234", "SBI0001234", "SBIN00012345", "XSBIN0001234", "SBIN000123"])
def test_ifsc_near_misses(text):
    assert find_ifsc(text) == []


def test_ifsc_messy_context():
    text = "(SBIN0001234),IFSC=HDFC0ABC123\tand\nICIC0000001."
    assert [t for _, t in texts(find_ifsc(text), text)] == ["SBIN0001234", "HDFC0ABC123", "ICIC0000001"]


# --------------------------------------------------------------------------- UPI

@pytest.mark.parametrize("upi", ["rahul@oksbi", "9876543210@ybl", "rahul.s-1@okhdfcbank", "RA@PAYTM"])
def test_upi_true_positive(upi):
    text = f"pay to {upi}."
    assert texts(find_upi(text), text) == [("UPI_ID", upi)]


def test_abha_address():
    text = "ABHA address rahul.s12@abdm ok"
    assert texts(find_upi(text), text) == [("ABHA_ID", "rahul.s12@abdm")]


@pytest.mark.parametrize("text", ["rahul@example.com", "rahul@ybl.example.com", "rahul@unknownbank", "@ybl", "a@ybl.in"])
def test_upi_near_misses(text):
    assert find_upi(text) == []


def test_upi_wins_over_phone_inside_it_and_email_is_untouched():
    text = "9876543210@ybl and 9876543210@example.com"
    got = [(e.type, text[e.start:e.end]) for e in find(text)]
    assert got == [("UPI_ID", "9876543210@ybl"), ("EMAIL", "9876543210@example.com")]


# -------------------------------------------------------------------------- cards

@pytest.mark.parametrize("num", [VISA, VISA_SP, MC, AMEX, VISA_SP.replace(" ", "-")])
def test_card_true_positive(num):
    text = f"card {num} ok"
    assert texts(find_card(text), text) == [("CARD_NUMBER", num)]


def test_card_amex_grouping_4_6_5():
    g = f"{AMEX[:4]} {AMEX[4:10]} {AMEX[10:]}"
    text = f"amex {g}"
    assert texts(find_card(text), text) == [("CARD_NUMBER", g)]


@pytest.mark.parametrize("text", [
    "4111111111111112",                 # Luhn fails
    "1111111111111117",                 # Luhn ok, no issuer range
    "411111111111",                     # 12 digits
    "41111111111111111111",             # 20 digits
    "12 " + VISA,                       # glued digit group
    VISA + " 12",
])
def test_card_near_misses(text):
    assert find_card(text) == []


def test_card_is_not_reported_as_aadhaar():
    ents = find(f"number {VISA_SP}")
    assert [e.type for e in ents] == ["CARD_NUMBER"]


# ------------------------------------------------------------------------- GSTIN

def test_gstin_true_positive_and_pan_not_reported_twice():
    text = f"GSTIN {GSTIN} PAN of firm"
    assert texts(find_gstin(text), text) == [("GSTIN", GSTIN)]
    assert [(e.type, text[e.start:e.end]) for e in find(text)] == [("GSTIN", GSTIN)]


@pytest.mark.parametrize("text", [
    "27AAPFU0939F1ZW",     # wrong check character
    "27AAPFU0939F1Y" + gstin_check_char("27AAPFU0939F1Y"),   # 14th char must be Z
    "27AAPFU0939F1Z",      # too short
    "X" + GSTIN,
])
def test_gstin_near_misses(text):
    assert find_gstin(text) == []


def test_gstin_lowercase():
    text = f"gst {GSTIN.lower()}"
    assert texts(find_gstin(text), text) == [("GSTIN", GSTIN.lower())]


# ----------------------------------------------------- vehicle / driving licence

@pytest.mark.parametrize("plate", ["KA19AB1234", "KA 19 MA 1234", "MH-12-DE-1433", "DL1CAB1234", "TS09EA0001", "22BH1234AA"])
def test_vehicle_true_positive(plate):
    text = f"car {plate} parked"
    assert texts(find_vehicle_and_licence(text), text) == [("VEHICLE_REG", plate)]


@pytest.mark.parametrize("text", [
    "XX19AB1234",           # not a state code
    "ka19ab1234",           # state code must be capitals (avoids matching ordinary words)
    "KA19AB123",            # 3 digits
    "KA19AB12345",          # 5 digits
    "or 12 ab 1234",        # the word "or"
    "KA19ABCD1234",         # 4 letters
])
def test_vehicle_near_misses(text):
    assert find_vehicle_and_licence(text) == []


@pytest.mark.parametrize("dl", ["KA0120110012345", "KA01 20110012345", "KA-01-2011-0012345", "MH12 20190001234"])
def test_driving_licence_true_positive(dl):
    text = f"DL {dl}."
    assert texts(find_vehicle_and_licence(text), text) == [("DRIVING_LICENCE", dl)]


def test_driving_licence_near_miss():
    assert find_vehicle_and_licence("KA0118110012345") == []      # year 18xx
    assert find_vehicle_and_licence("KA012011001234") == []       # 6 trailing digits


# ----------------------------------------------------------------- network ids

@pytest.mark.parametrize("ip", ["192.168.1.10", "10.0.0.1", "255.255.255.255", "8.8.8.8"])
def test_ipv4_true_positive(ip):
    text = f"from {ip}:8080"
    assert texts(find_network_ids(text), text) == [("IP_ADDRESS", ip)]


@pytest.mark.parametrize("ip", ["2001:db8::1", "fe80::1ff:fe23:4567:890a", "::1",
                                 "2001:0db8:85a3:0000:0000:8a2e:0370:7334"])
def test_ipv6_true_positive(ip):
    text = f"addr {ip} up"
    assert texts(find_network_ids(text), text) == [("IP_ADDRESS", ip)]


def test_mac_true_positive():
    text = "mac 00:1A:2B:3C:4D:5E and 00-1a-2b-3c-4d-5f"
    assert [t for _, t in texts(find_network_ids(text), text)] == ["00:1A:2B:3C:4D:5E", "00-1a-2b-3c-4d-5f"]


@pytest.mark.parametrize("text", [
    "256.1.1.1", "1.2.3", "1.2.3.4.5", "version 1.2.3.4", "v2.3.4.5", "10:30:45",
    "12:34", "01.02.2023", "00:1A:2B:3C:4D",
])
def test_network_near_misses(text):
    assert find_network_ids(text) == []


# ------------------------------------------------------------- profile URLs

@pytest.mark.parametrize("url", [
    "https://www.linkedin.com/in/rahul-s", "linkedin.com/in/rahul-s/", "github.com/rahul-s",
    "https://instagram.com/rahul_s", "twitter.com/rahul_s", "wa.me/919876543210",
])
def test_profile_url_true_positive(url):
    text = f"see {url} for more"
    (e,) = find_profile_urls(text)
    assert e.type == "SOCIAL_PROFILE" and text[e.start:e.end] == url.rstrip("/")


@pytest.mark.parametrize("text", ["github.com", "see example.com/in/x", "linkedin.com/company"])
def test_profile_url_near_misses(text):
    assert find_profile_urls(text) == []


# ---------------------------------------------------- normalisation / Indic digits

def test_normalize_keeps_length_and_maps_digits():
    kn = "".join(chr(0x0CE6 + int(d)) for d in "9876543210")
    hi = "".join(chr(0x0966 + int(d)) for d in "9876543210")
    full = "".join(chr(0xFF10 + int(d)) for d in "9876543210")
    for s in (kn, hi, full):
        assert normalize(s) == "9876543210" and len(normalize(s)) == len(s)
    assert normalize("a\u00a0b\u2013c") == "a b-c"
    assert normalize("plain") == "plain"


def test_indic_digit_phone_and_aadhaar_found_with_original_offsets():
    payload = "23456789012"
    a = payload + verhoeff_check_digit(payload)
    kn = lambda s: "".join(chr(0x0CE6 + int(ch)) if ch.isdigit() else ch for ch in s)  # noqa: E731
    text = f"ಆಧಾರ್ {kn(a[:4])} {kn(a[4:8])} {kn(a[8:])} ಫೋನ್ {kn('9876543210')}"
    got = [(e.type, text[e.start:e.end]) for e in find(text)]
    assert got == [("AADHAAR", f"{kn(a[:4])} {kn(a[4:8])} {kn(a[8:])}"), ("PHONE", kn("9876543210"))]


def test_non_breaking_space_and_en_dash_separators():
    text = "ph 98765\u00a043210 and 98765\u201343210"
    assert [text[e.start:e.end] for e in find(text)] == ["98765\u00a043210", "98765\u201343210"]


# ------------------------------------------------------------------ find / resolve

def test_find_all_is_unresolved_and_find_has_no_overlaps():
    text = "Name: Rahul, phone 9876543210, UPI 9876543210@ybl, mail 4so25cs017@college.example"
    raw = find_all(text)
    res = find(text)
    assert len(raw) > len(res)
    for a, b in zip(res, res[1:]):
        assert a.end <= b.start
    assert [e.type for e in res if e.type in ("UPI_ID", "EMAIL")] == ["UPI_ID", "EMAIL"]


def test_free_text_span_is_cut_around_a_phone_number_not_dropped():
    text = "Address: 12 MG Road, Mangaluru, ph 98765 43210, Karnataka"
    got = [(e.type, text[e.start:e.end]) for e in find(text)]
    assert ("PHONE", "98765 43210") in got
    assert any(t == "ADDRESS" and "MG Road" in s for t, s in got)
    assert any(t == "ADDRESS" and "Karnataka" in s for t, s in got)


def test_entities_are_plain_entity_objects_with_source_regex():
    for e in find(f"{VISA} 9876543210 a@b.com 192.168.1.10"):
        assert isinstance(e, Entity) and e.source == "regex" and 0 < e.score <= 1.0


def test_no_new_fields_on_entity():
    assert set(Entity.__dataclass_fields__) == {"type", "start", "end", "score", "source"}


def test_idempotent_and_does_not_mutate_or_log(capsys):
    text = f"USN 4SO25CS017 {VISA} 9876543210 a@b.com SBIN0001234"
    before = text
    assert find(text) == find(text)
    out = capsys.readouterr()
    assert text == before and out.out == "" and out.err == ""


def test_plain_prose_has_no_hits():
    prose = ("The committee met on the third floor to review the budget. Version two of the "
             "document was shared; nothing here identifies anyone.")
    assert find(prose) == []
