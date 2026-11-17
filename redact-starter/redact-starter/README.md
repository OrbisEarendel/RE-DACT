# RE-DACT starter

Redacts sensitive data and returns the same file format. Detect once, then the level only chooses what to do with each finding.

## Run it (should work before you change anything)

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
make demo                        # redacts samples/test.txt
make test                        # runs the tests
```

If you don't have `make` (Windows): run `python -m app.cli samples/test.txt --level 1` and `python -m pytest -q`.

## Who owns what

| Folder | Owner | Job |
| --- | --- | --- |
| `detect/`, `eval/` | P1 | Find sensitive text; measure how well |
| `adapters/` | P2 | Read and write each file format (text, image, PDF) |
| `core/` | P3 | Span model, policy, transform, `redact()` pipeline |
| `app/`, `docker/` | P4 | UI, validation, logging, container, security |
| `samples/` | everyone | Shared test files + ground truth |

## The data flow

```
file -> adapter.extract -> units -> detectors -> spans -> policy+transform -> edits -> adapter.apply -> output file
                                                                                        adapter.verify (leak check)
```

## Team rules

1. Work only in your own folder. Need a change elsewhere? Message the owner.
2. `core/types.py` is the contract. Add things freely; rename or remove nothing without telling everyone.
3. `main` must always pass `make demo` and `make test`. If you break it, fixing it comes first.
4. Small branches, merge at least every hour or two.
5. Logs hold metadata only (counts, types, rule ids). Never original text.
6. Don't edit `samples/*.expected.json` to make a test pass. Fix the code.

## Git in 6 commands

```bash
git checkout -b p1/name-detection   # new branch for your work
# ...edit files...
git add .
git commit -m "Add NER for person names"
git pull --rebase origin main       # get others' changes first
git push -u origin p1/name-detection  # then open a pull request on GitHub
```
