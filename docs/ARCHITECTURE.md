# RE-DACT: User Guide

## Quick Start

### First Time

```bash
# Clone project
git clone <repo-url> redact && cd redact

# Setup environment (fish shell)
uv venv --python 3.12
source .venv/bin/activate.fish

# Install dependencies
uv pip install torch --index-url https://download.pytorch.org/whl/cpu
uv pip install -r requirements.txt

# Download models (one-time, needs internet)
python scripts/download_models.py

# Verify everything works
pytest -q
# Expected: 491 passed, 5 failed (OCR env issue only)
```

### Run the Application

```bash
streamlit run app.py
```

UI opens at `http://localhost:8501`.

## Interface Overview

### Upload Area

- Drag & drop or browse to upload a file
- Supported formats: `txt, log, csv, json, xlsx, png, jpg, jpeg, heic, pdf`
- Size limit: `REDACT_MAX_FILE_MB` (default 25MB)
- Content-based validation (not just extension)

### Redaction Level Slider

- **L1 — Light**: Masks direct identifiers (names, Aadhaar, PAN, phone, email, bank account)
- **L2 — Medium**: L1 + quasi-identifiers (dates, ages, job titles, cities)
- **L3 — Strong**: L2 + addresses, organizations, geocoordinates (pseudonymizes with consistent fakes)
- **L4 — Synthetic**: Everything replaced with synthetic values, valid formats

### Entity Checkboxes

Toggle which entity types to act on:
- `PERSON`, `PHONE`, `EMAIL`, `AADHAAR`, `PAN`, `DATE`, `ADDRESS`, `ORGANIZATION`, etc.
- Users can override per-type (e.g., mask names but keep cities)

### Before / After Panels

- **Left**: Original file content
- **Right**: Redacted output
- Changes update in real-time as you adjust level and checkboxes

### Download

- Download the redacted file in the same format as upload
- Download a signed audit report (HMAC-SHA256)
- Report includes: entity types, counts by level, input/output SHA-256 hashes, residual risk status

## File Format Support

| Input | Extraction | Detection | Redaction |
|-------|-----------|-----------|-----------|
| **Plaintext (.txt, .log)** | Native text | Regex + GLiNER | Mask/generalize/synthesize |
| **CSV (.csv)** | Column values | Per-cell regex/GLiNER | Edit values, keep headers |
| **JSON (.json)** | Keys + values | Per-value detection | Edit values, keep structure |
| **Image (.png, .jpg, .jpeg)** | PaddleOCR | Regex + GLiNER on OCR words | Pixel-level blackout/blur |
| **PDF (.pdf)** | Native text + OCR for images | Regex + GLiNER + visual PII | True redaction annotations |
| **Heic (.heic)** | OCR after decode | Same as image | Same as image |

### PDF Details

- **PDF with text layer**: Words and coordinates come straight from the PDF
- **PDF with embedded images**: Native text extracted, OCR on each image
- **Scanned PDF**: Each page rasterized, then OCR applied
- **Redaction**: Real removal of pixels/annotations, not drawing over
- **Metadata stripped**: author, title, XMP, comments, embedded files, form values, bookmarks, history

### Image Details

- OCR words joined into one string (never regex on single words)
- Bounding boxes drawn around detected entities
- Pixel-level redaction (solid blackout or blur)
- EXIF data stripped from output
- Non-redacted areas preserved pixel-for-pixel

## Level Guide

### L1 — Light

**Acts on**: Direct identifiers
- Names (`PERSON`)
- Aadhaar (12 digits + Verhoeff checksum)
- PAN (`[A-Z]{5}\d{4}[A-Z]`)
- Phone (`[6-9]\d{4}\s?\d{5}`)
- Email
- Bank account numbers
- IFSC codes
- Passport, Voter ID, Driving licence, Vehicle reg, GSTIN, ABHA ID, USN

**Transform**: Mask
- `[NAME]`, `XXXX XXXX 1234`, redaction boxes

### L2 — Medium

**Acts on**: L1 + quasi-identifiers
- Dates → month/year
- Age → "30s", "40-49"
- Job titles
- Cities/geography
- Genders, blood groups, religion, caste, disability, health info

**Transform**: Generalize
- Age 34 → "30-39"
- Date Jan 15, 1990 → "January 1990"
- City "Mumbai" → "Maharashtra region"

### L3 — Strong

**Acts on**: L2 + organizational/geo
- Full addresses
- Geocoordinates
- Organizations/companies

**Transform**: Pseudonymize
- Consistent fakes: same real value → same fake (in memory only)
- HMAC-seeded Faker values
- Cross-field links broken (each entity gets independent fake)

### L4 — Synthetic

**Acts on**: Everything in policy
- Full entity substitution
- Perturbed numeric values (valid formats)
- Synthetic realistic values for tables
- Cross-field links explicitly broken

