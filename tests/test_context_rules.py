"""Context-word and "Label: value" detectors. Dummy data only (generated checksums, made-up names).

Per detector (AGENTS.md section 10): a true positive, near-misses that must NOT match, and a
messy-context case."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from redact.detect import context_rules as C  # noqa: E402
from redact.detect.checksum import luhn_check_digit, verhoeff_check_digit  # noqa: E402
from redact.detect.regex_rules import find  # noqa: E402


def texts(ents, text):
    return [(e.type, text[e.start:e.end]) for e in ents]


def grp(n, sizes, sep=" "):
    out, i = [], 0
    for s in sizes:
        out.append(n[i:i + s]); i += s
    return sep.join(out)


A_OK = "23456789012" + verhoeff_check_digit("23456789012")
A_BAD = A_OK[:-1] + ("0" if A_OK[-1] != "0" else "1")
_p = "234567890123456"
VID = _p + verhoeff_check_digit(_p)                       # 16 digits
IMEI = "49015420323751" + luhn_check_digit("49015420323751")


# --------------------------------------------------------- Aadhaar (unverified)

def test_aadhaar_with_one_wrong_digit_is_reported_at_lower_score_when_keyword_nearby():
    text = f"Aadhaar No: {grp(A_BAD, (4, 4, 4))}"
    (e,) = C.find_aadhaar_unverified(text)
    assert (e.type, e.score) == ("AADHAAR", 0.7)
    assert text[e.start:e.end] == grp(A_BAD, (4, 4, 4))


@pytest.mark.parametrize("kw", ["aadhar", "Adhaar", "UIDAI", "UID", "आधार", "ಆಧಾರ್"])
def test_aadhaar_unverified_keywords(kw):
    text = f"{kw}: {A_BAD}"
    assert [t for _, t in texts(C.find_aadhaar_unverified(text), text)] == [A_BAD]


@pytest.mark.parametrize("text", [
    f"order {A_BAD}",                                    # no keyword
    f"Aadhaar {A_OK}",                                   # checksum OK: handled by find_aadhaar
    f"Aadhaar 1{A_BAD[1:]}",                             # starts with 1
    f"Aadhaar 12 {A_BAD}",                               # glued digit group
    "Aadhaar 2345 6789",                                 # too short
])
def test_aadhaar_unverified_near_misses(text):
    assert C.find_aadhaar_unverified(text) == []


def test_aadhaar_valid_number_is_reported_once_at_full_score():
    text = f"Aadhaar: {A_OK}"
    ents = find(text)
    assert [(e.type, e.score) for e in ents] == [("AADHAAR", 1.0)]


# ------------------------------------------------------------------- Aadhaar VID

def test_vid_true_positive():
    text = f"VID: {grp(VID, (4, 4, 4, 4))}"
    assert texts(C.find_aadhaar_vid(text), text) == [("AADHAAR_VID", grp(VID, (4, 4, 4, 4)))]


@pytest.mark.parametrize("text", [
    f"number {VID}",                                     # no keyword
    f"VID {VID[:-1]}{(int(VID[-1]) + 1) % 10}",          # checksum fails
    f"VID 1{VID[1:]}",                                   # starts with 1
    f"VID {VID}7",                                       # 17 digits
])
def test_vid_near_misses(text):
    assert C.find_aadhaar_vid(text) == []


def test_vid_messy_context():
    text = f"(virtual ID={VID}); VID:{VID}"
    assert len(C.find_aadhaar_vid(text)) == 2


# ----------------------------------------------------------------- bank account

@pytest.mark.parametrize("text,num", [
    ("A/c No. 123456789012", "123456789012"),
    ("Account Number: 50100123456789", "50100123456789"),
    ("acct 1234567890", "1234567890"),
    ("Savings A/C no: 1234 5678 9012", "1234 5678 9012"),
    ("a.c. 123456789", "123456789"),
    ("Beneficiary account number is 9876543210123", "9876543210123"),
])
def test_bank_account_true_positive(text, num):
    (e,) = C.find_bank_account(text)
    assert (e.type, text[e.start:e.end], e.score) == ("BANK_ACCOUNT", num, 0.85)


@pytest.mark.parametrize("text", [
    "number 123456789012",                 # no keyword
    "A/c 12345678",                        # 8 digits
    "A/c 1234567890123456789012",          # 22 digits
    "account holder Rahul",                # no digits
    "account 12-03-2005",                  # a date, 8 digits
])
def test_bank_account_near_misses(text):
    assert C.find_bank_account(text) == []


def test_bank_account_messy_context():
    text = "Bank:XYZ;A/c#:123456789012,IFSC=SBIN0001234\nAcct. No - 5010012345"
    got = [(e.type, text[e.start:e.end]) for e in find(text)]
    assert ("BANK_ACCOUNT", "123456789012") in got and ("IFSC", "SBIN0001234") in got
    assert ("BANK_ACCOUNT", "5010012345") in got


# -------------------------------------------------------------------- passport

@pytest.mark.parametrize("pp", ["J8369854", "A1234567", "p1234567", "K83 69854"])
def test_passport_true_positive(pp):
    text = f"Passport No: {pp}"
    assert [t for _, t in texts(C.find_passport(text), text)] == [pp]


@pytest.mark.parametrize("text", [
    "ref J8369854",                         # no keyword
    "passport Q8369854",                    # Q is not used
    "passport J0369854",                    # 2nd char 0
    "passport J83698540",                   # 8 digits
    "passport J836985",                     # 6 digits
])
def test_passport_near_misses(text):
    assert C.find_passport(text) == []


# -------------------------------------------------------------------- voter id

def test_voter_id_scores_depend_on_keyword():
    t1, t2 = "Voter ID: ABC1234567", "code ABC1234567"
    assert [(e.type, e.score) for e in C.find_voter_id(t1)] == [("VOTER_ID", 0.95)]
    assert [(e.type, e.score) for e in C.find_voter_id(t2)] == [("VOTER_ID", 0.6)]


@pytest.mark.parametrize("text", ["abc1234567", "AB12345678", "ABCD1234567", "ABC123456", "ABC12345678"])
def test_voter_id_near_misses(text):
    assert C.find_voter_id(text) == []


# ------------------------------------------------------------------ ABHA number

def test_abha_number():
    text = "ABHA number: 12-3456-7890-1234 and ayushman 12345678901234"
    assert [t for _, t in texts(C.find_abha_number(text), text)] == ["12-3456-7890-1234", "12345678901234"]


def test_abha_near_misses():
    assert C.find_abha_number("number 12-3456-7890-1234") == []
    assert C.find_abha_number("ABHA 12-3456-7890-123") == []


# ------------------------------------------------------------------------ IMEI

def test_imei_true_positive_and_near_misses():
    text = f"IMEI: {IMEI}"
    assert texts(C.find_imei(text), text) == [("IMEI", IMEI)]
    assert C.find_imei(f"number {IMEI}") == []                      # no keyword
    bad = IMEI[:-1] + str((int(IMEI[-1]) + 1) % 10)
    assert C.find_imei(f"IMEI {bad}") == []                         # Luhn fails
    assert C.find_imei(f"IMEI {IMEI[:-1]}") == []                   # 14 digits


# --------------------------------------------------------------------- PIN code

@pytest.mark.parametrize("text,pin", [
    ("PIN: 574219", "574219"), ("Pincode 560 001", "560 001"), ("pin code - 575001", "575001"),
    ("Postal code: 400001", "400001"), ("ZIP 110001", "110001"),
])
def test_pin_true_positive(text, pin):
    assert [t for _, t in texts(C.find_pin_code(text), text)] == [pin]


@pytest.mark.parametrize("text", [
    "574219", "total 574219", "PIN 074219", "PIN 57421", "PIN 5742190", "pinned 574219",
])
def test_pin_near_misses(text):
    assert C.find_pin_code(text) == []


# -------------------------------------------------------------- CVV / card expiry

def test_cvv_and_expiry():
    text = "CVV: 123, cvc 4567, expiry 08/27, valid thru 12/2030, Exp Date: 01/26"
    got = [(e.type, text[e.start:e.end]) for e in C.find_card_extras(text)]
    assert got == [("CVV", "123"), ("CVV", "4567"), ("CARD_EXPIRY", "08/27"),
                   ("CARD_EXPIRY", "12/2030"), ("CARD_EXPIRY", "01/26")]


@pytest.mark.parametrize("text", ["cvv 12", "cvv 12345", "123", "expiry 13/27", "exp 00/27", "valid thru 8/27"])
def test_card_extras_near_misses(text):
    assert C.find_card_extras(text) == []


# ---------------------------------------------------------------- social handles

def test_social_handle_needs_social_keyword_right_before():
    text = "Instagram: @rahul_s, Telegram @rahul.s2 and twitter - @rs"
    got = [t for _, t in texts(C.find_social_handle(text), text)]
    assert got == ["@rahul_s", "@rahul.s2"]            # "@rs" is too short


@pytest.mark.parametrize("text", ["@dataclass", "@pytest.fixture", "mail me @ home", "follow @rahul_s now"])
def test_social_handle_near_misses(text):
    assert C.find_social_handle(text) == []


# ------------------------------------------------------------------ coordinates

def test_geo_true_positive():
    text = "location 12.9141, 74.8560 and lat: 51.5007, -0.1246 and (12.914100,74.856000)"
    assert [t for _, t in texts(C.find_geo(text), text)] == [
        "12.9141, 74.8560", "51.5007, -0.1246", "12.914100,74.856000"]


@pytest.mark.parametrize("text", [
    "pi is 3.14159, 2.71828", "values 91.1234, 74.8560", "12.9, 74.8", "12.9141 74.8560", "version 1.2345, 5.6789",
])
def test_geo_near_misses(text):
    assert C.find_geo(text) == []


# ------------------------------------------------------------------------ dates

@pytest.mark.parametrize("d", [
    "12/03/2005", "12-03-2005", "12.03.2005", "2005-03-12", "2005/3/12", "12 March 2005",
    "12th Mar 2005", "March 12, 2005", "Mar 12th 2005", "1 sept 1999", "29/02/2004", "02/29/2004",
])
def test_date_true_positive(d):
    text = f"on {d}."
    (e,) = C.find_dates(text)
    assert (e.type, text[e.start:e.end]) == ("DATE", d)


@pytest.mark.parametrize("text", [
    "31/02/2005",          # no such day
    "29/02/2005",          # not a leap year
    "13/13/2005",          # no such month
    "12/03/1850",          # outside 1900-2099
    "12/03/05",            # 2-digit year without a birth keyword
    "1.2.3.4",
    "12 March",            # no year
    "March 2005",          # month + year only
    "v12-03-2005x",
])
def test_date_near_misses(text):
    assert C.find_dates(text) == []


@pytest.mark.parametrize("text,d", [
    ("DOB: 12/03/2005", "12/03/2005"), ("D.O.B. 12-03-2005", "12-03-2005"),
    ("Date of Birth: 12 March 2005", "12 March 2005"), ("born on 2005-03-12", "2005-03-12"),
    ("DOB (dd/mm/yy): 12/03/05".replace("(dd/mm/yy): ", " "), "12/03/05"),
])
def test_date_of_birth_with_keyword(text, d):
    (e,) = C.find_dates(text)
    assert (e.type, text[e.start:e.end]) == ("DATE_OF_BIRTH", d)


def test_date_iso_timestamp_and_messy_context():
    text = "(12/03/2005),2005-03-12T10:30:00Z;\n12.03.2005\tMarch 12,2005"
    assert len(C.find_dates(text)) == 4


# --------------------------------------------------------------------------- age

@pytest.mark.parametrize("text,n,typ", [
    ("Age: 34", "34", "AGE"), ("aged 45", "45", "AGE"), ("age of 29", "29", "AGE"),
    ("a 34 years old man", "34", "AGE"), ("34-year-old", "34", "AGE"), ("34 yo", "34", "AGE"),
    ("34 y/o", "34", "AGE"), ("Age/Sex: 34/M", "34", "AGE"), ("age = 52", "52", "AGE"),
    ("Age: 12", "12", "AGE_MINOR"), ("she is 7 years old", "7", "AGE_MINOR"), ("aged 17", "17", "AGE_MINOR"),
    ("age: 18", "18", "AGE"),
])
def test_age_true_positive(text, n, typ):
    (e,) = C.find_age(text)
    assert (e.type, text[e.start:e.end]) == (typ, n)


@pytest.mark.parametrize("text", [
    "children under 18 years old", "over 60 years old", "between 18 and 25 years old",
    "5 years of experience", "age: 150", "Age: 34%", "age 3 months", "version 34 years",
    "aged", "at least 21 years old", "1999 years old",
])
def test_age_near_misses(text):
    assert C.find_age(text) == []


# ---------------------------------------------------------------- labelled fields

def labelled(text):
    return [(e.type, text[e.start:e.end]) for e in C.find_labelled_fields(text)]


def test_name_fields():
    text = ("Name: Rahul Sharma  USN: 4SO25CS017\n"
            "Student Name: PRIYA NAIR\nFather's Name: Ramesh Nair\nFull name - Anil K. Rao\n"
            "Name of the candidate: Meera Iyer Roll No: 12")
    got = [t for ty, t in labelled(text) if ty == "PERSON"]
    assert got == ["Rahul Sharma", "PRIYA NAIR", "Ramesh Nair", "Anil K. Rao", "Meera Iyer"]


def test_name_field_works_with_single_space_ocr_text():
    text = "USN: 4SO25CS017 Name: Rahul Sharma Gender: Male Age: 20"
    assert ("PERSON", "Rahul Sharma") in labelled(text)
    assert ("GENDER", "Male") in labelled(text)


@pytest.mark.parametrize("text", [
    "File name: report.pdf", "user name: john", "Company name: N/A", "Name: N/A", "Name: none",
    "Name based routing", "Name-based routing", "the name: is", "Name:", "Name: 12345",
    "Table name: orders", "Product name: Widget Pro",
])
def test_name_field_near_misses(text):
    assert [t for ty, t in labelled(text) if ty == "PERSON"] == []


def test_name_field_stops_at_sentence_and_next_label():
    assert labelled("Name: John Smith is a student")[0] == ("PERSON", "John Smith")
    assert labelled("Name: rahul sharma. Next")[0] == ("PERSON", "rahul sharma")
    assert labelled("Name: Rahul USN: 4SO25CS017")[0] == ("PERSON", "Rahul")


def test_address_city_org_job():
    text = ("Address: 12 MG Road, Mangaluru 574219\n"
            "Permanent Address: 4-5 Temple St, Udupi\n"
            "City: Udupi  District: Dakshina Kannada\n"
            "Company name: Acme Pvt Ltd, Bengaluru\nCollege: SDM College Sem: 4 Branch: CS\n"
            "Designation: Software Engineer, Occupation: Teacher")
    got = labelled(text)
    assert ("ADDRESS", "12 MG Road, Mangaluru 574219") in got
    assert ("ADDRESS", "4-5 Temple St, Udupi") in got
    assert ("CITY", "Udupi") in got and ("CITY", "Dakshina Kannada") in got
    assert ("ORGANIZATION", "Acme Pvt Ltd") in got and ("ORGANIZATION", "SDM College") in got
    assert ("JOB_TITLE", "Software Engineer") in got and ("JOB_TITLE", "Teacher") in got


@pytest.mark.parametrize("text", [
    "Email address: a@b.com", "IP address: 10.0.0.1", "Address: N/A", "Address: -",
    "City: none", "Designation: -", "address", "Company: ",
])
def test_address_and_line_near_misses(text):
    got = [x for x in labelled(text) if x[0] in ("ADDRESS", "CITY", "JOB_TITLE", "ORGANIZATION")]
    assert got == []


def test_sensitive_attribute_fields():
    text = ("Gender: Female  Sex: M\nBlood group: O+  Blood Type: AB negative\n"
            "Religion: Hindu  Caste: Vokkaliga  Category: OBC\n"
            "Disability: Visual impairment  Diagnosis: Type 2 diabetes  Allergies: penicillin\n"
            "Salary: Rs. 50,000 per month  Annual income: ₹4.5 lakhs  CIBIL score: 750")
    got = labelled(text)
    for item in [("GENDER", "Female"), ("GENDER", "M"), ("BLOOD_GROUP", "O+"), ("BLOOD_GROUP", "AB negative"),
                 ("RELIGION", "Hindu"), ("CASTE", "Vokkaliga"), ("CASTE", "OBC"),
                 ("DISABILITY", "Visual impairment"), ("HEALTH_INFO", "Type 2 diabetes"),
                 ("HEALTH_INFO", "penicillin"), ("FINANCIAL_INFO", "Rs. 50,000 per month"),
                 ("FINANCIAL_INFO", "₹4.5 lakhs"), ("FINANCIAL_INFO", "750")]:
        assert item in got


@pytest.mark.parametrize("text", [
    "Gender: unknown", "Blood group: C+", "Disability: None", "Disability: No", "Salary: negotiable",
    "Category: Premium", "Diagnosis: n/a", "Religion:", "gender neutral",
])
def test_sensitive_attribute_near_misses(text):
    assert labelled(text) == []


# ------------------------------------------------------------------ titled names

@pytest.mark.parametrize("text,name", [
    ("Mr. Anil Kumar attended", "Anil Kumar"), ("Mrs Priya Nair, MD", "Priya Nair"),
    ("Dr. R. K. Rao said", "R. K. Rao"), ("Smt. Lakshmi Devi", "Lakshmi Devi"),
    ("Shri Ramesh Rao visited", "Ramesh Rao"), ("Sri Ramesh Rao visited", "Ramesh Rao"),
    ("S/o Ramesh Rao, Udupi", "Ramesh Rao"), ("D/o Late Sri Krishna", "Late Sri Krishna"),
    ("C/o Suresh Babu", "Suresh Babu"), ("wife of Anil Kumar", "Anil Kumar"),
])
def test_titled_names_true_positive(text, name):
    assert [t for _, t in texts(C.find_titled_names(text), text)] == [name]


@pytest.mark.parametrize("text", [
    "Sri Residency, Mangaluru", "Sri Nilaya Apartments", "Dr. residency", "Mr. anil", "Ms 5 items",
    "Hotel Sri Krishna Bhavan", "Prof", "Miss.",
])
def test_titled_names_near_misses(text):
    assert C.find_titled_names(text) == []


def test_sri_residency_is_not_a_person_but_sri_ramesh_is():
    text = "Stay at Sri Residency. Met Sri Ramesh Rao."
    assert [(e.type, text[e.start:e.end]) for e in find(text)] == [("PERSON", "Ramesh Rao")]


# ---------------------------------------------------------------- whole documents

def test_full_dummy_form():
    text = (
        "Student Name: Rahul Sharma  USN: 4SO25CS017\n"
        f"Aadhaar: {grp(A_OK, (4, 4, 4))}  PAN: ABCDE1234F  DOB: 12/03/2005 (Age: 20)\n"
        "Phone: +91 98765 43210  Email: rahul.s@example.com\n"
        "Address: 12 MG Road, Mangaluru 574219\n"
        "A/c No. 123456789012  IFSC: SBIN0001234  UPI: rahul@oksbi\n"
    )
    got = {(e.type, text[e.start:e.end]) for e in find(text)}
    expected = {
        ("PERSON", "Rahul Sharma"), ("USN", "4SO25CS017"), ("AADHAAR", grp(A_OK, (4, 4, 4))),
        ("PAN", "ABCDE1234F"), ("DATE_OF_BIRTH", "12/03/2005"), ("AGE", "20"),
        ("PHONE", "+91 98765 43210"), ("EMAIL", "rahul.s@example.com"),
        ("ADDRESS", "12 MG Road, Mangaluru 574219"), ("BANK_ACCOUNT", "123456789012"),
        ("IFSC", "SBIN0001234"), ("UPI_ID", "rahul@oksbi"),
    }
    assert expected <= got


def test_context_detectors_do_not_log(capsys):
    find("Name: Rahul Sharma DOB: 12/03/2005 A/c 123456789012 Age: 20")
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_windows_line_endings():
    text = "Name: Rahul Sharma\r\nAddress: 12 MG Road, Mangaluru\r\nCity: Udupi\r\n"
    got = [(e.type, text[e.start:e.end]) for e in find(text)]
    assert got == [("PERSON", "Rahul Sharma"), ("ADDRESS", "12 MG Road, Mangaluru"), ("CITY", "Udupi")]
