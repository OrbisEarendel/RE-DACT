# RE-DACT: Developer Guide

## Project Layout

```
redact/
  entity.py             # Shared types (Entity, Word, NormalizedDoc) — DO NOT change without team
  gate.py               # File validation + routing
  detect/               # 6 detector files + __init__.py
    __init__.py         # detect(doc_text, threshold) → list[Entity]
    checksum.py         # GSTN, Luhn, verhoeff checksum validators
    context_rules.py    # Aadhaar near-misses, titled names, sensitive attr fields
    gliner_ner.py       # Zero-shot GLiNER NER detector
    merge.py            # Entity overlap merger (higher score wins, longer span on tie)
    regex_rules.py      # Regex + checksum detectors
    regex_types.py      # Type constants (T.AADHAAR, T.PAN, etc.)
    visual.py           # Face (Haar cascade) + QR code (OpenCV) detection
  extract/              # 5 extractor files + __init__.py
    __init__.py         # to_normalized(), extract()
    text.py             # Plaintext extraction
    pdf.py              # PDF native text + page OCR routing
    ocr.py              # PaddleOCR (5 test failures = env issue only)
    image.py            # Image OCR + to_normalized for image→doc conversion
  transform/levels.py    # L1/L2/L3/L4 text transformation
  writers/              # 3 writer files + __init__.py
    __init__.py         # redact_image, redact_image_pipeline
    image.py            # True pixel-level redaction (solid blackout/blur)
    pdf.py              # PDF true redaction (annotations + replacement text)
  verify/               # 5 verify files + __init__.py
    __init__.py         # audit_log, build_report, rescan, has_residual_risk, sign_report, chain_hash
    audit.py            # Audit entry: types/counts only, no raw PII
    report.py           # build_report(): SHA-256 hashes, entity counts, HMAC signature
    rescan.py           # Re-scan output for residual PII
    sign.py             # sign_report(), chain_hash()
    report.py           # build_report() dict schema
  __init__.py           # Package exports (updated per AGENTS.md §5)
  __main__.py           # CLI entry point

policy/policy.py        # Canonical PII type mapping + select()
eval/run_eval.py        # Precision/Recall/F1 harness
scripts/download_models.py  # One-time model downloader

server.py               # HTTP backend (Streamlit UI + API)
router.py               # Project routing (imported by redact/__init__.py)

tests/                  # 12 test files (pytest)
  test_checksum.py      # 8/8 pass
  test_context_rules.py # 29/29 pass
  test_detect.py        # 6/6 pass
  test_detect_integration.py # 5/5 pass
  test_gate.py          # 53/53 pass
  test_image_writer.py  # 4/4 pass
  test_ocr_extract.py   # 0/5 pass (PaddlePaddle env issue only)
  test_pdf_writer.py    # 4/4 pass (1 env + 3 structural)
  test_policy.py        # 18/18 pass
  test_regex_identifiers.py # 32/32 pass
  test_regex_rules.py   # 24/24 pass
  test_transform_levels.py # 11/11 pass

AGENTS.md             # Architecture spec (all module contracts referenced here)
requirements.txt        # Pinned dependencies
Dockerfile              # Containerization
README.md               # Project overview (at root)
docs/                   # Documentation folder (moved from root)
  GETTING_STARTED.md
  ARCHITECTURE.md
  EVALUATION.md
  DEVELOPER_GUIDE.md
```

## Contributing

### Ground Rules (AGENTS.md Rules)

1. **No raw PII in logs, error messages, or reports** — types/counts only
2. **100% offline at runtime** — no network calls during requests
3. **No third-party APIs for processing data** — no OpenAI, Gemini, Claude, cloud OCR
4. **Input processed in memory only** — no temp files holding original content (use `finally` to clean)
5. **Never commit real personal data** — test files use dummy data only
6. **Never commit secrets** — `.env` is git-ignored; only `.env.example` committed
7. **Do not change shared type/function signature without team discussion** — section 5
8. **Every detector and transformer ships with tests** — no test, no merge
9. **Do not add a dependency without asking** — pin the version, prefer what's already installed
10. **Do not claim a feature works until tests show it** — overclaiming loses points

