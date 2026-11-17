# RE-DACT: PII Legal Reference

> This document maps **Indian law** to our detector entity types.
> It is the human policy decision layer referenced in AGENTS.md §6.
> The two primary laws are:
> 1. **DPDP Act 2023** — `policy/refs/DPDP_Act_2023_Official_Gazette.pdf` (the lawsonpii.pdf you added)
> 2. **IT (SPDI) Rules 2011** — Rule 3, under Information Technology Act 2000

---

## Law 1: DPDP Act 2023 (No. 22 of 2023) — Official Gazette, 11 Aug 2023

### Key Definitions

**§2(t) — "Personal data"**
> Any data about an individual who is **identifiable** by or in relation to such data.

No subcategories of "sensitive" vs "normal" — the DPDP Act treats ALL personal data uniformly under the same protections. The tiering distinction instead comes from the older IT Rules below.

**§2(c) — "Child"**
> Any individual who has **not completed 18 years** of age.
> → `AGE_MINOR` type must always be treated as **highest risk**, regardless of level.

**§9 — Children / Persons with Disability**
> Processing data of a child requires **verifiable parental consent**.
> No tracking, behavioural monitoring, or targeted advertising at children.
> → Any `AGE_MINOR` entity triggers a warning in our verify/report step.

**§15(c) — Duties of Data Principal (explicitly lists PII categories)**
> Must not suppress material information when providing:
> - **personal data**
> - **unique identifier** (Aadhaar, PAN, Passport, Voter ID, Driving Licence, GSTIN, ABHA, USN)
> - **proof of identity** issued by the State
> - **proof of address** issued by the State
> → These are our **L1 direct identifiers**.

**§8(5) — Security Safeguards**
> Data Fiduciary shall take reasonable security safeguards to prevent **personal data breach**.
> Penalty: up to ₹250 crore (Schedule, Item 1).

---

## Law 2: IT (SPDI) Rules 2011 — Rule 3

The older law (pre-DPDP) is still relevant because it **explicitly enumerates** Sensitive Personal Data categories, which DPDP 2023 absorbed without re-listing them.

### Rule 3 — Sensitive Personal Data or Information (SPDI)

| # | SPDI Category (Rule 3) | Our Detector Type | Our Level |
|---|---|---|---|
| 1 | **Password** | (not in scope — text redaction) | — |
| 2 | **Financial information** — bank account, credit card, debit card, payment instruments | `BANK_ACCOUNT`, `CARD_NUMBER`, `CARD_EXPIRY`, `CVV`, `UPI_ID`, `IFSC` | L1 |
| 3 | **Physical, physiological and mental health condition** | `HEALTH_INFO`, `DISABILITY` | L2 |
| 4 | **Sexual orientation** | `GENDER` (when context indicates orientation) | L2 |
| 5 | **Medical records and history** | `HEALTH_INFO` | L2 |
| 6 | **Biometric information** — fingerprints, retinas, iris, voice, facial patterns, DNA | `[PHOTO]` (face), `[QR]` (Aadhaar biometric QR) | L1 |

> Rule 3 Proviso: Freely available / public domain info is NOT SPDI. This aligns with our
> confidence scoring — public records get lower scores, not removed at L1.

---

## Combined PII Taxonomy for RE-DACT

### L1 — Direct Identifiers (always redact first)
*DPDP §15(c) "unique identifier / proof of identity / proof of address" + IT Rules Rule 3 financial + biometric*

