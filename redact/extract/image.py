"""RE-DACT image extraction module using PaddleOCR.

Conforms to AGENTS.md section 5:
    def to_normalized(path_or_bytes) -> NormalizedDoc: ...
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
from PIL import Image

from redact.entity import NormalizedDoc
from redact.extract.ocr import ocr, words_to_normalized


def to_normalized(
    path_or_bytes: str | Path | bytes | Image.Image | np.ndarray,
) -> NormalizedDoc:
    """Extract text and word coordinates from an image into NormalizedDoc."""
    words = ocr(path_or_bytes)
    return words_to_normalized(words)
