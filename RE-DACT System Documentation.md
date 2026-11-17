# RE-DACT: System Documentation

Nov 16, 2026 · @Ran

## Overview

RE-DACT redacts, masks or anonymizes sensitive data in documents and returns the result in the same file format, at a redaction level the user sets. It runs fully offline in a hardened container, processes input in memory, and detects sensitive content with rules and classical NLP, with no generative model in the loop.

The problem it addresses: organizations in healthcare, law, finance and government must share documents and datasets without exposing personal information. Current de-identification is mostly manual or script-driven. Existing tools treat redaction as all-or-nothing, miss indirect identifiers, or send data to third-party services.

How it works in one pass: the system detects sensitive spans once and caches them, a policy engine picks a transform for each span based on the chosen level, a format adapter writes the change back into a copy of the original file, and a verification step re-reads the output and checks that no originals survive. Moving the level slider re-runs only the transform and verification, not detection.

## Requirements and scope

The committed scope is plaintext, images and PDFs, with output in the same format as the input; video is out of scope. XLSX and DOCX are planned after the committed set.

**Must have (from the problem statement)**

- Redact, mask or anonymize input data using an NLP/ML approach.
- A gradational control over how much is redacted.
- Output that keeps the input's structure and format, with only the sensitive content changed.
- Stage 1 inputs: text files and images; outputs: redacted files and logs.
- A GUI with a web-based version and an offline version.
- No storage of input data and no retrievability by third parties.
- Measured precision, recall and F1 on an open-source test set.

**Should have (scored, not blocking)**

- A benchmark against a baseline (Microsoft Presidio).
- Efficient compute and a reported speed figure.
- Minimal API dependency, so nothing needs a cloud call.
- Secure coding practices that can be pointed to.

**Could have (Stage 2 or roadmap)**

- PDF coverage and annotated redacted outputs at the Grand Finale.
- Synthetic data generation at scale.
- A system that improves over time.

**Constraints**

- Privacy: processing in memory, no third-party calls, which rules out hosted LLM APIs.
- Compute: must run on a laptop, offline.
- Data: the Stage 2 dataset is only provided at the Grand Finale.
- Legal: the tool reduces re-identification risk; it does not claim HIPAA or GDPR compliance.
- Judging: a working proof of concept is preferred over slides.

## Architecture

RE-DACT is a linear pipeline in which detection runs once and everything after it is driven by the redaction level.

&#91;embedded content: pipeline architecture · 10 stages, one retry loop\]

The router sends each page to native extraction or OCR, detection fills the span store, and the policy engine reads the level, law profile and user choices to pick a transform. A format adapter writes the change into a copy of the file, and verification re-reads the output. A failed check retries with stricter settings, shown as the dashed loop.

## Ingestion and routing

Every upload is treated as untrusted, validated first, and then routed page by page to the cheapest path that yields text and coordinates. OCR is used only where no native text exists.

**Validation**

- File type is checked by content, not by extension.
- Size, page-count and decompression limits are enforced before parsing.
- Parsing runs in an unprivileged process, and embedded content (scripts, attachments) is never executed.

**Routing**

| Input | Path | Why |
| --- | --- | --- |
| Plaintext, CSV | Native extract | Text is already available, with character offsets |
| PDF with a text layer | Native extract | Words and coordinates come straight from the PDF |
| PDF with embedded images | Native extract for text, OCR for each image | Both layers can hold PII |
| Scanned PDF | Rasterize each page, then OCR | No text layer exists |
| Image (PNG, JPG) | OCR | Text must be recognized |
| DOCX, XLSX (planned) | Native extract | Text and structure are read from the file itself |

Native extraction is faster and more accurate than OCR, so the router decides per page rather than per file. A single PDF can send some pages down each path.

OCR output is used as evidence of where text sits, not as the file returned to the user. Which OCR engine to use is still being decided; see the last section.

## Detection

Detection is a union of deterministic layers, so every redaction traces to a named rule and the same input always gives the same spans. There is no generative model: the earlier plan for a small language model was dropped in favor of rules plus classical NLP.

| Layer | What it catches | Examples |
| --- | --- | --- |
| Rules and checksums | Structured identifiers | Emails, phone numbers, card numbers, ID numbers validated with a checksum (the Verhoeff algorithm for Aadhaar-style numbers) |
| NER | Names, places, organizations, dates | spaCy entity recognition |
| Dictionaries | Known sensitive terms | Gazetteers of names, domain terms |
| Context rules | Spans that depend on their surroundings | See below |
| Optional classifier | A sensitivity score for borderline spans | Logistic regression or gradient boosting on span features, run on CPU |

**Context rules** replace what a language model would have done:

