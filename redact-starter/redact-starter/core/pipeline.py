"""The one function the UI calls. Owner: P3.

    redact("samples/test.txt", level=1)
"""
import os

from adapters import get_adapter
from core.transform import build_edits
from core.types import RedactResult
from detect import run_detectors


def redact(path: str, level: int = 1, overrides: dict | None = None,
           out_dir: str = "out") -> RedactResult:
    os.makedirs(out_dir, exist_ok=True)
    adapter = get_adapter(path)

    units = adapter.extract(path)
    spans = run_detectors(units)
    edits = build_edits(spans, level, overrides)

    base, ext = os.path.splitext(os.path.basename(path))
    out_path = os.path.join(out_dir, f"{base}.redacted{ext}")
    adapter.apply(path, out_path, edits)

    leaks = adapter.verify(out_path, [e.span.text for e in edits])

    # LOG RULE: metadata only. Never put span.text or any original text in here.
    counts: dict = {}
    for e in edits:
        counts[e.span.type] = counts.get(e.span.type, 0) + 1
    log = {
        "input": os.path.basename(path),
        "level": level,
        "spans_found": len(spans),
        "spans_redacted": len(edits),
        "by_type": counts,
        "rules_fired": sorted({e.span.rule_id for e in edits}),
        "leaks_found": len(leaks),
        "verified_clean": len(leaks) == 0,
    }
    return RedactResult(out_path=out_path, log=log)