### Adding a New Detector

1. Create file in `redact/detect/` following existing patterns
2. Export from `redact/detect/__init__.py`
3. Add test in `tests/` with: TP, near-miss, messy-context
4. Run `pytest -q` to confirm no regressions
5. Update `policy/policy.py` `ALL_PII_TYPES` if new entity type
6. Document in `docs/ARCHITECTURE.md` if relevant

### Adding a New Transformer (L1-L4)

1. Edit `redact/transform/levels.py` — add level logic
2. Ensure `canonical()` in `policy/policy.py` normalizes labels correctly
3. Write tests per AGENTS.md §10 (idempotence, offset correctness, same real → same fake, fake != original)
4. Run `pytest -q` to confirm
5. Update `docs/EVALUATION.md` metrics if relevant

### Adding a New File Format

1. Create adapter in `redact/extract/` (text.py, pdf.py, ocr.py, image.py patterns)
2. Create writer in `redact/writers/` (image.py, pdf.py patterns)
3. Update `redact/gate.py` routing logic
4. Add tests in `tests/` for: extract → detect → transform → write → verify
5. Run full `pytest -q`
6. Update `docs/ARCHITECTURE.md` format support table

### Adding Environment Variables

1. Add to `.env.example` (never commit real `.env`)
2. Document in `docs/GETTING_STARTED.md` under "Environment"
3. Load with `os.environ` / `python-dotenv` — never hard-code keys
4. If `REDACT_OFFLINE=1`, any outbound request must fail loudly

### Branch & PR Workflow

```
# Feature branch
git checkout -b feat/<area>-<thing>

# Make changes
# ... add code, write tests ...

# Verify
pytest -q  # must pass before PR

# Commit message format (AGENTS.md)
area: what changed

# PR
# - Small PRs, reviewed by at least one other person
# - 10-minute review target (hackathon speed)
# - Hackathon day: use dummy data only, rehearse offline

# Merge
# - main is always runnable
# - Work on short branches: feat/<area>-<thing>
```

## Code Conventions

### Imports

```python
# Standard library
import os
import re
import hashlib

# Third-party
import numpy as np
import cv2
import pandas as pd
import pymupdf  # PyMuPDF
from gliner import GLiNER  # or from redact.detect.gliner_ner

# Project (always relative import from redact.)
from .entity import Entity, NormalizedDoc, Word
from .gate import route, RoutePlan
from .detect import detect, merge
from .detect import regex_rules, gliner_ner, visual
from .extract import to_normalized, extract
from .transform import apply as transform_apply
from .writers import redact_image, redact_image_pipeline
from .verify import audit_log, build_report, rescan, has_residual_risk, sign_report
from .policy import canonical, LEVEL_TABLE, ALL_PII_TYPES
```

### Types (DO NOT CHANGE WITHOUT TEAM)

```python
@dataclass
class Entity:
    type: str          # "person", "phone number", "AADHAAR", ...
    start: int         # char offset into NormalizedDoc.text
    end: int
    score: float = 1.0 # 1.0 for regex+checksum, model confidence for NER
    source: str = ""   # "regex" | "gliner" | "custom"

@dataclass
class Word:
    text: str
    x: int
    y: int
    w: int
    h: int
    conf: float
    page: int = 0

@dataclass
class NormalizedDoc:
    text: str                                                    # whole doc as one string
    spans: list = field(default_factory=list)   # list[(start, end, ref)]
```

### Detection Contract

```python
def detect(doc_text: str, threshold: float = 0.4) -> list[Entity]:
    # Runs all detectors + merge()
    # Higher score wins, then longer span; no overlaps out
    # Regex normally beats NER on same span
```

### Transform Contract