**Transform**: Substitute
- Every entity replaced with synthetic value
- Numeric values perturbed but valid (e.g., Aadhaar 12 digits, still Verhoeff-valid)
- Tables: column-wise or SDV-style synthetic generation (roadmap)

## Verification & Audit

Every output is automatically checked:

1. **Re-extract**: The redacted file is re-read (text extraction for text/PDFs, OCR for images)
2. **Leak check**: Original span strings searched for in extracted text (exact + fuzzy matching)
3. **Residual risk**: If PII found, output flagged and NOT returned as "clean"
4. **Audit log**: Types, counts, level, input/output hashes — **no raw values**
5. **HMAC signature**: Report signed with per-session key

If verification fails, the file is regenerated with stricter settings or plain masks.

## Reports

Downloaded report includes:
- Input SHA-256 hash
- Output SHA-256 hash
- Redaction level (L1-L4)
- Entity type counts (how many of each were found/redacted)
- Residual risk status (clean/risky)
- HMAC-SHA256 signature (tamper-evident)
- Optional chain hash (links to previous report)

**No raw PII** appears in the report — only types, counts, and hashes.

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Esc` | Close current operation |
| `Ctrl+L` | Focus level slider |
| `Ctrl+E` | Focus entity checkboxes |
| `F5` | Refresh/re-run detection |

## Offline Mode

Set `REDACT_OFFLINE=1` in `.env` or environment. The app will:
- Refuse any outbound network calls
- Work completely offline after model download
- Health check confirms offline mode

## Error Handling

- **Unsupported format**: File rejected at upload with explanation
- **File too large**: Rejected with current limit
- **OCR failure**: Falls back to available results; user notified
- **Verification failure**: Output not returned as "clean"; user can adjust level
- **All errors**: Logged with types/counts only, never raw PII

## Security Best Practices (for users)

- Never upload real PII if you don't want processed locally
- Output files should be treated as sensitive until verified
- Download reports only to trusted locations
- `.env` contains `REDACT_HMAC_KEY` — keep it secret (never committed to git)
- Model files downloaded once; never sent to cloud at runtime

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "OCR not available" | Run `python scripts/download_models.py` to ensure models cached |
| "File rejected" | Check extension, size (<25MB), and content type |
| "Level slider has no effect" | Ensure entity types are checked in the UI |
| "Residual PII detected" | Increase level (L1→L2→L3) or check different entity types |
| "Report won't download" | Check that verification passed (residual risk = 0) |
| "Slow performance on PDFs" | Native text PDFs are fast; scanned PDFs require OCR per page |

## FAQ

**Q: Does RE-DACT claim GDPR/HIPAA compliance?**
A: No. It reduces re-identification risk but does not claim legal compliance. See AGENTS.md Legal section.

**Q: Can I use this on real patient records / financial documents?**
A: The tool runs offline and processes in memory, but you should verify it meets your organization's data handling policies before use.

**Q: What happens to my uploaded files?**
A: Input is processed in memory only. No document content is written to disk (except the user's explicit output download). Temporary files, if any, are deleted in `finally` blocks.

**Q: Can I chain reports for tamper-evidence?**
A: Yes. The `chain_hash` function in `verify/sign.py` links each report's HMAC hash to the previous one. Enable via the UI or API.

**Q: Is the OCR engine swapable?**
A: The OCR pipeline is behind one function (`extract/ocr.py`). Swapping engines doesn't touch detection or redaction logic. Currently PaddleOCR is the primary engine.

**Q: What if OCR misses a string?**
A: If OCR misses it, no text-based detector can catch it. Visual PII (faces/QR codes) via `detect/visual.py` works independently of OCR.

**Q: Can I run this without the UI?**
A: Yes. The core engine (`redact/`) is a pure Python package. Use `from redact import detect, extract, transform, writers, verify` in your own scripts.

**Q: What Python version do I need?**
A: Python **3.12** recommended. 3.14 breaks ML wheels. Use the uv-managed venv.

**Q: Can I contribute detectors or transforms?**
A: Yes — but per AGENTS.md: "Do not change a shared type or function signature without telling the whole team" and "Every detector and transformer ships with tests."

# Glossary

| Term | Definition |
|------|-----------|
| `Entity` | A detected PII span with type, location, and confidence |
| `NormalizedDoc` | Document as one string + char-range map to source |
| `Level L1-L4` | Graduated redaction intensity (light to synthetic) |
| `GLiNER` | Zero-shot NER model (`urchade/gliner_multi_pii-v1`) |
| `Verhoeff` | Checksum algorithm for Aadhaar-style ID validation |
| `HMAC-SHA256` | Keyed hash for signed reports |
| `Residual risk` | PII remaining in output after re-scan |
| `Pseudonymize` | Same real → same fake, in memory only |
| `Generalize` | Reduce precision (age 34 → "30s") |
| `Mask` | Replace with type label or black box |