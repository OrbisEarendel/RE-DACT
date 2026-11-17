"""Tests for redact/gate.py. Dummy data only. Needs only pymupdf, Pillow and pytest."""
import io
import sys
import zipfile
from pathlib import Path

import pymupdf
import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from redact import (  # noqa: E402
    EncryptedInput, Engine, Format, GateConfig, GateError, InputTooLarge, Kind,
    UnsupportedFormat, route,
)
from redact import gate  # noqa: E402

LOREM = "Patient Rahul Sharma lives at 12 MG Road Bengaluru and his phone is 9876543210. " * 3


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("REDACT_MAX_FILE_MB", raising=False)
    monkeypatch.delenv("REDACT_ALLOWED_EXT", raising=False)


# ---------- fixture builders (all in memory) ---------- #

def img_bytes(size=(1200, 1600), text="Rahul Sharma 9876543210", fmt="PNG"):
    im = Image.new("RGB", size, "white")
    ImageDraw.Draw(im).text((50, 50), text, fill="black")
    buf = io.BytesIO()
    im.save(buf, format=fmt)
    return buf.getvalue()


def pdf_text_page(doc):
    p = doc.new_page()
    p.insert_text((72, 100), LOREM[:120])
    p.insert_text((72, 120), LOREM[120:240])
    return p


def pdf_scan_page(doc, hidden_text=False):
    p = doc.new_page()
    p.insert_image(p.rect, stream=img_bytes())
    if hidden_text:
        p.insert_text((72, 100), LOREM[:120], render_mode=3)
    return p


def make_pdf(builders):
    doc = pymupdf.open()
    for b in builders:
        b(doc)
    data = doc.tobytes()
    doc.close()
    return data


def make_xlsx(sheets=(("Summary", "visible"),), media=None):
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    body = "".join(f'<sheet name="{n}" sheetId="{i + 1}" state="{s}"/>' for i, (n, s) in enumerate(sheets))
    wb = f'<?xml version="1.0"?><workbook xmlns="{ns}"><sheets>{body}</sheets></workbook>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("xl/workbook.xml", wb)
        for name, content in (media or {}).items():
            z.writestr(name, content)
    return buf.getvalue()


# ---------- PDF ---------- #

def test_pdf_pages_routed_individually():
    plan = route(make_pdf([pdf_text_page, pdf_scan_page, pdf_text_page]), filename="a.pdf")
    assert plan.format is Format.PDF
    assert [r.engine for r in plan.routes] == [Engine.NATIVE, Engine.OCR, Engine.NATIVE]
    assert plan.routes[1].kind is Kind.SCAN
    assert [r.unit for r in plan.ocr_units] == [1]


def test_scan_with_hidden_ocr_layer_goes_to_ocr():
    r = route(make_pdf([lambda d: pdf_scan_page(d, hidden_text=True)])).routes[0]
    assert r.engine is Engine.OCR and r.kind is Kind.SCAN
    assert "hidden OCR layer" in r.reason


def test_visible_text_over_full_page_image_is_both():
    def page(doc):
        p = doc.new_page()
        p.insert_image(p.rect, stream=img_bytes())
        p.insert_text((72, 100), LOREM[:120])
        p.insert_text((72, 120), LOREM[120:240])
    r = route(make_pdf([page])).routes[0]
    assert r.engine is Engine.BOTH and r.kind is Kind.MIXED and r.ocr_regions


def test_text_page_with_embedded_picture_is_mixed_with_region():
    def page(doc):
        p = pdf_text_page(doc)
        p.insert_image(pymupdf.Rect(72, 300, 372, 500), stream=img_bytes((300, 200)))
    r = route(make_pdf([page])).routes[0]
    assert r.engine is Engine.BOTH and r.kind is Kind.MIXED
    assert len(r.ocr_regions) == 1


def test_blank_page():
    r = route(make_pdf([lambda d: d.new_page()])).routes[0]
    assert r.kind is Kind.BLANK and r.engine is Engine.NONE


def test_sparse_page_number_stays_native():
    def page(doc):
        doc.new_page().insert_text((300, 800), "12")
    assert route(make_pdf([page])).routes[0].engine is Engine.NATIVE