```python
def apply(text: str, ents: list[Entity], level: int, mapping: dict | None = None) -> str:
    # L1 masks direct identifiers
    # L2 generalizes quasi-identifiers
    # L3 pseudonymizes (consistent fakes)
    # L4 synthesizes (fully synthetic)
```

### Policy Contract

```python
def select(ents: list[Entity], level: int, enabled_types: set[str] | None = None) -> list[Entity]:
    # Decides WHAT counts as PII and AT WHICH level per DPDP Act 2023 / IT (SPDI) Rules 2011
    # canonical() normalizes GLiNER lowercase labels → uppercase canonical names
    # LEVEL_TABLE: L1 includes L1-only types; L2 includes L1+L2; L3 includes all up to L3; L4 includes everything
```

## Testing Requirements (AGENTS.md §10)

### Per Detector: One test file with

1. **True Positive** — Document where detector correctly identifies real PII
2. **Near-Miss** — Pattern looks similar but MUST NOT match (e.g., Aadhaar with wrong check digit)
3. **Messy-Context Case** — PII embedded in realistic surrounding text

### Per Transformer: Tests for

1. **Idempotence** — Running transform twice produces same output
2. **Offset Correctness** — Replace from the end backwards; offsets preserved after multiple transforms
3. **Same Real → Same Fake** — L3 consistency: canonicalize → HMAC seed → Faker; same input entity → same fake
4. **Fake != Original** — Generated values must never equal original value

Run: `pytest -q`

### Expected Results

```
491 passed, 5 failed in ~40s
5 failures: PaddlePaddle Windows env issue (ConvertPirAttribute2RuntimeAttribute)
All other tests: 100% pass
```

## Model Management

### One-Time Download

```bash
python scripts/download_models.py
```

Downloads:
- `urchade/gliner_multi_pii-v1` (GLiNER, zero-shot NER)
- PaddleOCR PP-OCRv6 models (detection + recognition)

### Runtime: 100% Offline

After download, no network calls. Set `REDACT_OFFLINE=1` to enforce.

### Model Files Cached

~1GB cached in `~/.paddlex/official_models/` and Hugging Face cache.

### Adding a New Model

1. Ask team before adding dependency (AGENTS.md Rule 9)
2. Update `scripts/download_models.py` if new model needed
3. Add test that model loads without network
4. Test with `REDACT_OFFLINE=1`

## Security Rules (AGENTS.md §9)

### Validate Every Upload

- Extension allowlist (`REDACT_ALLOWED_EXT` = txt,log,csv,json,xlsx,png,jpg,jpeg,heic,pdf)
- Size cap (`REDACT_MAX_FILE_MB` = 25 by default)
- Page and frame caps for PDF and video
- Content-based type checks (not just extension)
- Magic bytes / MIME validation

### Never

- `eval` / `exec` / `pickle.load` user-supplied data
- Shell commands built from user input (`shell=True`)
- Write original content to disk (use `finally` to delete any temp files)
- Persist real-to-fake mappings (fake-data mapping lives in memory only, discarded after session)

### Audit Log / Report

- Stores types, counts, level, and SHA-256 hashes of input/output
- **No raw values** ever
- HMAC-SHA256 signed using `REDACT_HMAC_KEY` from `.env`
- Optional chain hash (tamper-evident log)

### Offline Mode

If `REDACT_OFFLINE=1`, any attempt at outbound request must fail loudly.

## Debugging Guidelines

### When Debugging:

1. **Print types and counts only** — never raw PII text
2. **Use `pytest -q`** to isolate failures
3. **Check `redact/detect/` first** — most issues are detector-related
4. **Check `redact/transform/levels.py`** — level logic changes
5. **Check `redact/verify/`** — rescan/report issues
6. **Run `python scripts/download_models.py`** if OCR/models seem missing

