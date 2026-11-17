"""Plaintext adapter. Works fully, so you have one finished example to copy. Owner: P2."""
from core.types import Edit, TextUnit


class TextAdapter:
    extensions = (".txt", ".log")

    def extract(self, path: str) -> list[TextUnit]:
        with open(path, encoding="utf-8") as f:
            return [TextUnit(text=f.read(), locator={"kind": "text"})]

    def apply(self, path: str, out_path: str, edits: list[Edit]) -> None:
        with open(path, encoding="utf-8", newline="") as f:
            text = f.read()
        # Replace from the end so earlier offsets stay valid; skip overlapping spans.
        last_start = len(text) + 1
        for e in sorted(edits, key=lambda e: e.span.start, reverse=True):
            if e.span.end > last_start:
                continue
            text = text[:e.span.start] + e.replacement + text[e.span.end:]
            last_start = e.span.start
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            f.write(text)

    def verify(self, out_path: str, originals: list[str]) -> list[str]:
        with open(out_path, encoding="utf-8") as f:
            text = f.read()
        return [o for o in originals if o and o in text]
