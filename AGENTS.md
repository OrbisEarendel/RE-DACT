# RE-DACT: Team + Agent Rules

> **Read this file fully before writing or changing any code.**
> Humans and AI agents (Claude Code, Cursor, Copilot, etc.) must follow it.
> If something here is wrong or missing, fix this file in the same PR. Do not silently work around it.
> Tip: Claude Code reads `CLAUDE.md`, so copy this file to `CLAUDE.md` (or symlink it).

---

## 1. What we are building

**RE-DACT**: an offline tool that redacts / masks / anonymizes sensitive data from text, datasets, images and PDFs, with a **user-controlled redaction level (L1 to L4)**, and proves the output is clean.

Hackathon track: Blockchain & Cybersecurity (Software).

**Judged on:** Precision / Recall / F1 on an open test set, gradational effect (the level slider must visibly do something), variety of input formats, minimal data retention, speed, ease of use (UI), benchmark vs a COTS tool (Presidio), offline + web mode, minimal API dependency, secure coding.

**A working PoC beats slides.** Anything that does not run end to end does not count.

### Stages
- **Stage 1 (PoC):** text, CSV/JSON/XLSX, images -> redacted files + logs. Web UI.
- **Stage 2 (finale):** PDFs, video, annotated redaction output. Dataset is given at the finale.

---

## 2. Hard rules (never break these)

1. **No raw PII in logs, error messages, reports, filenames or git.** Log entity *types and counts* only. Never log `text[start:end]`.
2. **No network calls at runtime.** The pipeline must work with the internet off. Models are downloaded once at setup, never during a request.
3. **No third-party APIs for processing data.** No OpenAI, Gemini, Claude, cloud OCR, cloud NER. Zero. (See section 8: there are no API keys in this project by design.)
4. **Input is processed in memory only.** No writing uploads to disk except the user's explicit output download. No temp files holding original content; if a library forces one, delete it in a `finally` block.
5. **Never commit real personal data.** Test files use **dummy data only**. No real Aadhaar, PAN, bank numbers, phone numbers, student letters, or ID photos in the repo, in screenshots or in demos.
6. **Never commit secrets.** `.env` is git-ignored. Only `.env.example` is committed.
7. **Do not change a shared type or function signature (section 5) without telling the whole team.** Everyone's code depends on them.
8. **Every detector and transformer ships with tests.** No test, no merge.
9. **Do not add a dependency without asking.** Pin the version. Prefer what is already installed.
10. **Do not claim a feature works until the eval or a test shows it.** Overclaiming loses points when judges try it.

---

## 3. Environment

| Thing | Value |
|---|---|
| OS (dev) | CachyOS (Arch), **fish shell** |
| Python | **3.12** (3.14 breaks ML wheels. Do not use it) |
| Env manager | **uv** |
| Activate venv | `source .venv/bin/activate.fish` (fish, not bash!) |
| Install packages | `uv pip install <pkg>` (plain `pip` hits the system Python and errors) |
| Torch | CPU build: `uv pip install torch --index-url https://download.pytorch.org/whl/cpu` |

### First-time setup
```fish
git clone <repo-url> redact && cd redact
uv venv --python 3.12
source .venv/bin/activate.fish
uv pip install torch --index-url https://download.pytorch.org/whl/cpu
uv pip install -r requirements.txt
cp .env.example .env
python scripts/download_models.py    # one-time, needs internet
pytest -q
```
Bash/zsh users: `source .venv/bin/activate`.

> **TBD (owner fills in):** exact PaddleOCR / PaddlePaddle versions that were tested on our laptops. Record them in `requirements.txt` with exact pins and note any install quirks here.

---

## 4. Tech stack (decided)

| Layer | Choice | Notes |
|---|---|---|
| OCR | **PaddleOCR** | Decided and tested by the team. Must return word boxes (see `Word` below) |
| NER | **GLiNER** (`urchade/gliner_multi_pii-v1`) | Zero-shot. It only finds the labels we give it |
| Rules | Python `re` + checksums (Verhoeff for Aadhaar) | Deterministic, score 1.0 |
| Fake data | **Faker** (`en_IN`) + custom generators | Valid-format IDs |
| PDF | **PyMuPDF** | True redaction (content removed, not covered) |
| Images | Pillow (open / draw / save), OpenCV (straighten, preprocess, face & QR detection) | Built-in offline Haar cascade & QRCodeDetector |
| UI | **Streamlit** | Same code serves offline (localhost) and "web" mode |
| Tests | pytest | |
| Baseline | **Presidio** | Used only in `eval/` for the COTS comparison |
| Signing | HMAC-SHA256 (stdlib `hmac`) | Key from `.env` |