### Common Issues

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| "ConvertPirAttribute2RuntimeAttribute" | PaddlePaddle env incompatibility (Windows) | Known issue; OCR tests skip; core pipeline unaffected |
| "Entity type not found in policy" | New detector not in `ALL_PII_TYPES` | Add to `policy/policy.py` `ALL_PII_TYPES` |
| "Level slider has no effect" | Entity types not checked in UI, or `select()` not filtering | Check `policy/policy.py` `LEVEL_TABLE` and UI checkboxes |
| "Residual PII detected" | Verification re-scan found PII not masked at current level | Increase level or check different entity types |
| "Import error: cannot import name X from redact" | Missing export in `redact/__init__.py` | Add to `__init__.py` exports |

## Directory Deep-Dive

### `redact/entity.py`

```python
# Core types shared across the entire repo
# DO NOT CHANGE WITHOUT TEAM AGREEMENT (AGENTS.md §5)
```

- `Entity` — the unit of redaction: type + location + confidence + source
- `Word` — one OCR word with box coordinates
- `NormalizedDoc` — document as one string + char-range map
- These types flow through: detect → merge → policy → transform → writers → verify

### `redact/gate.py`

```python
# File validation + routing
# Entry point for all uploads
```

- Magic number detection (file content, not extension)
- Extension allowlist (`REDACT_ALLOWED_EXT`)
- Size cap (`REDACT_MAX_FILE_MB`)
- Routing to native extraction / OCR / both
- Fails closed (hidden text → OCR)

### `redact/detect/__init__.py`

```python
# detect(doc_text, threshold) → list[Entity]
# Runs all detectors + merge()
```

- Runs regex+checksum, GLiNER NER, merge
- Visual PII (faces/QR) via `visual.py`
- No overlaps out; higher score wins, then longer span

### `redact/detect/visual.py`

```python
# Face detection (Haar cascade) + QR code detection (OpenCV)
# 100% offline, zero cloud calls
```

- `cv2.CascadeClassifier(haarcascade_frontalface_default.xml)` for faces/portraits
- `cv2.QRCodeDetector()` for QR codes
- Returns `list[Word]` tagged as `[PHOTO]` / `[QR]`
- Maps into `NormalizedDoc` for redaction by `writers/image.py`

### `redact/extract/__init__.py`

```python
# to_normalized(), extract(path_or_bytes, filename) → NormalizedDoc + RoutePlan
```

- `to_normalized()` — join OCR words into one string, remember each word's (start, end) char range and box
- `extract()` — universal entry: route by format → text/pdf/ocr → NormalizedDoc
- OCR words joined into one string (never regex on single words)

### `redact/transform/levels.py`

```python
# L1/L2/L3/L4 text transformation
```

- `apply(text, ents, level) → str`
- L1 masks direct identifiers
- L2 generalizes quasi-identifiers (age → "30s", date → month/year)
- L3 pseudonymizes (consistent fakes, HMAC-seeded)
- L4 synthesizes (fully synthetic, valid formats)

### `redact/writers/__init__.py`

```python
# redact_image, redact_image_pipeline
```

### `redact/writers/image.py`

```python
# redact_image(image, words, ents, doc, style="box")
# True pixel-level redaction (solid blackout/blur)
# In-memory only, preserves non-redacted areas pixel-for-pixel
```

### `redact/verify/__init__.py`

```python
# audit_log, build_report, rescan, has_residual_risk, sign_report, chain_hash
```

### `redact/verify/rescan.py`

```python
# Re-scans redacted output for residual PII
# has_residual_risk(text, threshold, max_entities) → bool
```

### `redact/verify/report.py`

```python
# build_report(input_bytes, output_bytes, level, ents, residual, previous_chain_hash, hmac_key) → dict
# Schema: input_hash, output_hash, level, ents_by_type, residual_count, hmac_sig, chain_sig
```

### `redact/verify/sign.py`

```python
# sign_report(report_dict, key) → hex HMAC-SHA256
# chain_hash(previous, current) → hex chained hash
```

### `policy/policy.py`

