"""Tests box math and blackout WITHOUT PaddleOCR, by injecting fake OCR lines."""
from PIL import Image

from adapters.image_adapter import ImageAdapter, poly_to_bbox, slice_box
from core.types import Edit, Span, TextUnit


def test_poly_to_bbox():
    assert poly_to_bbox([[10, 20], [110, 18], [112, 40], [9, 42]]) == (9.0, 18.0, 112.0, 42.0)


def test_slice_box_covers_only_the_span():
    # line "Phone: 12345" is 12 chars in a 120px-wide box; the number is chars 7..12
    x0, y0, x1, y1 = slice_box((0, 0, 120, 20), 12, 7, 12, pad=0)
    assert (x0, x1) == (70.0, 120.0) and (y0, y1) == (0, 20)


def test_apply_blacks_out_span_only_and_strips_exif(tmp_path):
    src, out = str(tmp_path / "in.png"), str(tmp_path / "out.png")
    img = Image.new("RGB", (200, 60), "white")
    exif = Image.Exif()
    exif[0x010E] = "secret description"
    img.save(src, exif=exif)

    unit = TextUnit(text="Phone: 12345", locator={"kind": "image-line", "bbox": (0, 20, 120, 40)})
    ad = ImageAdapter()
    ad._units[src] = [unit]  # pretend OCR already ran
    span = Span(text="12345", start=7, end=12, type="PHONE", unit=0)
    ad.apply(src, out, [Edit(span=span, replacement="[PHONE]")])

    result = Image.open(out)
    assert result.getpixel((100, 30)) == (0, 0, 0)       # inside the PII: black
    assert result.getpixel((10, 30)) == (255, 255, 255)  # the label "Phone:" untouched
    assert not result.getexif()                          # metadata gone