OCR is behind one function (section 5), so swapping engines never touches detection or redaction.

---

## 5. Architecture and contracts

```
input file
   -> io/ (gate: validate type + size, route by format)
   -> extract (text reader / table reader / OCR / PDF text / frames)
   -> NormalizedDoc  (text + position map)
   -> detect/ (regex+checksum, GLiNER, custom rules)  -> list[Entity]
   -> merge()  (resolve overlaps)
   -> policy/ (what is PII + level L1-L4)  -> list[Entity] to act on
   -> transform/ (mask / generalize / pseudonymize / synthesize)
   -> writers (text / dataset / image / pdf)
   -> verify/ (re-scan, report, HMAC signature, audit log)
   -> output file + report
```

See `redact_architecture.png` for the diagram.

### Repo layout
```
redact/
  entity.py            # shared types (Entity, Word, NormalizedDoc)
  gate.py              # file validation + routing
  extract/             # text.py, table.py, ocr.py (Paddle), pdf.py, video.py
  detect/              # regex_rules.py, checksum.py, gliner_ner.py, custom.py, merge.py
  policy/              # policy.py (PII table + levels)
  transform/           # levels.py, fakers.py, mapping.py
  writers/             # text.py, dataset.py, image.py, pdf.py
  verify/              # rescan.py, report.py, sign.py, audit.py
  feedback/            # store.py
  eval/                # run_eval.py, presidio_baseline.py, datasets/ (dummy only)
app.py                 # Streamlit UI
scripts/               # download_models.py, etc.
tests/
```

### Shared types (`redact/entity.py`): DO NOT CHANGE WITHOUT TEAM AGREEMENT
```python
from dataclasses import dataclass, field

@dataclass
class Entity:
    type: str            # "person", "phone number", "AADHAAR", ...
    start: int           # char offset into NormalizedDoc.text
    end: int
    score: float = 1.0   # 1.0 for regex+checksum, model confidence for NER
    source: str = ""     # "regex" | "gliner" | "custom"

@dataclass
class Word:              # one OCR word
    text: str
    x: int
    y: int
    w: int
    h: int
    conf: float
    page: int = 0

@dataclass
class NormalizedDoc:
    text: str                                   # whole document as one string
    # char range -> where it lives in the source (cell / page+bbox / line)
    spans: list = field(default_factory=list)   # list[(start, end, ref)]
```

### Module contracts (signatures are the interface)
```python
# extract/ocr.py
def ocr(image) -> list[Word]: ...                 # PaddleOCR inside, nothing else leaks out

# extract/*.py
def to_normalized(path_or_bytes) -> NormalizedDoc: ...

# detect/__init__.py
def detect(doc_text: str, threshold: float = 0.4) -> list[Entity]: ...   # runs all detectors + merge()

# detect/merge.py
def merge(ents: list[Entity]) -> list[Entity]: ...  # higher score wins, then longer span; no overlaps out

# policy/policy.py
def select(ents: list[Entity], level: int, enabled_types: set[str] | None = None) -> list[Entity]: ...

# transform/levels.py
def apply(text: str, ents: list[Entity], level: int, mapping: dict | None = None) -> str: ...

# writers/image.py
def redact_image(image, words: list[Word], ents: list[Entity], doc: NormalizedDoc, style="box"): ...

# verify/report.py
def build_report(input_hash: str, output_hash: str, level: int, ents: list[Entity], residual: int) -> dict: ...
```

### How OCR connects to detection (the position map)
OCR returns words, but numbers get split (`2345 | 6789 | 0123`), so **never run regex on single words**.
1. Join OCR words into one string. Remember each word's `(start, end)` char range and its box.
2. Run `detect()` on the **full string**.
3. For each `Entity`, find the words whose char range overlaps `[start, end)`.
4. Draw boxes on those words only.

The same idea applies to PDFs (word coordinates) and tables (cell references).