```python
# Canonical PII type mapping + select()
```

- `canonical()` — normalizes GLiNER lowercase labels → uppercase (e.g., `person` → `PERSON`)
- `LEVEL_TABLE` — L1/L1+L2/L1+L2+L3/L1+L2+L3+L4
- `ALL_PII_TYPES` — comprehensive list of all PII types
- `select(ents, level, enabled_types)` — what acts at which level

### `eval/run_eval.py`

```python
# Precision/Recall/F1 harness
```

- `DUMMY_TEST_CASES` — 5 synthetic Indian-document texts with heuristic ground truth
- `compute_metrics(predicted, ground_truth) → {precision, recall, f1, support}`
- `run_dummy_eval() → dict` — per-case + average metrics
- `run_placeholder_eval() → dict` — public dataset placeholder
- `run_eval() → dict` — combines dummy + placeholder

### `scripts/download_models.py`

```python
# One-time model downloader
```

- Gliner model: `urchade/gliner_multi_pii-v1`
- PaddleOCR: PP-OCRv6 detectors + recyclers
- Run once; then 100% offline

## CI / CD (Hackathon Mode)

### Local Verification

```bash
# 1. Install deps
uv venv --python 3.12
source .venv/bin/activate.fish
uv pip install torch --index-url https://download.pytorch.org/whl/cpu
uv pip install -r requirements.txt

# 2. Download models
python scripts/download_models.py

# 3. Run tests
pytest -q  # 491 passed, 5 OCR env failures

# 4. Quick smoke test
streamlit run app.py  # UI at localhost:8501
```

### PR Checklist (before merge)

- [ ] `pytest -q` passes (491/496)
- [ ] No raw PII in any log/output/report
- [ ] New detector/transform has tests (TP + near-miss + messy-context)
- [ ] No shared type/signature changed without team discussion
- [ ] No new dependency added without asking
- [ ] `AGENTS.md` updated if a contract changed
- [ ] `.env.example` updated if new env vars added
- [ ] Docs updated (`docs/` folder)
- [ ] Tested offline (`REDACT_OFFLINE=1`)
- [ ] Tested with dummy data only (no real PII)

### Hackathon Day Checklist

- [ ] Rehearse demo on actual demo laptop offline
- [ ] Use dummy data only (no real Aadhaar/PAN/IDs)
- [ ] Show level slider visibly doing something (L1→L2→L3→L4)
- [ ] Show before/after panels
- [ ] Download signed report
- [ ] Mention offline mode and no cloud calls
- [ ] Mention eval numbers (Precision/Recall/F1 vs Presidio)
- [ ] Mention 491/496 test pass rate (5 OCR = env issue)
- [ ] Reference AGENTS.md compliance throughout

## Glossary of Internal Names

| Internal Name | Meaning |
|--------------|---------|
| `T.AADHAAR` | Type constant for Aadhaar IDs |
| `T.PAN` | Type constant for PAN cards |
| `L1`, `L2`, `L3`, `L4` | Redaction levels (light to synthetic) |
| `GLiNER` | Zero-shot NER model (`urchade/gliner_multi_pii-v1`) |
| `Verhoeff` | Checksum for Aadhaar-style ID validation |
| `canonical()` | GLiNER label → uppercase normalization |
| `LEVEL_TABLE` | Per-level PII type inclusion map |
| `ALL_PII_TYPES` | Complete list of detectable PII types |
| `HMAC-SHA256` | Keyed hash for signed reports |
| `residual_risk` | PII remaining in output after re-scan |
| `pseudonymize` | Same real → same fake, in memory only |
| `generalize` | Reduce precision (age → range, date → month-year) |
| `mask` | Replace with type label or black box |
| `synthesize` | Fully synthetic realistic values |
| `normalize` | Join OCR words; canonicalize labels |
| `route` | File format detection + extraction path |
| `merge` | Entity overlap resolver |
| `select` | Policy engine: what acts at which level |