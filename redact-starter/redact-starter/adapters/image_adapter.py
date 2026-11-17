"""Image adapter using PaddleOCR (PP-OCRv5 pipeline). Owner: P2.

Flow: OCR gives one text line + one box per line -> each line is a TextUnit.
Detectors find spans inside the line text. We then slice the line's box to just the span
and black it out, and save a clean copy (no EXIF) in the same format.

KNOWN LIMIT: a span is a few characters inside a line, but OCR gave us the whole line's box.
slice_box() estimates the span's position assuming equal character widths. That is only
approximate for normal fonts, so the box has padding and verify() re-OCRs the output.
If boxes are off, look for word-level boxes in PaddleOCR (check the 'return_word_box' option
in the PaddleOCR 3.x docs for your installed version; it was not confirmed here).

Setup (CPU):  pip install paddlepaddle==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
              pip install paddleocr
Install the CPU build OR the GPU build, never both.
OFFLINE: models download on first use. Run once with internet to fill the cache, bake the
cache into the Docker image, and pin ocr_version.
"""
import os

from PIL import Image, ImageDraw

from core.types import Edit, TextUnit

PAD = 3  # pixels of padding around each blackout box


def poly_to_bbox(poly) -> tuple:
    xs = [float(p[0]) for p in poly]
    ys = [float(p[1]) for p in poly]
    return (min(xs), min(ys), max(xs), max(ys))


def slice_box(bbox: tuple, n_chars: int, start: int, end: int, pad: int = PAD) -> tuple:
    """Estimate the sub-box for characters [start, end) of a line whose box is bbox."""
    x0, y0, x1, y1 = bbox
    cw = (x1 - x0) / max(n_chars, 1)
    return (x0 + start * cw - pad, y0 - pad, x0 + end * cw + pad, y1 + pad)


class ImageAdapter:
    extensions = (".png", ".jpg", ".jpeg")

    def __init__(self):
        self._engine = None
        self._units: dict = {}  # path -> units from the last extract() of that path

    def _ocr(self):
        if self._engine is None:
            from paddleocr import PaddleOCR  # imported late so the repo runs without it
            self._engine = PaddleOCR(
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                lang="en",
                ocr_version="PP-OCRv5",  # pin it: defaults change between releases
            )
        return self._engine

    def extract(self, path: str) -> list[TextUnit]:
        units = []
        for res in self._ocr().predict(path):
            for text, score, poly in zip(res["rec_texts"], res["rec_scores"], res["rec_polys"]):
                units.append(TextUnit(text=text, locator={
                    "kind": "image-line", "bbox": poly_to_bbox(poly), "ocr_score": float(score)}))
        self._units[path] = units
        return units

    def apply(self, path: str, out_path: str, edits: list[Edit]) -> None:
        units = self._units.get(path) or self.extract(path)
        img = Image.open(path).convert("RGB")
        draw = ImageDraw.Draw(img)
        for e in edits:
            unit = units[e.span.unit]
            box = slice_box(unit.locator["bbox"], len(unit.text), e.span.start, e.span.end)
            draw.rectangle(box, fill=(0, 0, 0))
        # Rebuild from raw pixels so EXIF / metadata is not carried over.
        clean = Image.frombytes("RGB", img.size, img.tobytes())
        fmt = "JPEG" if os.path.splitext(out_path)[1].lower() in (".jpg", ".jpeg") else "PNG"
        clean.save(out_path, format=fmt)

    def verify(self, out_path: str, originals: list[str]) -> list[str]:
        text = " ".join(u.text for u in self.extract(out_path))
        return [o for o in originals if o and o in text]