- Cue words such as "Patient:", "Dr." or "Ms." promote nearby spans and rescue low-confidence NER hits.
- Mention propagation: once a name is found, every alias, surname, initial and possessive in the document is redacted too.
- Structure rules: form labels and column headers mark their values as sensitive (a "Salary" column, for example).
- Combination scoring: age, postal code and job title together raise a record's risk class.
- Role patterns: title plus organization, or a superlative plus a small group ("the only surgeon at ...").

The layers are unioned and never replace one another, so a higher level never detects less than a lower one. Jurisdiction-specific rules (which fields count as PII under a given law) plug in as a profile; see the policy section.

The classifier is a tiebreaker, and rules stay the main mechanism. This keeps the ML claim honest while leaving behavior auditable.

## Span store and data model

Everything downstream works from one in-memory record per detected span, which is what keeps detection format-independent and the slider instant. Detection runs once; the spans are cached, and changing the level only re-runs transform and verification.

| Field | Meaning |
| --- | --- |
| `text` | The matched original string |
| `start`, `end` | Character offsets within its text unit |
| `type` | Entity type (name, phone, email, ID, date, place, organization, ...) |
| `confidence` | Detector confidence score |
| `source` | Which layer found it (rule, NER, dictionary, context) |
| `rule_id` | The named rule behind it, used for the audit log |
| `locator` | Where it lives in the file; see below |
| `bbox` | Bounding box, for images and scanned pages |

The `locator` depends on the format, so the right adapter can find the span again when writing back:

- Plaintext: character offsets.
- PDF and image: page number plus bounding box.
- XLSX: sheet and cell.
- DOCX: paragraph and run.

**Invariant to test.** The spans detected at level N must be a subset of the spans detected at level N+1. A direct identifier at L2 must still be one at L3. This is written as a unit test, since it is easy to break by accident when adding rules.

The store lives in memory only and is discarded when the session ends.

## Policy engine and redaction levels

The policy engine maps each span's entity type and the chosen level to a transform, and the level only decides what happens to detected spans, never what is detected. Levels are presets over a per-entity policy table, which also gives users per-entity overrides.

| Level | Also covers | Transform |
| --- | --- | --- |
| L1 | Direct identifiers (names, phones, emails, IDs) | Mask, such as `[NAME]` or a black box |
| L2 | Quasi-identifiers (dates, places, ages, organizations) | Generalize: age to a range, date to month and year, city to region |
| L3 | Context and role identifiers | Consistent pseudonyms: one entity gets one fake per session |
| L4 | Same detection as L3 | Full entity substitution with perturbed numeric values; synthetic generation for tables |

Three inputs shape the policy table:

- **Level preset:** the slider position.
- **User choices:** the user can override per entity type, for example mask names but keep cities. This matches the problem statement's "customized output" wording.
- **Law profile:** a preset that marks which fields count as PII under a given regime (examples discussed: DPDP, GDPR, HIPAA). The profile feeds the policy table; it does not claim legal compliance.

Notes on scope:

- k-anonymity only makes sense on tables or batches, where there is a population to be "k" within. For a single text document, L2 uses generalization rules and a risk heuristic instead.
- L1 does not remove context-based identifiers, and the interface should say so.
- The committed target is L1 to L3. L4 is roadmap.

## Transform and consistency

The transform step rewrites each span according to the policy, and at L3 it guarantees that the same real entity always becomes the same fake within a session. Without that guarantee a document would turn "Priya" into one name in paragraph one and another in paragraph three.

**How the actions work**

- **Mask:** replace with a type label (`[NAME]`) or a black box on images and PDFs.
- **Generalize:** reduce precision, for example age 34 to 30-39, an exact date to month and year, a city to a region.
- **Pseudonymize (L3):** build a keyed hash (HMAC) of the canonical entity and use it to seed a fake-data generator such as Faker. The same input entity yields the same fake.
- **Substitute (L4):** replace every entity and perturb numeric values; for tables, column-wise or SDV-style synthetic generation (roadmap).

**Canonicalization.** Before hashing, mentions are resolved to one entity ID, so "Priya", "Ms. Sharma" and "Sharma's" map to the same person. Pronoun resolution is heuristic (nearest mention), so a person can occasionally be split into two fakes. This is a known limit.

**Session key.** The HMAC key is random per session, held only in memory, never written to disk, and zeroed afterward. That gives consistency inside one document, with no way to link or reverse fakes across documents.

**Fit in fixed space.** In PDFs and images a replacement must fit the original box. Fakes there are the same length or shorter, and anything that does not fit falls back to a labeled mask.

## Format adapters

The output must be the same file type as the input, so redaction happens inside each format and never on extracted text. Markdown or JSON from an OCR parser is evidence of where PII sits, not the file returned.

Every format gets an adapter with the same three operations: `extract` returns text units with a locator, `apply` writes redactions into a copy of the file, and `verify` re-extracts the output for the leak check. Detection, policy and transform stay format-independent, so the slider behaves identically everywhere.

