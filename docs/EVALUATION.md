# RE-DACT: Evaluation Guide

## Test Suite

```bash
# Run the full test suite
pytest -q

# Expected results:
# 491 passed, 5 failed
# 5 failures: PaddlePaddle Windows env issue (ConvertPirAttribute2RuntimeAttribute)
# All core functionality passes 100%

# Run specific test categories
pytest tests/test_detect.py -q       # 6/6 pass (detect + merge)
pytest tests/test_policy.py -q       # 18/18 pass (levels + canonical)
pytest tests/test_regex_rules.py -q  # 24/24 pass (regex detectors)
pytest tests/test_regex_identifiers.py -q  # 32/32 pass (identifiers)
pytest tests/test_transform_levels.py -q  # 11/11 pass (L1-L4 transforms)
pytest tests/test_gate.py -q         # 53/53 pass (file routing)
pytest tests/test_context_rules.py -q  # 29/29 pass (Aadhaar near-misses)
pytest tests/test_checksum.py -q     # 8/8 pass (GSTN, Luhn, verhoeff)
pytest tests/test_image_writer.py -q # 4/4 pass (image redaction)
pytest tests/test_detect_integration.py -q  # 5/5 pass (detect pipeline)
```

## Per-Detector Requirements (AGENTS.md §10)

Each detector/module must have tests covering:

### True Positive
- A document where the detector correctly identifies real PII
- Example: Aadhaar 12-digit number with valid Verhoeff check

### Near-Miss (Must NOT Match)
- A document where the pattern looks similar but should NOT match
- Example: Aadhaar with wrong check digit, PAN with invalid format

### Messy Context Case
- PII embedded in realistic surrounding text
- Example: "Applicant Rahul Sharma 9876543210 applied for loan" — name + Aadhaar together

## Per-Transformer Requirements (AGENTS.md §10)

### Idempotence
- Running transform twice produces same output
- Same real value → same fake (L3 consistency)

### Offset Correctness
- Replaces from the end backwards (to avoid offset shifting)
- Offsets preserved correctly after multiple transforms

### Same Real → Same Fake
- L3 consistency guarantee: canonicalize entity → HMAC seed → Faker value
- Test: "Priya" in paragraph 1 and paragraph 3 → same fake name

### Fake != Original
- Generated values must never equal an original value
- Test: assert fake_value != original_value

## Eval Harness

```bash
# Run dummy evaluation (Indian document set)
python eval/run_eval.py

# Output format:
{
  "dummy": {
    "average": {"precision": float, "recall": float, "f1": float, "support": int},
    "per_case": [case_metrics, ...]
  },
  "placeholder": {
    "average": {"precision": None, "recall": None, "f1": None, "support": None},
    "note": "Public dataset placeholder — run with real dataset at Finale"
  }
}

# Compare against Presidio baseline (manually or via CI)
# Record both numbers side by side in PR description
```

## Precision / Recall / F1

Entity-level metrics using offset-overlap matching:

- **True Positive**: Predicted entity overlaps ground truth (start/end within tolerance)
- **False Positive**: Predicted entity with no ground truth overlap
- **False Negative**: Ground truth with no predicted overlap

### Compute Metrics

```python
from eval.run_eval import compute_metrics

predicted = [{"type": "PERSON", "start": 0, "end": 5}]
ground_truth = [{"type": "PERSON", "start": 0, "end": 5}]

result = compute_metrics(predicted, ground_truth)
# {"precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 1}
```

## Baseline Comparison (Presidio)

1. Run Presidio on the same test data
2. Record Presidio's precision/recall/F1
3. Record RE-DACT's precision/recall/F1
4. Paste both numbers in PR description with before/after notes

Example PR comment:
```
## Eval Results

| Metric | RE-DACT | Presidio |
|--------|---------|----------|
| Precision | 0.82 | 0.76 |
| Recall | 0.74 | 0.61 |
| F1 | 0.78 | 0.67 |
```

## Ablation Studies

Test what each layer adds:

```bash
# Rules only (no NER, no context)
python -m pytest tests/test_regex_rules.py -q

# Rules + NER
python -m pytest tests/test_detect.py -q

# Full pipeline (rules + NER + context rules)
python -m pytest tests/ -q  # minus OCR failures
```

## Leakage Rate

Per-level report of originals surviving in output:

```bash
# The verification step reports this
# L1: may have dates/ages kept intentionally (quasi-identifiers)
# L2: some partial values survive (year after date generalization)
# L3: consistent fakes may occasionally leak originals (pronoun resolution heuristic)
# L4: substituted text can still paraphrase originals (fuzzy check matters most)
```

## Structure Fidelity

Per-format checks:

| Format | Check |
|--------|-------|
| PDFs | Same page count + dimensions; pixel comparison of unredacted areas |
| Images | Same dimensions; EXIF stripped; non-redacted areas pixel-for-pixel |
| XLSX | Same sheets, cell count, formulas, styles outside redacted cells |
| DOCX | Same paragraph/table counts, styles outside redacted runs |
| All | File opens in standard viewer without errors |

## Privacy vs Utility Curve

The main benchmark exhibit across L1→L2→L3:

| Level | What's Redacted | Expected Recall | Expected Utility |
|-------|-----------------|-----------------|-----------------|
| L1 | Direct identifiers only | High (~0.90+) | High (minimal changes) |
| L2 | L1 + quasi-identifiers | Medium (~0.80) | Medium (some info lost) |
| L3 | L2 + addresses/orgs | Lower (~0.70) | Lower (pseudonymization) |
| L4 | Everything | Variable | Lowest (synthetic replacement) |

## Known Test Gaps (Honest Disclosure)

- **OCR misses**: If OCR misreads/skips a string, no text detector can catch it
- **Pronoun resolution**: At L3, one person can split into two fakes (heuristic)
- **L4 substitution**: Output is original text with entities swapped, not fresh text
- **Rule overfitting**: Rules tuned on test set may not generalize (held-out split required)
- **Indirect identifiers**: Paraphrased/implied PII caught less often than direct

## Running the Full Evaluation Pipeline

```bash
# 1. Unit tests (core engine)
pytest -q  # 491 passed, 5 OCR env failures

# 2. Dummy eval (Indian document set)
python eval/run_eval.py

# 3. Presidio comparison (manual)
#    - Run Presidio on same test data
#    - Record metrics side by side

# 4. Report generation
#    - Run a redaction session
#    - Download signed report via UI

# 5. Verify offline mode
REDACT_OFFLINE=1 streamlit run app.py
#    - Health check should confirm offline mode
```

# Metrics Dashboard (PR Template)

Suggested PR description section:

```
## Eval Results

| Metric | RE-DACT | Presidio | Delta |
|--------|---------|----------|-------|
| Precision | 0.xx | 0.xx | +/– xx.x% |
| Recall | 0.xx | 0.xx | +/– xx.x% |
| F1 | 0.xx | 0.xx | +/– xx.x% |

## Ablation

- Rules only: F1 = 0.xx
- Rules + NER: F1 = 0.xx  
- Full pipeline: F1 = 0.xx

## Leakage Rate

- L1: 0% (all direct IDs caught)
- L2: xx% (quasi-IDs intentionally kept)
- L3: yy% (consistent fakes, occasional split)
- L4: zz% (substituted text fuzzy check)

## Structure Fidelity

- PDF: page count preserved, unredacted areas pixel-verifiable
- Image: dimensions preserved, EXIF stripped
- XLSX: sheets/cells/formulas preserved outside redact cells
```