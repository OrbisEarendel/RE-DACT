"""Entity type names produced by the regex / context detectors, in one place.

Why a file for this: AGENTS.md section 6 says WHAT counts as PII (and at which level) is a
human decision in policy/policy.py. These constants only name what the detectors can emit.
SUGGESTED_LEVEL is a starting point for the policy table (AGENTS.md section 6), not the policy.

No logging, no I/O.
"""

# --- Government / institutional identifiers (DPDP s.15(c): "unique identifier, proof of
#     identity or proof of address issued by the State") ------------------------------------
AADHAAR = "AADHAAR"
AADHAAR_VID = "AADHAAR_VID"
PAN = "PAN"
PASSPORT = "PASSPORT"
VOTER_ID = "VOTER_ID"
DRIVING_LICENCE = "DRIVING_LICENCE"
VEHICLE_REG = "VEHICLE_REG"
GSTIN = "GSTIN"
ABHA_ID = "ABHA_ID"
USN = "USN"

# --- Contact -------------------------------------------------------------------------------
PHONE = "PHONE"
EMAIL = "EMAIL"
SOCIAL_PROFILE = "SOCIAL_PROFILE"
SOCIAL_HANDLE = "SOCIAL_HANDLE"

# --- Financial -----------------------------------------------------------------------------
IFSC = "IFSC"
BANK_ACCOUNT = "BANK_ACCOUNT"
UPI_ID = "UPI_ID"
CARD_NUMBER = "CARD_NUMBER"
CARD_EXPIRY = "CARD_EXPIRY"
CVV = "CVV"
FINANCIAL_INFO = "FINANCIAL_INFO"

# --- Digital identifiers / location --------------------------------------------------------
IP_ADDRESS = "IP_ADDRESS"
MAC_ADDRESS = "MAC_ADDRESS"
IMEI = "IMEI"
GEO_COORDINATES = "GEO_COORDINATES"
PIN_CODE = "PIN_CODE"

# --- Quasi-identifiers (AGENTS.md L2 / L3) ---------------------------------------------------
DATE = "DATE"
DATE_OF_BIRTH = "DATE_OF_BIRTH"
AGE = "AGE"
AGE_MINOR = "AGE_MINOR"            # age < 18 -> "child" under DPDP s.2(f), s.9
PERSON = "PERSON"
ADDRESS = "ADDRESS"
CITY = "CITY"
ORGANIZATION = "ORGANIZATION"
JOB_TITLE = "JOB_TITLE"

# --- Sensitive attributes (label: value forms) ---------------------------------------------
GENDER = "GENDER"
BLOOD_GROUP = "BLOOD_GROUP"
RELIGION = "RELIGION"
CASTE = "CASTE"
DISABILITY = "DISABILITY"          # DPDP s.2(j)(ii), s.9: person with disability
HEALTH_INFO = "HEALTH_INFO"

ALL_TYPES = (
    AADHAAR, AADHAAR_VID, PAN, PASSPORT, VOTER_ID, DRIVING_LICENCE, VEHICLE_REG, GSTIN,
    ABHA_ID, USN, PHONE, EMAIL, SOCIAL_PROFILE, SOCIAL_HANDLE, IFSC, BANK_ACCOUNT, UPI_ID,
    CARD_NUMBER, CARD_EXPIRY, CVV, FINANCIAL_INFO, IP_ADDRESS, MAC_ADDRESS, IMEI,
    GEO_COORDINATES, PIN_CODE, DATE, DATE_OF_BIRTH, AGE, AGE_MINOR, PERSON, ADDRESS, CITY,
    ORGANIZATION, JOB_TITLE, GENDER, BLOOD_GROUP, RELIGION, CASTE, DISABILITY, HEALTH_INFO,
)

# Suggested lowest level at which each type should be acted on (AGENTS.md section 6):
#   L1 direct identifiers | L2 + quasi-identifiers | L3 + city/org/address
SUGGESTED_LEVEL = {
    # L1
    AADHAAR: 1, AADHAAR_VID: 1, PAN: 1, PASSPORT: 1, VOTER_ID: 1, DRIVING_LICENCE: 1,
    VEHICLE_REG: 1, GSTIN: 1, ABHA_ID: 1, USN: 1, PHONE: 1, EMAIL: 1, SOCIAL_PROFILE: 1,
    SOCIAL_HANDLE: 1, IFSC: 1, BANK_ACCOUNT: 1, UPI_ID: 1, CARD_NUMBER: 1, CARD_EXPIRY: 1,
    CVV: 1, IP_ADDRESS: 1, MAC_ADDRESS: 1, IMEI: 1, PERSON: 1,
    # L2
    DATE: 2, DATE_OF_BIRTH: 2, AGE: 2, AGE_MINOR: 2, JOB_TITLE: 2, FINANCIAL_INFO: 2,
    GENDER: 2, BLOOD_GROUP: 2, RELIGION: 2, CASTE: 2, DISABILITY: 2, HEALTH_INFO: 2,
    # L3
    CITY: 3, ORGANIZATION: 3, ADDRESS: 3, PIN_CODE: 3, GEO_COORDINATES: 3,
}
assert set(SUGGESTED_LEVEL) == set(ALL_TYPES)

# Tie-break order when two detectors produce the same span (earlier = wins).
PRIORITY = (
    AADHAAR, AADHAAR_VID, PAN, GSTIN, CARD_NUMBER, IMEI, PASSPORT, DRIVING_LICENCE, VOTER_ID,
    VEHICLE_REG, USN, ABHA_ID, UPI_ID, EMAIL, PHONE, IFSC, BANK_ACCOUNT, DATE_OF_BIRTH, DATE,
    AGE_MINOR, AGE, IP_ADDRESS, MAC_ADDRESS, GEO_COORDINATES, PIN_CODE, SOCIAL_PROFILE,
    SOCIAL_HANDLE, CVV, CARD_EXPIRY, PERSON, GENDER, BLOOD_GROUP, RELIGION, CASTE, DISABILITY,
    HEALTH_INFO, FINANCIAL_INFO, JOB_TITLE, CITY, ORGANIZATION, ADDRESS,
)
assert set(PRIORITY) == set(ALL_TYPES)