| Format | How PII is found | How it is redacted | Watch out for |
| --- | --- | --- | --- |
| Plaintext, logs | Character offsets | Replace at the offsets | Keep encoding, line endings and whitespace |
| CSV, JSON | Parse, then scan values | Edit values only, keep keys and headers | Column order, quoting, types |
| Image | OCR word or line boxes | Fill boxes, save in the same format and size | Strip EXIF and thumbnails; JPEG re-encodes |
| PDF with text layer | Words and coordinates from the PDF itself | True redaction annotations, optionally with replacement text, then apply | Replacement text must fit the original box and font |
| PDF with images | Text layer plus OCR on each embedded image | Also redact the image pixels | Redaction must remove the pixels underneath, not draw over them |
| Scanned PDF | Rasterize pages, then OCR | Redact the pixels, rebuild the PDF | The text layer is lost; optionally re-OCR to keep it searchable |
| DOCX (planned) | Walk paragraphs, tables, headers, footers | Edit runs in place | A name can span several runs; comments and tracked changes |
| XLSX (planned) | Walk cells | Edit values, keep styles | Formulas, comments, hidden sheets, named ranges, charts |

**PDF redaction has to be real.** Drawing a black box over text leaves it selectable underneath. The adapter uses redaction annotations and applies them so the underlying text and image pixels are removed. It also strips metadata (author, title, creating tool), XMP data, annotations, comments, embedded files, form-field values, bookmarks and document history.

**Images.** The redacted image is flattened so the original pixels are gone, and EXIF data is stripped.

## Verification

Every output is re-read and checked for surviving originals before it is returned, because a redaction that looks right on screen can still leave the data in the file. This runs at all levels and on all formats.

1. **Re-extract.** The `verify` operation reads the redacted file back the way a recipient would: text extraction for text files and PDFs, OCR again for images and scanned pages.
2. **Search for originals.** Every original span string is searched for in the extracted text, both exactly and with fuzzy matching, since text can be changed slightly by re-encoding or OCR.
3. **Tolerate legitimate retention.** At L2 some partial values survive on purpose, such as a year kept after a date is generalized, so the check compares against what the policy was supposed to keep.
4. **On failure,** the file is regenerated with stricter settings or a plain mask rather than returned. This loop back to the transform step is part of the design, though it is not drawn in the system diagram.

An L4 rewrite is the riskiest case: substituted text can still contain, or paraphrase, an original value, so the fuzzy check matters most there.

Logs from this step hold metadata only (entity type, count, rule ID, pass or fail), never the original text. The problem statement treats logs as an output, so a log that leaked originals would defeat the tool.

## Security design

The tool handles the data people most want to protect, so security is built into the architecture and each claim should be measurable. Everything ships as one container that runs with no network.

**Container**

- Non-root user, read-only root filesystem, all Linux capabilities dropped, and a seccomp profile.
- Scratch space on `tmpfs`, so nothing persists after the container stops.
- Run with `--network none` for offline mode. The same image can serve the online case behind TLS, rate limiting and a content security policy.
- Minimal base image with pinned digests. Model weights are baked into the image so nothing downloads at runtime.

**Input handling**

- Content-based type checks, size limits, and guards against decompression bombs, malicious PDFs and path traversal in archives.
- Parsing in an unprivileged process; embedded scripts and attachments are never executed.

**Data handling**

- Input is processed in memory and never retained.
- The pseudonymization key is per session, never stored, and zeroed after use.
- Logs carry metadata only, never original text.
- The leak check runs on every output.

**Interface**

- A thin local web layer with one upload endpoint and one download endpoint. No accounts and no database.

**Supply chain and process**

- Dependency scanning (`pip-audit`, Trivy), static analysis (Bandit), an SBOM and signed images.
- A short STRIDE threat model.
- License checks before adding libraries: PyMuPDF is AGPL, and MinerU's license has changed between versions, so read the current text before shipping.

Examples of measurable claims: the container passes a Trivy scan with no high-severity findings, and no file is written outside `tmpfs`, verified by a test.

## Evaluation

The problem statement scores detection quality, how well the level slider is calibrated, speed, and benchmarking, so the evaluation measures each of them rather than only precision and recall. Recall matters most, since a missed identifier is a privacy failure while an over-redacted word is only an annoyance.

| Measure | What it shows | How |
| --- | --- | --- |
| Precision, recall, F1 | Detection quality | Open de-identification dataset, with a held-out split so rules are not tuned on test data |
| Baseline comparison | Standing against an existing tool | Microsoft Presidio, run on the same data |
| Ablation | What each layer adds | Rules only, then plus NER, then plus context rules |
| Leakage rate | Originals surviving in the output | Per level, using the verification step |
| Utility | Whether redacted data is still useful | A downstream task or field-structure preservation, per level |
| Structure fidelity | Whether output matches the input's structure | Per format, see below |
| Systems metrics | Speed and footprint | Throughput, memory, container scan results |

