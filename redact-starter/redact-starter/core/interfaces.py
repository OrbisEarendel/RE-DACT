"""The shapes each part must have. Implement these in your own folder.

Detector  -> detect/      (P1)
Adapter   -> adapters/    (P2)
"""
from typing import Protocol

from core.types import Edit, Span, TextUnit


class Detector(Protocol):
    def detect(self, units: list[TextUnit]) -> list[Span]:
        """Find sensitive spans. Must not depend on the redaction level."""
        ...


class Adapter(Protocol):
    extensions: tuple  # e.g. (".txt",)

    def extract(self, path: str) -> list[TextUnit]:
        """Read the file and return its text units."""
        ...

    def apply(self, path: str, out_path: str, edits: list[Edit]) -> None:
        """Write a COPY of the file with the edits applied, in the SAME format."""
        ...

    def verify(self, out_path: str, originals: list[str]) -> list[str]:
        """Re-read the output. Return the original strings that are still in it (should be [])."""
        ...