def test_outlined_text_page_goes_to_ocr():
    def page(doc):
        p = doc.new_page()
        for i in range(300):  # many separate tiny paths, no text layer
            p.draw_rect(pymupdf.Rect(50 + (i % 20) * 10, 50 + (i // 20) * 10,
                                     55 + (i % 20) * 10, 55 + (i // 20) * 10), fill=(0, 0, 0))
    r = route(make_pdf([page])).routes[0]
    assert r.engine is Engine.OCR and "outlined" in r.reason


def test_encrypted_pdf_rejected():
    doc = pymupdf.open()
    pdf_text_page(doc)
    data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="x", owner_pw="y")
    with pytest.raises(EncryptedInput):
        route(data)


def test_corrupt_pdf_rejected():
    with pytest.raises(UnsupportedFormat):
        route(b"%PDF-1.7\nthis is not really a pdf")


def test_page_cap():
    data = make_pdf([lambda d: d.new_page()] * 5)
    with pytest.raises(InputTooLarge):
        route(data, config=GateConfig(max_units=3))


def test_pdf_metadata_warning_has_no_values():
    doc = pymupdf.open()
    pdf_text_page(doc)
    doc.set_metadata({"author": "Alan Secret Name"})
    plan = route(doc.tobytes())
    assert any("metadata" in w for w in plan.warnings)
    assert "Alan Secret Name" not in str(plan.to_dict())


# ---------- images ---------- #

@pytest.mark.parametrize("fmt,name", [("PNG", "a.png"), ("JPEG", "a.jpg"), ("JPEG", "a.jpeg")])
def test_allowed_image_formats(fmt, name):
    plan = route(img_bytes(fmt=fmt), filename=name)
    assert plan.format is Format.IMAGE and plan.routes[0].engine is Engine.OCR


@pytest.mark.parametrize("fmt", ["BMP", "TIFF", "WEBP", "GIF"])
def test_disallowed_image_formats_rejected(fmt):
    with pytest.raises(UnsupportedFormat):
        route(img_bytes(fmt=fmt))


def test_heic_routes_to_ocr_with_warning_when_decoder_missing(monkeypatch):
    monkeypatch.setattr(gate, "_heif_available", lambda: False)
    fake_heic = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00heicmif1" + b"\x00" * 64
    plan = route(fake_heic, filename="photo.heic")
    assert plan.format is Format.IMAGE and plan.routes[0].engine is Engine.OCR
    assert any("pillow-heif" in w for w in plan.warnings)


def test_heic_rejected_when_not_in_allowlist(monkeypatch):
    monkeypatch.setattr(gate, "_heif_available", lambda: False)
    fake_heic = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00heicmif1" + b"\x00" * 64
    with pytest.raises(UnsupportedFormat):
        route(fake_heic, config=GateConfig(allowed_ext=frozenset({"pdf", "png"})))


def test_low_res_image_warns():
    plan = route(img_bytes(size=(300, 200)))
    assert any("Low resolution" in w for w in plan.warnings)


def test_image_detected_without_extension():
    assert route(img_bytes(), filename="upload").format is Format.IMAGE


# ---------- XLSX ---------- #

def test_xlsx_sheets_including_hidden():
    plan = route(make_xlsx([("Summary", "visible"), ("Secrets", "hidden")]), filename="a.xlsx")
    assert plan.format is Format.XLSX
    assert [r.locator for r in plan.routes] == ["sheet:Summary", "sheet:Secrets"]
    assert all(r.engine is Engine.NATIVE for r in plan.routes)
    assert any("Hidden sheets" in w for w in plan.warnings)


def test_xlsx_embedded_pictures_go_to_ocr_and_icons_skipped():
    media = {"xl/media/image1.png": img_bytes((400, 300)), "xl/media/image2.png": img_bytes((16, 16))}
    plan = route(make_xlsx(media=media))
    assert [r.locator for r in plan.ocr_units] == ["media:xl/media/image1.png"]
    assert any("tiny" in w for w in plan.warnings)


def test_docx_rejected_as_unsupported():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", "<w:document/>")
    with pytest.raises(UnsupportedFormat, match="DOCX is not supported"):
        route(buf.getvalue())


def test_unknown_zip_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("hello.txt", "hi")
    with pytest.raises(UnsupportedFormat):
        route(buf.getvalue())


def test_legacy_office_rejected():
    with pytest.raises(UnsupportedFormat):
        route(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100)


# ---------- text / CSV / JSON ---------- #

def test_plain_text_and_log():
    for name in ("n.txt", "app.log"):
        plan = route(b"Hello, my name is Rahul.\nSecond line.", filename=name)
        assert plan.format is Format.TEXT and plan.encoding == "utf-8"


def test_csv_by_extension_and_by_sniffing():
    body = b"name,phone\nRahul,9876543210\nAsha,9123456780\n"
    assert route(body, filename="x.csv").format is Format.CSV
    assert route(body).format is Format.CSV


def test_prose_with_commas_is_not_csv():
    assert route(b"Hello, world.\nAnother line, with a comma, and more words.\n").format is Format.TEXT


def test_json_by_extension_and_by_sniffing():
    body = b'{"name": "Rahul", "phone": "9876543210"}'
    assert route(body, filename="d.json").format is Format.JSON
    assert route(body).format is Format.JSON
    assert route(b'[{"a": 1}, {"a": 2}]').format is Format.JSON


def test_invalid_json_named_json_falls_back_to_text_with_warning():
    plan = route(b'{"name": "Rahul", ', filename="d.json")
    assert plan.format is Format.TEXT and any("not valid JSON" in w for w in plan.warnings)


def test_utf16_bom_and_cp1252_fallback():
    assert route("héllo wörld".encode("utf-16")).encoding == "utf-16"
    plan = route("café au lait".encode("cp1252"))
    assert plan.encoding == "cp1252" and plan.warnings


def test_binary_garbage_rejected():
    with pytest.raises(UnsupportedFormat):
        route(b"\x00\x01\x02\x03" * 100)


# ---------- allowlist and limits (AGENTS.md section 8) ---------- #

def test_default_size_cap_is_25_mb():
    assert GateConfig.from_env({}).max_input_bytes == 25 * 1024 * 1024


def test_env_size_cap(monkeypatch):
    monkeypatch.setenv("REDACT_MAX_FILE_MB", "0.0001")
    with pytest.raises(InputTooLarge):
        route(b"a" * 500, filename="n.txt")


def test_env_size_cap_must_be_a_number(monkeypatch):
    monkeypatch.setenv("REDACT_MAX_FILE_MB", "lots")
    with pytest.raises(GateError):
        route(b"hello", filename="n.txt")


def test_env_allowlist(monkeypatch):
    monkeypatch.setenv("REDACT_ALLOWED_EXT", "pdf,txt")
    assert route(b"hello world", filename="n.txt").format is Format.TEXT
    with pytest.raises(UnsupportedFormat):
        route(img_bytes(), filename="a.png")


def test_unlisted_extension_rejected():
    with pytest.raises(UnsupportedFormat, match="not allowed"):
        route(b"hello", filename="payload.exe")


def test_allowlist_applies_to_sniffed_json_without_extension():
    cfg = GateConfig(allowed_ext=frozenset({"txt", "csv", "pdf"}))
    with pytest.raises(UnsupportedFormat):
        route(b'{"a": 1}', config=cfg)


def test_pdf_bytes_with_txt_extension_rejected():
    with pytest.raises(UnsupportedFormat, match="does not match"):
        route(make_pdf([pdf_text_page]), filename="notes.txt")


def test_png_bytes_with_pdf_extension_rejected():
    with pytest.raises(UnsupportedFormat, match="does not match"):
        route(img_bytes(), filename="scan.pdf")


def test_path_traversal_filename_only_uses_extension():
    plan = route(b"hello", filename="..\\..\\etc\\passwd.txt")
    assert plan.format is Format.TEXT


def test_empty_rejected():
    with pytest.raises(UnsupportedFormat):
        route(b"")


# ---------- privacy (AGENTS.md rule 1) ---------- #

def test_plan_never_contains_document_text():
    dumped = str(route(make_pdf([pdf_text_page, pdf_scan_page])).to_dict())
    assert "Rahul" not in dumped and "9876543210" not in dumped


def test_errors_never_contain_document_text():
    for data, name in [
        (b"Rahul Sharma 9876543210", "x.exe"),
        (b"%PDF-1.7 Rahul Sharma 9876543210", "x.pdf"),
        (b"Rahul Sharma 9876543210", "x.png"),
    ]:
        with pytest.raises(GateError) as exc:
            route(data, filename=name)
        assert "Rahul" not in str(exc.value) and "9876543210" not in str(exc.value)