| Type | Law Basis | Description |
|---|---|---|
| `AADHAAR` | DPDP §15(c), Aadhaar Act 2016 | 12-digit UID, Verhoeff checksum |
| `AADHAAR_VID` | DPDP §15(c) | 16-digit virtual ID |
| `PAN` | DPDP §15(c), IT Act | Permanent Account Number |
| `PASSPORT` | DPDP §15(c) | Indian passport number |
| `VOTER_ID` | DPDP §15(c) | EPIC number |
| `DRIVING_LICENCE` | DPDP §15(c) | DL number |
| `VEHICLE_REG` | DPDP §15(c) | Vehicle registration plate |
| `GSTIN` | DPDP §15(c) | GST Identification Number |
| `ABHA_ID` | DPDP §15(c), NHA | Ayushman Bharat Health Account ID |
| `USN` | DPDP §15(c) | University Seat Number (VTU-style) |
| `PERSON` | DPDP §2(t) | Full name of an individual |
| `PHONE` | DPDP §2(t) | Mobile / landline number |
| `EMAIL` | DPDP §2(t) | Email address |
| `SOCIAL_PROFILE` | DPDP §2(t) | LinkedIn, GitHub, Instagram, etc. |
| `SOCIAL_HANDLE` | DPDP §2(t) | @username on social platforms |
| `BANK_ACCOUNT` | IT Rules Rule 3(ii) | Bank account number |
| `CARD_NUMBER` | IT Rules Rule 3(ii) | Credit / debit card number (Luhn) |
| `CARD_EXPIRY` | IT Rules Rule 3(ii) | Card expiry date |
| `CVV` | IT Rules Rule 3(ii) | Card CVV |
| `UPI_ID` | IT Rules Rule 3(ii) | UPI payment handle |
| `IFSC` | IT Rules Rule 3(ii) | Bank IFSC code |
| `IP_ADDRESS` | DPDP §2(t) | IP address (online identifier) |
| `MAC_ADDRESS` | DPDP §2(t) | MAC address (device identifier) |
| `IMEI` | DPDP §2(t) | Device IMEI |
| `[PHOTO]` | IT Rules Rule 3(vi) biometric | Face/portrait in document |
| `[QR]` | IT Rules Rule 3(vi) biometric | QR code (may encode Aadhaar biometric) |

### L2 — Quasi-Identifiers + Sensitive Attributes
*DPDP §2(t) (identifiable by combination) + IT Rules Rule 3(iii)(iv)(v)*

| Type | Law Basis | Description |
|---|---|---|
| `DATE` | DPDP §2(t) | Generic dates (can narrow identity) |
| `DATE_OF_BIRTH` | DPDP §2(t) | DOB specifically |
| `AGE` | DPDP §2(t) | Age (can narrow identity) |
| `AGE_MINOR` | DPDP §2(c), §9 | Age < 18 — highest risk, parental consent |
| `JOB_TITLE` | DPDP §2(t) | Professional role |
| `GENDER` | IT Rules Rule 3(iv) | Gender / sexual orientation |
| `BLOOD_GROUP` | IT Rules Rule 3(iii) | Health condition |
| `HEALTH_INFO` | IT Rules Rule 3(iii)(v) | Medical condition / history |
| `DISABILITY` | DPDP §2(j)(ii), §9 | Person with disability |
| `RELIGION` | DPDP §2(t) (identifiable) | Religious belief |
| `CASTE` | DPDP §2(t) (identifiable) | Caste / community |
| `FINANCIAL_INFO` | IT Rules Rule 3(ii) | General financial context |

### L3 — Location / Organisational Quasi-Identifiers
*DPDP §2(t) — identifiable by combination with L1/L2*

| Type | Law Basis | Description |
|---|---|---|
| `ADDRESS` | DPDP §15(c) "proof of address" | Street / residential address |
| `CITY` | DPDP §2(t) | City / district name |
| `PIN_CODE` | DPDP §2(t) | Postal code |
| `GEO_COORDINATES` | DPDP §2(t) | Lat/long |
| `ORGANIZATION` | DPDP §2(t) | Employer / institution name |

### L4 — Everything (Synthetic replacement)
All of the above types, fully synthesised with realistic fake values.

---

## What DPDP 2023 Does NOT Cover (but we redact anyway)
These are not in DPDP 2023 but are real PII in Indian context:

| Entity | Why we include |
|---|---|
| `USN` | Unique student identifier — uniquely identifies a person in a university |
| `[PHOTO]` / `[QR]` | Visual biometrics — Rule 3(vi) IT Rules |
| `VEHICLE_REG` | Traceable to owner via VAHAN database |
| `SOCIAL_PROFILE` / `SOCIAL_HANDLE` | Direct linkage to real-world identity |

---

## References
1. **lawsonpii.pdf** = `policy/refs/DPDP_Act_2023_Official_Gazette.pdf`
   — The Digital Personal Data Protection Act, 2023 (No. 22 of 2023), Gazette of India, 11 August 2023
2. **IT (SPDI) Rules 2011** — Rule 3, Information Technology (Reasonable Security Practices and Procedures and Sensitive Personal Data or Information) Rules, 2011, under IT Act 2000 §43A (since repealed by DPDP §44(2)(a), but categories remain relevant)
3. **Aadhaar Act 2016** — §29 prohibits publishing Aadhaar number
4. **DPDP Draft Rules 2025** (expected) — will add specific rules for children's data, consent managers

---

*Last updated: 2026-11-17 | Maintainer: Ganapati branch*
