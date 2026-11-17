<div align="center">

<img src="RE-DACT_logo.png" width="800" alt="RE-DACT Logo">

# RE-DACT

### Privacy-Preserving, In-Memory Document Sanitization

An offline, gradational de-identification engine for plaintext, tabular datasets, images, and PDFs.<br>
Zero cloud dependencies · In-memory processing · Real-time level slider · Tamper-evident audit trail.

**[Overview](#overview)** &nbsp;·&nbsp;
**[Ecosystem](#the-ecosystem)** &nbsp;·&nbsp;
**[Architecture](#architecture--pipeline)** &nbsp;·&nbsp;
**[Redaction Levels](#redaction-levels-l1--l4)** &nbsp;·&nbsp;
**[Format Adapters](#format-adapters)** &nbsp;·&nbsp;
**[Quickstart](#quickstart)** &nbsp;·&nbsp;
**[Security & Privacy](#security--privacy)** &nbsp;·&nbsp;
**[Evaluation](#evaluation--benchmark)** &nbsp;·&nbsp;
**[The Mark](#the-mark)**

<p>
  <a href="#quickstart"><img alt="Python 3.12" src="https://img.shields.io/badge/PYTHON-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/LICENSE-MIT-80CBC4?style=for-the-badge&labelColor=0C1213"></a>
  <a href="#architecture--pipeline"><img alt="Streamlit UI" src="https://img.shields.io/badge/UI-STREAMLIT-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white"></a>
</p>
<p>
  <img alt="OCR" src="https://img.shields.io/badge/OCR-PADDLEOCR-80CBC4?style=for-the-badge&labelColor=0C1213">
  <img alt="NER" src="https://img.shields.io/badge/NER-GLiNER%20PII-B7C7EA?style=for-the-badge&labelColor=0C1213">
  <img alt="PDF" src="https://img.shields.io/badge/PDF-PYMUPDF%20TRUE%20REDACTION-FF6F00?style=for-the-badge&labelColor=0C1213">
</p>

</div>

> [!IMPORTANT]
> **Zero Data Retention & 100% Offline by Design**<br>
> RE-DACT processes sensitive documents strictly in memory (`RAM`/`tmpfs`). It executes zero outbound network calls, depends on zero third-party cloud APIs (no OpenAI, Gemini, or cloud OCR/NER), and stores **zero raw personal data** in logs, reports, or persistent storage.

> [!TIP]
> **Gradational Privacy (L1 to L4): Detect Once, Slide Freely**<br>
> Detection runs once and caches sensitive spans. Moving the redaction slider instantly shifts transforms from light masking (L1) to quasi-identifier generalization (L2), HMAC-seeded consistent pseudonymization (L3), and synthetic generation (L4) without re-running expensive OCR or NLP models.

---

## Overview

Organizations across healthcare, law, finance, and government need to share documents and datasets without exposing personal or proprietary information. Existing de-identification solutions are typically:
* **All-or-nothing**: blunt redactions that destroy analytical utility.
* **Fragile & manual**: regex scripts that miss contextual, indirect identifiers.
* **Cloud-leaking**: sending private payloads to external LLMs and cloud APIs.

**RE-DACT** solves this with a **deterministic, modular pipeline** built on open local NLP, rule-based checksums, and true format-native redaction adapters. It guarantees that the output matches the exact structure of the input, validates that no sensitive originals survive via an automated anti-leak verification scan, and provides cryptographic proof of sanitization through an HMAC-SHA256 signed audit report.

Built for **CONVERGE '26** (Blockchain & Cybersecurity Track) by team **StrangerStrings**.

---

## The Ecosystem

<table>
<tr>
<th width="33%">Ingestion & Detection</th>
<th width="33%">Policy & Transform</th>
<th width="33%">Adapters & Verification</th>
</tr>
<tr valign="top">
<td>

* **Content Gate**: Real MIME inspection, size caps, and decompression bomb guards
* **Dual-Path Routing**: Native extraction for digital text; PaddleOCR for scans/images
* **Regex + Checksum**: Deterministic detection with Verhoeff validation (Aadhaar, PAN, phones, emails)
* **Zero-Shot NER**: GLiNER (`urchade/gliner_multi_pii-v1`) for names, orgs, and locations
* **Context Engine**: Cue words, title rules, and mention propagation
* **Span Store**: Format-agnostic in-memory span index

</td>
<td>

* **L1 (Light)**: Masking direct identifiers (`[PERSON]`, `XXXX XXXX 1234`)
* **L2 (Medium)**: Generalizing quasi-identifiers (age ranges, month/year dates)
* **L3 (Strong)**: Consistent pseudonymization (HMAC-seeded `Faker` stand-ins)
* **L4 (Synthetic)**: Realistic entity synthesis & perturbed values
* **Policy Presets**: Configurable entity-level checkboxes and compliance profiles
* **In-Memory Mappings**: Ephemeral real-to-fake translation discarded after session

</td>
<td>

* **Plaintext & Logs**: Exact offset replacement preserving encoding and whitespace
* **Datasets (CSV/JSON/XLSX)**: Value modification with structure & formula preservation
* **Images**: True pixel clearing and flattening with EXIF metadata stripping
* **PDFs**: PyMuPDF true redaction (destroys underlying text/pixels; strips metadata)
* **Anti-Leak Re-scan**: Output re-extraction searching for residual originals
* **Cryptographic Report**: HMAC-SHA256 signed audit certificate

</td>
</tr>
</table>

---

## Architecture & Pipeline

RE-DACT processes files in a single unified flow where detection is performed once and all subsequent actions are governed by the selected policy level:

```
[ Input File ]
      │
      ▼
┌──────────────────┐
│  Gate & Route    │ ── Validate MIME/magic bytes, check size caps, route per page
└──────────────────┘
      │
      ├───────────────────────────────┐
      ▼                               ▼
┌──────────────────┐       ┌──────────────────┐
│ Native Extract   │       │ PaddleOCR Engine │ ── Generates word-level bounding boxes
└──────────────────┘       └──────────────────┘
      │                               │
      └───────────────┬───────────────┘
                      ▼
┌──────────────────────────────────────┐
│ NormalizedDoc (Text + Position Map)  │
└──────────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────┐
│ Detection Suite                      │
│ ├─ Regex + Checksums (Score: 1.0)    │ ── Aadhaar (Verhoeff), PAN, Phone, Email, IFSC
│ ├─ Zero-Shot GLiNER NER (Score: conf)│ ── Names, Organizations, Locations, Titles
│ └─ Context Rules & Gazetteer         │ ── Cue words ("Dr.", "Patient:"), mention propagation
└──────────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────┐
│ Span Merge (Resolve Overlaps)        │ ── Higher score wins, then longer span
└──────────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────┐
│ Policy Engine (Levels L1 – L4)       │ ── User checkboxes + Slider position
└──────────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────┐
│ Transform Engine                     │ ── Mask / Generalize / Pseudonymize / Synthesize
└──────────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────┐
│ Format Writers                       │ ── Native Text / Tabular / Image / PyMuPDF PDF
└──────────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────┐
│ Verification Loop (Anti-Leak Re-scan)│
└──────────────────────────────────────┘
      │                           │
      │ (Residuals found)         │ (Clean)
      ▼                           ▼
[ Stricter Retry ]         [ Redacted Document + Signed HMAC Report ]
```

---

## Redaction Levels (L1 – L4)

The slider controls the depth of de-identification. Changing the level updates the transform applied to detected spans without needing to re-parse the document:

| Level | Name | Target Entities | Transform Applied | Visual Example |
| :---: | :--- | :--- | :--- | :--- |
| **L1** | **Light** | Direct Identifiers (Names, Aadhaar, PAN, Phone, Email, Bank Accounts) | **Masking**: Replaced with generic tokens or partial character masks. | `Priya Sharma` $\rightarrow$ `[PERSON]`<br>`98765 43210` $\rightarrow$ `XXXXX 43210` |
| **L2** | **Medium** | L1 + Quasi-Identifiers (Ages, Exact Dates, Specific Job Titles) | **Generalization**: Reduces precision to prevent linkage attacks. | `Age 34` $\rightarrow$ `30s`<br>`14/08/1992` $\rightarrow$ `Aug 1992`<br>`Lead Neurosurgeon` $\rightarrow$ `Doctor` |
| **L3** | **Strong** | L2 + Geographic & Demographic Context (Cities, Orgs, Full Addresses) | **Pseudonymization**: Consistent realistic fakes per session via HMAC-seeded `Faker`. | `Dr. Priya Sharma at AIIMS Delhi` $\rightarrow$ `Dr. Ananya Iyer at Apollo Hospital` *(consistent throughout)* |
| **L4** | **Synthetic** | Complete Entity Replacement | **Full Synthesis**: Complete entity substitution with perturbed numeric values. | Fully synthetic, realistic profile with broken cross-record statistical linkage. |

---

## Format Adapters

Redaction occurs directly inside the original format layer to preserve layout, styling, and structural metadata:

* **Plaintext & Logs (`.txt`, `.log`, `.json`)**: Operates on character offsets; preserves original encoding, BOM, whitespace, and line endings.
* **Tabular Data (`.csv`, `.tsv`, `.xlsx`)**: Modifies data cell values while retaining formulas, column headers, cell dimensions, and sheet structures. Supports cross-row pseudonym consistency.
* **Images (`.png`, `.jpg`, `.jpeg`, `.heic`)**: OCR maps word-level bounding boxes. Redacted regions are filled and permanently flattened (destroying underlying pixels). All EXIF and GPS tags are stripped.
* **PDFs (`.pdf`)**: Uses **PyMuPDF true redaction**. Text and pixel coordinates are eradicated from the binary stream (not just overlaid with black rectangles). Strips PDF metadata, annotations, bookmarks, and revision history.

---

## Verification & Anti-Leak Assurance

A document that appears sanitized on-screen can still leak sensitive strings through OCR discrepancies, hidden layers, or encoding quirks. RE-DACT includes an automated verification step:

1. **Re-Extraction**: The generated output is re-extracted using the recipient's view (native PDF parser for digital PDFs; OCR for flattened images).
2. **Residual Matching**: The extracted stream is matched against the list of original sensitive strings using exact and fuzzy matching.
3. **Adaptive Retry**: If a residual leak is detected, the pipeline automatically falls back to a stricter labeled mask (`[REDACTED]`).
4. **Cryptographic Attestation**: The engine generates a SHA-256 fingerprint of input and output documents, along with an HMAC-SHA256 signature calculated with `REDACT_HMAC_KEY`.

```json
{
  "timestamp": "2026-11-17T11:25:00Z",
  "input_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "output_hash": "a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e",
  "level": 3,
  "spans_detected": 14,
  "spans_redacted": 14,
  "residual_risk": 0,
  "verified_clean": true,
  "hmac_signature": "7d5a9...4b8c"
}
```

> [!NOTE]
> Audit logs store **metadata only** (entity categories, counts, and hashes). Original PII values are never written to logs or error messages.

---

## Quickstart

### Prerequisites
* **OS**: Linux (Arch/CachyOS, Ubuntu, Debian), macOS, or Windows
* **Python**: **3.12** *(Python 3.14 breaks ML wheels)*
* **Environment Manager**: [uv](https://github.com/astral-sh/uv) (recommended) or standard virtualenv

### 1. Installation

```fish
# Clone the repository
git clone https://github.com/OrbisEarendel/RE-DACT.git redact && cd redact

# Create virtual environment with Python 3.12
uv venv --python 3.12
source .venv/bin/activate.fish   # Bash/Zsh: source .venv/bin/activate | Windows: .venv\Scripts\activate

# Install PyTorch CPU build
uv pip install torch --index-url https://download.pytorch.org/whl/cpu

# Install dependencies
uv pip install -r requirements.txt

# Configure environment
cp .env.example .env

# Download models locally (one-time setup, requires internet)
python scripts/download_models.py
```

### 2. Configuration (`.env`)

Generate a deployment signing key:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Edit your `.env` file:
```env
# Cryptographic signing key for verification reports
REDACT_HMAC_KEY=your_generated_64_character_hex_key_here

# Runtime limits
REDACT_MAX_FILE_MB=25
REDACT_ALLOWED_EXT=txt,log,csv,json,xlsx,png,jpg,jpeg,heic,pdf

# Hardened offline mode (1 = refuse any outbound network call)
REDACT_OFFLINE=1
REDACT_LOG_LEVEL=INFO
```

### 3. Launch the Application

#### Streamlit Web GUI
```bash
streamlit run app.py
```
Open `http://localhost:8501` to access the interactive dashboard with drag-and-drop upload, real-time level slider, entity checkboxes, and before/after inspection.

#### CLI Command Line
```bash
# Redact a sample file at Level 1 (Light Masking)
python -m app.cli samples/test.txt --level 1

# Redact an image with PaddleOCR at Level 3 (Pseudonymization)
python -m app.cli samples/id_card.png --level 3
```

### 4. Run Test Suite
```bash
pytest -q
```

---

## Security & Privacy

RE-DACT is engineered from the ground up to handle sensitive datasets without creating secondary leakage vectors:

* **In-Memory Lifespan**: Files and intermediate representations live strictly in volatile memory. No temporary files holding original data are saved to disk.
* **Ephemeral Pseudonym Keys**: The HMAC seed used to generate deterministic fake identities is held in RAM only and zeroed immediately upon session termination. Cross-document entity linking is impossible.
* **Isolated Containerization**: Production deployment utilizes a minimal container with a read-only root filesystem, dropped capabilities, no root user, and `--network none` network isolation.
* **Safe Parser Sandbox**: File parsing executes in unprivileged worker processes with strict resource quotas to mitigate decompression bombs and malformed file exploits.
* **No Telemetry / No Call-Homes**: Guaranteed offline operation. Setting `REDACT_OFFLINE=1` forces immediate termination on any outbound socket request.

---

## Evaluation & Benchmark

RE-DACT is evaluated against **Microsoft Presidio** using entity-level **Precision, Recall, and F1** metrics across open benchmark datasets:

* **Indian Identification Benchmarks**: High-precision evaluation on national IDs (Aadhaar with Verhoeff validation, PAN, IFSC codes, Indian mobile number formats).
* **Open Healthcare & De-id Sets**: Evaluated on public benchmark de-identification collections (MIMIC-III de-id subsets, synthetic patient records).
* **Ablation Studies**: Quantifying the contribution of deterministic rules vs. zero-shot GLiNER vs. context heuristics.
* **Utility vs. Privacy Curve**: Measuring downstream utility retention across levels L1 through L4.

Run the evaluation harness:
```bash
python eval/run_eval.py --dataset eval/datasets/dummy_test_set.json
```

---

## The Mark

<picture>
  <img src="RE-DACT_logo.png" width="96" align="left" alt="The RE-DACT Mark" style="margin-right: 20px;">
</picture>

The **RE-DACT** logo represents the balance between privacy protection and structural integrity: a cryptographic lock intertwined with clean document lines and a precision shielding aperture. The deep blue and cyan accents signify trust, offline containerization, and verifiable data security.

<br clear="left">

---

## Team

Developed with pride for **CONVERGE '26** by **StrangerStrings**:
* **Track**: Blockchain & Cybersecurity (Software)
* **Goal**: Deliver a verifiable, containerized proof of concept that proves de-identification can be fast, offline, and gradational.

---

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details. Built using [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR), [GLiNER](https://github.com/urchade/GLiNER), [PyMuPDF](https://github.com/pymupdf/PyMuPDF), and [Streamlit](https://streamlit.io/).
