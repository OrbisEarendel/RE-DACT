"""RE-DACT plain text extraction module.

Conforms to AGENTS.md section 5:
    def to_normalized(path_or_bytes) -> NormalizedDoc: ...
"""

from __future__ import annotations

import io
from pathlib import Path

from redact.entity import NormalizedDoc


def to_normalized(
    path_or_bytes: str | Path | bytes,
    encoding: str = "utf-8",
) -> NormalizedDoc:
    """Extract text from plain text/log inputs into NormalizedDoc."""
    if isinstance(path_or_bytes, (str, Path)):
        p = Path(path_or_bytes)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {p}")
        text = p.read_text(encoding=encoding, errors="replace")
    elif isinstance(path_or_bytes, bytes):
        text = path_or_bytes.decode(encoding, errors="replace")
    else:
        text = str(path_or_bytes)

    spans: list[tuple[int, int, str]] = []
    offset = 0
    for idx, line in enumerate(text.splitlines(keepends=True)):
        spans.append((offset, offset + len(line), f"line:{idx + 1}"))
        offset += len(line)

    return NormalizedDoc(text=text, spans=spans)
