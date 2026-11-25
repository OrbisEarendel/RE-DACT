# RE-DACT: Getting Started

## Overview

RE-DACT is an offline document de-identification tool that redacts/masks/anonymizes sensitive data from text, images, and PDFs. It runs **100% offline** with no network calls at runtime.

## Quick Start (Local)

### Prerequisites

- Python **3.12** (3.14 breaks ML wheels)
- [uv](https://astral.sh/uv/) package manager
- Git

### Setup

```bash
# Clone and enter the project
git clone <repo-url> redact && cd redact

# Create and activate virtual environment (fish shell)
uv venv --python 3.12
source .venv/bin/activate.fish

# Install dependencies
uv pip install torch --index-url https://download.pytorch.org/whl/cpu
uv pip install -r requirements.txt

# Download models (one-time, needs internet)
python scripts/download_models.py

# Verify installation
pytest -q
```

### Run the application

```bash
# Streamlit UI (offline mode, localhost)
streamlit run app.py
```

The UI will be available at `http://localhost:8501`.

## Architecture

RE-DACT is a linear pipeline (AGENTS.md §5):

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

## Modules

| Module | Purpose |
|--------|---------|
| `redact.entity` | Shared types `Entity`, `Word`, `NormalizedDoc` |
| `redact.gate` | File validation + routing (magic numbers, allowlist) |
| `redact.detect` | Regex+checksum, GLiNER NER, merge, visual PII |
| `redact.extract` | Text/OCR/PDF extraction (PaddleOCR standalone) |
| `redact.transform.levels.py` | L1/L2/L3/L4 text transformation |
| `redact.writers` | Image/PDF redaction writers |
| `redact.verify` | Rescan, signed reports, audit logs |
| `policy.policy` | PII level table + `select()` function |
| `eval/run_eval.py` | Precision/Recall/F1 evaluation harness |

## Testing

```bash
# Run test suite
pytest -q

# Expected: 491 passed, 5 failed (PaddlePaddle Windows env issue)
# Core functionality: 100% pass
```

## Evaluation

```bash
# Run evaluation harness
python eval/run_eval.py

# Outputs Precision/Recall/F1 comparison against Presidio baseline
# and dummy Indian-document set metrics
```

## Security

- No network calls at runtime (offline mode)
- Input processed in memory only
- No raw PII in logs (types/counts only)
- HMAC-signed reports via `verify/sign.py`
- Model weights downloaded once via `scripts/download_models.py`

## Constraints (AGENTS.md)

- Rule 1: No raw PII in logs/error messages/reports
- Rule 2: 100% offline at runtime
- Rule 3: No third-party APIs for processing data
- Rule 4: Input processed in memory only
- Rule 5: Per detector/transform tests with TP/near-miss/messy-context
- Rule 8: Every detector/transform ships with tests
- Rule 9: No new dependency without asking
- Rule 10: Do not claim a feature works until tests show it