The privacy-versus-utility curve across L1 to L3 is the main benchmark exhibit.

**Structure fidelity checks**

- PDFs and images: same page count and dimensions, and a pixel comparison of unredacted areas against the original.
- XLSX: same sheets, cell count, formulas and styles outside redacted cells.
- DOCX: same paragraph and table counts, styles and layout outside redacted runs.
- All formats: the file opens in a standard viewer without errors.

Indirect-identifier recall is reported separately from direct-identifier recall. It is the weak spot of a rule-based system, and stating it is more credible than leaving judges to find it.

The Stage 2 dataset arrives only at the Grand Finale, so the PDF path must be robust to unseen layouts, with the L1 and L2 path as the fallback.

## Limitations and known risks

RE-DACT reduces re-identification risk but cannot guarantee anonymization, and the known gaps should be stated openly in the pitch and the interface.

- **Implicit identifiers.** Paraphrased or implied identifiers ("the head of the largest bank in town") are caught less often than direct ones, because the core is rule-based.
- **Pronoun resolution is heuristic.** One person can occasionally be split into two fakes at L3.
- **OCR caps image recall.** A name that OCR misreads or misses cannot be redacted by any detector. Scanned PDFs inherit the same limit.
- **Box precision.** If an OCR returns whole lines instead of words, a box can cover more than the PII, and boxes may need slicing by character position.
- **L4 is substitution, not new text.** The output is the original text with entities swapped, not freshly written text. For images and PDFs, expect labeled masks to cover most cases, with fake-value replacement mainly in plaintext and text-based PDFs.
- **Rule maintenance.** Rules need tuning per domain and can overfit the test set, which is why a held-out split is required.
- **Legal.** "Anonymized" is a legal standard, not a feature. The tool does not claim HIPAA or GDPR compliance.
- **Out of scope.** Video, audio and face tracking. "Learns over time" is roadmap, planned as user-approved rules and dictionary entries rather than retained data.

## OCR selection, testing and status

The OCR engine is not yet chosen: the team is testing MinerU first, with PaddleOCR-VL-1.6 as the alternative and a classic OCR as the fallback. The deciding measure is box quality, because the box is what gets redacted.

**Candidates**

|  | PaddleOCR-VL-1.6 | MinerU |
| --- | --- | --- |
| License | Apache 2.0 | Moved from AGPLv3 to a custom Apache-based license in 3.1.0; one source says thresholds still apply, so verify |
| Accuracy (OmniDocBench v1.6) | 96.33 overall | 95.75 for MinerU2.5-Pro |
| CPU use | Possible, but no speed figures found; benchmark on the target laptop | Has a `pipeline` backend for pure CPU |
| Formats | Images, PDFs | Also DOCX, PPTX, XLSX natively |

Both are document parsers that output Markdown and JSON, not word-level OCR, so they must be tested for coordinate granularity before the choice is made.

**Test procedure** (script `ocr_test.py`)

1. Install MinerU in a virtual environment (Python 3.10 to 3.12) and download its models once.
2. Run `python ocr_test.py`. It builds `test.png` with five fake PII lines, runs MinerU's CPU `pipeline` backend, and reads the `*_middle.json` output.
3. It prints everything the OCR read, marks each known PII string FOUND or MISSING with recall as a fraction, flags spans whose box covers more than the PII, and saves `boxes.png` with the boxes drawn.
4. Repeat on 10 to 20 harder files (a phone photo, a skewed scan, a low-resolution screenshot, text and scanned PDFs) and record found and missing counts.

The script's parsing and drawing logic was checked against a mock output only. MinerU's real JSON field names were written from memory and may need adjusting. No real OCR results exist yet.

**Build order**

1. Span data model, policy YAML, and a test that levels never shrink detection.
2. Plaintext pipeline (rules and NER, L1 and L2), evaluation harness, Presidio comparison.
3. Context rules and the leak check.
4. Dockerized local UI with the security hardening.
5. Image path: OCR, boxes, blackout.
6. PDF path: text-based first, then embedded images, then scanned.
7. L3 consistent fakes, starting with plaintext.
8. Annotated outputs for Stage 2.

A thin slice (plaintext, a text-layer PDF and a simple image at L1 and L2, with a UI and a container) is estimated at about 5 to 6 focused hours. The evaluation, L3 and DOCX or XLSX adapters need more time.

**Open questions**

- Deadline and team size, which decide whether the competitive target is realistic.
- Whether the Stage 1 dataset choice is the team's to make.
- Which OCR wins the bake-off.