### Newly Added Feature: Visual PII Detection (Face/Photo & QR Codes)
Documents (especially ID cards, certificates, and official records) contain non-text visual PII:
- **Personal portraits / face photos**
- **QR codes / Barcodes** encoding personal identifiers (e.g. Aadhaar QR)

Because OCR and GLiNER only process textual characters, visual PII cannot be detected through text extraction. Visual PII is detected directly using OpenCV:
- `cv2.CascadeClassifier(haarcascade_frontalface_default.xml)` for faces/portraits.
- `cv2.QRCodeDetector()` for QR codes.
- 100% offline, zero cloud calls, zero new packages required (uses pre-installed OpenCV).
- Visual PII bounding boxes are mapped into `Word(text="[PHOTO]", ...)` and `Word(text="[QR]", ...)` in `NormalizedDoc`, and redacted by `writers/image.py`.

---

## 6. Redaction levels and policy

The slider selects the level. The policy table decides which entity types are acted on.

| Level | Name | Acts on | Transform |
|---|---|---|---|
| **L1** | Light | Direct identifiers: names, IDs (Aadhaar, PAN), phone, email, bank/account no. | Mask: `[PERSON]`, `XXXX XXXX 1234` |
| **L2** | Medium | L1 + quasi-identifiers: age, dates, job title | Generalize: age 34 -> "30s", date -> month/year |
| **L3** | Strong | L2 + city, organization, address | Pseudonymize: consistent fakes (same real value -> same fake, in memory only) |
| **L4** | Synthetic | Everything in policy | Fully synthetic realistic values, valid formats, cross-field links broken |

- **What counts as PII is a human policy decision** (`policy/policy.py`), not something the model decides. The model only *finds* the labels we ask for.
- Entity types are exposed as checkboxes in the UI.
- Types such as `family relation` ("my cousin") are on an **ignore list**, not PII.
- Fake values must **never equal an original value**. Tests must check this.

---

## 7. Detection rules

- **Regex + checksum** for fixed formats: phone (`[6-9]\d{4}\s?\d{5}`), email, PAN (`[A-Z]{5}\d{4}[A-Z]`), Aadhaar (12 digits + **Verhoeff** check). Score `1.0`.
- **GLiNER** for names, addresses, orgs, dates, ages, job titles, etc. Default threshold `0.4`. It only finds what is in `LABELS`; if a type is missing from the list it will leak.
- **Custom rules** (optional): gazetteer / context words / user-added patterns from the feedback store.
- **Merge:** overlapping spans, higher score wins, then longer span. Regex normally beats NER on the same span.
- **Known weak spots** (do not hide them): fragmented low-confidence addresses, "Sri Residency" tagged as an organization, bank account numbers (no checksum; use context words like "account", "A/c"), IFSC (`[A-Z]{4}0[A-Z0-9]{6}`), Kannada/Indic text.

---

## 8. Config, keys and secrets

**This project has no external API keys, by design.** Everything runs locally. If you think you need one, you are breaking rule 3, so ask first.

The only config lives in `.env` (never committed). Commit `.env.example`:

```env
# --- Signing (REQUIRED for verify/sign.py) ---
# Generate once per deployment:  python -c "import secrets; print(secrets.token_hex(32))"
REDACT_HMAC_KEY=

# --- Limits ---
REDACT_MAX_FILE_MB=25
REDACT_ALLOWED_EXT=txt,log,csv,json,xlsx,png,jpg,jpeg,heic,pdf

# --- Runtime ---
REDACT_OFFLINE=1            # 1 = refuse any outbound network call
REDACT_LOG_LEVEL=INFO

# --- Optional, setup-time only ---
# Hugging Face token. Only used by scripts/download_models.py to avoid rate limits.
# Never used at runtime.
HF_TOKEN=
```

Rules:
- Load with `os.environ` / `python-dotenv`. Never hard-code a key.
- `.gitignore` must include: `.env`, `.venv/`, `__pycache__/`, `*.heic`, `*.pdf`, `uploads/`, `outputs/`, `models/`.
- If anyone commits a secret by accident: tell the team immediately and rotate it.
- Share the real `.env` values over a private channel, never in chat history that is public or in the repo.

---

## 9. Security rules for code

- **Validate every upload:** extension allowlist, real MIME / magic bytes, size cap (`REDACT_MAX_FILE_MB`), page and frame caps for PDF and video.
- **Never `eval` / `exec` / `pickle.load` user-supplied data.** Parse with safe libraries only.
- **No shell commands built from user input.** If calling `ffmpeg`, pass an argument list, never `shell=True`.
- **Sanitize filenames:** never use the uploaded name in a path directly.
- **Fake-data mapping lives in memory only** and is discarded after the session. Never persist real-to-fake mappings.
- **Audit log / report** stores types, counts, level, and SHA-256 hashes of input and output. **No raw values.**
- **Verify step:** re-scan the output with our own detector. If PII remains, flag it and report a residual-risk count. Do not claim "clean" if the re-scan finds anything.
- **Signed report:** HMAC-SHA256 over the report JSON using `REDACT_HMAC_KEY`. Optionally chain each report's hash to the previous one (tamper-evident log).
- Pin dependencies. No `latest`.
- Offline mode: if `REDACT_OFFLINE=1`, any attempt at an outbound request must fail loudly.

---

## 10. Testing and evaluation

- `pytest -q` must pass before every merge.
- **Per detector:** one test file with at least: a true positive, a near-miss that must **not** match, and a messy-context case.
- **Per transformer:** idempotence, offset correctness (replace from the end backwards), same real value -> same fake, fake != original.
- **Eval harness** (`eval/run_eval.py`): entity-level **Precision, Recall, F1** on (a) a public PII dataset and (b) our small hand-made **dummy** Indian-document set. Run **Presidio** on the same data and record both numbers side by side.
- Every detection or threshold change should be re-measured. Paste before/after F1 in the PR description.
- Test images and documents are **synthetic**. Generate them. Do not photograph real documents.

---

## 11. Team workflow

| Area | Owner | Notes |
|---|---|---|
| Core engine (detect / merge / policy) | _TBD_ | |
| Transforms + levels (L1-L4, fakers) | _TBD_ | |
| OCR + image writer (Paddle) | _TBD_ | |
| Dataset + PDF I/O | _TBD_ | |
| UI (Streamlit) | _TBD_ | |
| Verify + report + eval | _TBD_ | |

- `main` is always runnable. Work on short branches: `feat/<area>-<thing>`.
- Small PRs, reviewed by at least one other person. Hackathon speed: 10-minute reviews, not zero reviews.
- Commit messages: `area: what changed`.
- Before touching a shared type or signature (section 5): post in the team chat first.
- Demo day: use **dummy data only**, and rehearse the demo on the actual demo laptop **offline**.

### Build order (priority)
1. Eval harness + Presidio baseline (it is the score).
2. Levels L1 to L4 + policy table.
3. Streamlit UI: upload, level slider, entity checkboxes, before/after, download.
4. Dataset mode (CSV/JSON/XLSX): per-column typing, consistent fakes across rows.
5. Verify + signed report (our differentiator).
6. Image redaction via Paddle + position map.
7. Feedback loop ("learns over time": user corrections -> local rules / allowlist).
8. Stage 2: PDF (PyMuPDF), video (frames -> image path), annotated output.

---

## 12. Instructions for AI coding agents

1. Read this entire file first. Re-read the relevant section when starting a new module.
2. Stay inside the module you were asked to work on. Do not refactor other areas.
3. Use the signatures and types in section 5 exactly. Do not invent new fields on `Entity`, `Word` or `NormalizedDoc`.
4. Never write code that logs, prints, or stores raw PII. When debugging, print types and counts only.
5. Never add network calls, cloud SDKs, or API keys.
6. Prefer small, targeted changes over broad rewrites.
7. Write the test first or alongside the code. Run `pytest -q` before saying you are done.
8. Use `uv pip install` and Python 3.12. Assume **fish** shell for any shell commands you give the user.
9. If a requirement here conflicts with the task you were given, stop and ask instead of picking one.
10. If you are unsure whether something is allowed, treat it as not allowed and ask.

---

## 13. Definition of done (per feature)

- [ ] Runs end to end from the UI or CLI, offline
- [ ] Tests written and passing
- [ ] No raw PII in logs, outputs, report or repo
- [ ] Input formats it claims to support actually work (tried with dummy files)
- [ ] Eval numbers updated if detection changed
- [ ] This file updated if a contract or decision changed
