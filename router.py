"""RE-DACT router: decides, per page / frame / sheet, whether content goes to
native extraction, OCR, or both.

Design rules (from the pipeline diagram and the no-storage requirement):
  * Works on in-memory bytes only. Nothing is written to disk, nothing cached.
  * Never puts document content in its output. Reasons and warnings contain
    counts and part names only, so a plan is safe to log.
  * Sniffs the format from the bytes, not the file extension.
  * Routes PDF pages individually, because one PDF can mix text pages and scans.
  * Fails closed: if a page might hide pixels that a text-layer redaction would
    not remove (scan with a hidden OCR layer, outlined text), it goes to OCR.

Usage:
    plan = route(data, filename="report.pdf")
    plan.native_units   # -> units for native extract
    plan.ocr_units      # -> units for OCR (incl. units that need both)
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath
from typing import Any

try:  # PyMuPDF >= 1.24 prefers the `pymupdf` name
    import pymupdf
except ImportError:  # pragma: no cover
    import fitz as pymupdf  # type: ignore

from PIL import Image


# --------------------------------------------------------------------------- #
# Types
# --------------------------------------------------------------------------- #

class Format(str, Enum):
    TEXT = "text"
    CSV = "csv"
    IMAGE = "image"
    PDF = "pdf"
    DOCX = "docx"
    XLSX = "xlsx"


class Kind(str, Enum):
    TEXT = "text"    # reliable native text
    SCAN = "scan"    # page is (effectively) a picture of text
    IMAGE = "image"  # image file, frame, or embedded picture
    MIXED = "mixed"  # native text plus pictures that may contain text
    BLANK = "blank"  # nothing to detect


class Engine(str, Enum):
    NATIVE = "native"
    OCR = "ocr"
    BOTH = "both"
    NONE = "none"


class RouterError(ValueError):
    """Base class. Safe to show to the user."""


class UnsupportedFormat(RouterError):
    pass


class EncryptedInput(RouterError):
    pass


class InputTooLarge(RouterError):
    pass


@dataclass(frozen=True)
class RouterConfig:
    # PDF page classification
    min_text_chars: int = 25            # alphanumeric chars for a page to count as "has text"
    scan_coverage: float = 0.80         # image area / page area => page is a picture
    sparse_scan_coverage: float = 0.30  # same, for pages with almost no text
    region_min_coverage: float = 0.03   # embedded picture worth OCRing on a text page
    max_garbage_ratio: float = 0.20     # unreadable glyphs in the text layer => distrust it
    hidden_text_ratio: float = 0.50     # share of invisible text that marks a fake OCR layer
    outlined_text_paths: int = 200      # vector paths on a textless page => maybe outlined text
    ocr_dpi: int = 300
    # Embedded pictures in DOCX / XLSX
    min_embedded_px: int = 40           # skip icons smaller than this on both sides
    # Limits
    max_input_bytes: int = 200 * 1024 * 1024
    max_uncompressed_bytes: int = 600 * 1024 * 1024
    max_units: int = 2000
    max_pixels: int = 200_000_000
    low_res_px: int = 800               # warn when an image's long side is below this


@dataclass(frozen=True)
class Route:
    unit: int                    # sequential index within the plan
    locator: str                 # "page:3", "frame:0", "sheet:Summary", "media:word/media/image1.png", "body", "text"
    kind: Kind
    engine: Engine
    reason: str
    ocr_regions: tuple[tuple[float, float, float, float], ...] = ()  # PDF points; empty with OCR = whole unit
    stats: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit": self.unit,
            "locator": self.locator,
            "kind": self.kind.value,
            "engine": self.engine.value,
            "reason": self.reason,
            "ocr_regions": [list(r) for r in self.ocr_regions],
            "stats": self.stats,
        }


@dataclass
class RoutePlan:
    format: Format
    routes: list[Route]
    warnings: list[str] = field(default_factory=list)
    encoding: str | None = None
    ocr_dpi: int = 300

    @property
    def native_units(self) -> list[Route]:
        return [r for r in self.routes if r.engine in (Engine.NATIVE, Engine.BOTH)]

    @property
    def ocr_units(self) -> list[Route]:
        return [r for r in self.routes if r.engine in (Engine.OCR, Engine.BOTH)]

    @property
    def needs_ocr(self) -> bool:
        return bool(self.ocr_units)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format.value,
            "encoding": self.encoding,
            "ocr_dpi": self.ocr_dpi,
            "warnings": self.warnings,
            "routes": [r.to_dict() for r in self.routes],
        }


# --------------------------------------------------------------------------- #
# Entry points
# --------------------------------------------------------------------------- #

def route(data: bytes, filename: str | None = None, config: RouterConfig | None = None) -> RoutePlan:
    """Build a routing plan for one input. `filename` is only a hint (CSV vs text)."""
    cfg = config or RouterConfig()
    if not data:
        raise UnsupportedFormat("Input is empty.")
    if len(data) > cfg.max_input_bytes:
        raise InputTooLarge(f"Input is {len(data)} bytes; limit is {cfg.max_input_bytes}.")

    head = data[:1024]
    if b"%PDF-" in head:
        return _route_pdf(data, cfg)
    if head.startswith(b"PK\x03\x04"):
        return _route_zip(data, cfg)
    if head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        raise UnsupportedFormat(
            "Legacy Office (.doc/.xls) or password-protected Office file. "
            "Save as .docx/.xlsx without a password and retry."
        )
    if _looks_like_image(head):
        return _route_image(data, cfg)
    return _route_text(data, filename, cfg)


def route_path(path: str, config: RouterConfig | None = None) -> RoutePlan:
    """Convenience wrapper. Reads the file into memory; writes nothing."""
    with open(path, "rb") as fh:
        data = fh.read()
    return route(data, filename=path, config=config)


# --------------------------------------------------------------------------- #
# Text / CSV
# --------------------------------------------------------------------------- #

_BOMS = (
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe\x00\x00", "utf-32"),
    (b"\x00\x00\xfe\xff", "utf-32"),
    (b"\xff\xfe", "utf-16"),
    (b"\xfe\xff", "utf-16"),
)


def _decode_text(data: bytes) -> tuple[str, str, list[str]]:
    warnings: list[str] = []
    for bom, enc in _BOMS:
        if data.startswith(bom):
            return data.decode(enc), enc, warnings
    if b"\x00" in data[:8192]:
        raise UnsupportedFormat("Binary file with no recognised format.")
    try:
        return data.decode("utf-8"), "utf-8", warnings
    except UnicodeDecodeError:
        warnings.append("Not valid UTF-8; decoded as cp1252. Offsets refer to the decoded text.")
        return data.decode("cp1252", errors="replace"), "cp1252", warnings


def _looks_like_csv(text: str, filename: str | None) -> bool:
    ext = (PurePosixPath(filename.replace("\\", "/")).suffix.lower() if filename else "")
    if ext in (".csv", ".tsv"):
        return True
    lines = [ln for ln in text.splitlines()[:20] if ln.strip()]
    if len(lines) < 2:
        return False
    for delim in (",", ";", "\t", "|"):
        counts = []
        for row in csv.reader(lines, delimiter=delim):
            counts.append(len(row) - 1)
        if counts and counts[0] >= 1 and len(set(counts)) == 1:
            return True
    return False


def _route_text(data: bytes, filename: str | None, cfg: RouterConfig) -> RoutePlan:
    text, enc, warnings = _decode_text(data)
    fmt = Format.CSV if _looks_like_csv(text, filename) else Format.TEXT
    r = Route(0, "text", Kind.TEXT, Engine.NATIVE, "plain text input",
              stats={"chars": len(text)})
    return RoutePlan(fmt, [r], warnings, encoding=enc, ocr_dpi=cfg.ocr_dpi)


# --------------------------------------------------------------------------- #
# Images
# --------------------------------------------------------------------------- #

_IMAGE_FORMATS = {"PNG", "JPEG", "TIFF", "BMP", "WEBP", "GIF", "MPO"}


def _looks_like_image(head: bytes) -> bool:
    return (
        head.startswith(b"\x89PNG\r\n\x1a\n")
        or head.startswith(b"\xff\xd8\xff")
        or head.startswith((b"II*\x00", b"MM\x00*"))
        or head.startswith(b"BM")
        or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")
        or head.startswith((b"GIF87a", b"GIF89a"))
    )


def _image_info(data: bytes, cfg: RouterConfig) -> dict[str, Any]:
    try:
        with Image.open(io.BytesIO(data)) as im:
            fmt = im.format
            w, h = im.size
            if w * h > cfg.max_pixels:
                raise InputTooLarge(f"Image is {w}x{h}px; limit is {cfg.max_pixels} pixels.")
            dpi = im.info.get("dpi")
            return {
                "format": fmt,
                "width": w,
                "height": h,
                "frames": getattr(im, "n_frames", 1),
                "dpi": tuple(round(float(d)) for d in dpi) if dpi else None,
            }
    except InputTooLarge:
        raise
    except Image.DecompressionBombError as exc:
        raise InputTooLarge("Image is too large to process safely.") from exc
    except Exception as exc:
        raise UnsupportedFormat("Could not read image file.") from exc


def _route_image(data: bytes, cfg: RouterConfig) -> RoutePlan:
    info = _image_info(data, cfg)
    if info["format"] not in _IMAGE_FORMATS:
        raise UnsupportedFormat(f"Image format {info['format']} is not supported.")
    frames = info["frames"]
    if frames > cfg.max_units:
        raise InputTooLarge(f"Image has {frames} frames; limit is {cfg.max_units}.")

    warnings: list[str] = []
    if max(info["width"], info["height"]) < cfg.low_res_px:
        warnings.append(
            f"Low resolution ({info['width']}x{info['height']}px); OCR may miss small text. Consider upscaling."
        )
    routes = [
        Route(i, f"frame:{i}", Kind.IMAGE, Engine.OCR, "image file",
              stats={k: info[k] for k in ("width", "height", "dpi")})
        for i in range(frames)
    ]
    return RoutePlan(Format.IMAGE, routes, warnings, ocr_dpi=cfg.ocr_dpi)


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #

def _union_coverage(rects: list[Any], page_rect: Any, grid: int = 64) -> float:
    """Fraction of the page covered by the union of rects (coarse grid, no numpy)."""
    pw, ph = page_rect.width, page_rect.height
    if pw <= 0 or ph <= 0 or not rects:
        return 0.0
    covered = [bytearray(grid) for _ in range(grid)]
    for r in rects:
        r = r & page_rect
        if r.is_empty:
            continue
        x0 = int((r.x0 - page_rect.x0) / pw * grid)
        x1 = min(grid, int((r.x1 - page_rect.x0) / pw * grid + 0.999))
        y0 = int((r.y0 - page_rect.y0) / ph * grid)
        y1 = min(grid, int((r.y1 - page_rect.y0) / ph * grid + 0.999))
        for y in range(y0, y1):
            row = covered[y]
            row[x0:x1] = b"\x01" * (x1 - x0)
    return sum(sum(row) for row in covered) / (grid * grid)


def _garbage_ratio(text: str) -> float:
    visible = [c for c in text if not c.isspace()]
    if not visible:
        return 0.0
    bad = 0
    for c in visible:
        cat = unicodedata.category(c)
        if c == "�" or cat in ("Co", "Cn", "Cc"):
            bad += 1
    return bad / len(visible)


def _hidden_text_ratio(page: Any) -> float:
    """Share of glyphs drawn invisibly (render mode 3 / zero opacity): a fake OCR layer."""
    try:
        spans = page.get_texttrace()
    except Exception:
        return 0.0
    total = hidden = 0
    for sp in spans:
        n = len(sp.get("chars", ()))
        total += n
        if sp.get("type") == 3 or sp.get("opacity", 1) == 0:
            hidden += n
    return hidden / total if total else 0.0


def _classify_pdf_page(page: Any, index: int, cfg: RouterConfig) -> Route:
    text = page.get_text("text")
    chars = sum(1 for c in text if c.isalnum())
    garbage = _garbage_ratio(text)

    images = page.get_image_info()
    img_rects = [pymupdf.Rect(i["bbox"]) for i in images if i.get("bbox")]
    page_area = max(page.rect.width * page.rect.height, 1.0)
    cov = _union_coverage(img_rects, page.rect)
    large = tuple(
        tuple(round(v, 1) for v in (r & page.rect))
        for r in img_rects
        if not (r & page.rect).is_empty
        and (r & page.rect).width * (r & page.rect).height / page_area >= cfg.region_min_coverage
    )

    n_annots = sum(1 for _ in (page.annots() or []))
    n_widgets = sum(1 for _ in (page.widgets() or []))
    stats: dict[str, Any] = {
        "text_chars": chars,
        "image_coverage": round(cov, 2),
        "images": len(images),
        "garbage_ratio": round(garbage, 2),
        "rotation": page.rotation,
    }
    if n_annots:
        stats["annotations"] = n_annots
    if n_widgets:
        stats["form_fields"] = n_widgets

    whole_page = ((round(page.rect.x0, 1), round(page.rect.y0, 1),
                   round(page.rect.x1, 1), round(page.rect.y1, 1)),)
    loc = f"page:{index}"

    # 1. Page is basically one picture.
    if cov >= cfg.scan_coverage:
        hidden = _hidden_text_ratio(page) if chars else 0.0
        stats["hidden_text_ratio"] = round(hidden, 2)
        if chars < cfg.min_text_chars:
            return Route(index, loc, Kind.SCAN, Engine.OCR, "full-page image, no text layer", (), stats)
        if hidden >= cfg.hidden_text_ratio:
            return Route(index, loc, Kind.SCAN, Engine.OCR,
                         "full-page image with hidden OCR layer; pixels must be redacted, not just the layer",
                         (), stats)
        return Route(index, loc, Kind.MIXED, Engine.BOTH,
                     "visible text over a full-page image", whole_page, stats)

    # 2. Text layer exists but is unreadable (bad font encoding).
    if chars and garbage > cfg.max_garbage_ratio:
        return Route(index, loc, Kind.SCAN, Engine.OCR, "text layer unreadable (font encoding)", (), stats)

    # 3. Good text layer.
    if chars >= cfg.min_text_chars:
        if large:
            return Route(index, loc, Kind.MIXED, Engine.BOTH,
                         f"text plus {len(large)} embedded picture(s)", large, stats)
        return Route(index, loc, Kind.TEXT, Engine.NATIVE, "text layer", (), stats)

    # 4. Little or no text: look for content that is not text-layer.
    if cov >= cfg.sparse_scan_coverage:
        return Route(index, loc, Kind.SCAN, Engine.OCR, "mostly image, little text", (), stats)
    if images:
        engine = Engine.BOTH if chars else Engine.OCR
        return Route(index, loc, Kind.IMAGE, engine, "small embedded picture(s)", large or whole_page, stats)
    n_paths = len(page.get_drawings())
    stats["vector_paths"] = n_paths
    if n_paths >= cfg.outlined_text_paths:
        return Route(index, loc, Kind.SCAN, Engine.OCR,
                     "no text but many vector paths; text may be outlined", (), stats)
    if chars:
        return Route(index, loc, Kind.TEXT, Engine.NATIVE, "sparse text layer", (), stats)
    return Route(index, loc, Kind.BLANK, Engine.NONE, "empty page", (), stats)


def _route_pdf(data: bytes, cfg: RouterConfig) -> RoutePlan:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise UnsupportedFormat("Could not read PDF (corrupt or not a PDF).") from exc
    try:
        if doc.needs_pass:
            raise EncryptedInput("PDF is password-protected. Provide an unlocked copy.")
        if doc.page_count > cfg.max_units:
            raise InputTooLarge(f"PDF has {doc.page_count} pages; limit is {cfg.max_units}.")

        routes = [_classify_pdf_page(doc[i], i, cfg) for i in range(doc.page_count)]
        warnings: list[str] = []

        if doc.embfile_count():
            warnings.append(f"{doc.embfile_count()} embedded file(s) are not processed.")
        meta_keys = [k for k, v in (doc.metadata or {}).items() if v and k in ("title", "author", "subject", "keywords", "creator")]
        if meta_keys:
            warnings.append("PDF metadata present (" + ", ".join(meta_keys) + "); strip it in the output.")
        if any("annotations" in r.stats or "form_fields" in r.stats for r in routes):
            warnings.append("Annotations or form fields present; they are not in the page text layer.")
        if all(r.kind is Kind.BLANK for r in routes):
            warnings.append("No content detected on any page.")
        return RoutePlan(Format.PDF, routes, warnings, ocr_dpi=cfg.ocr_dpi)
    finally:
        doc.close()


# --------------------------------------------------------------------------- #
# DOCX / XLSX (zip containers)
# --------------------------------------------------------------------------- #

_RASTER_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp"}
_VECTOR_EXT = {".emf", ".wmf", ".svg"}
_XL_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _route_zip(data: bytes, cfg: RouterConfig) -> RoutePlan:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UnsupportedFormat("Corrupt zip container.") from exc
    with zf:
        infos = zf.infolist()
        if sum(i.file_size for i in infos) > cfg.max_uncompressed_bytes:
            raise InputTooLarge("Archive expands beyond the safe size limit.")
        names = {i.filename for i in infos}
        if "word/document.xml" in names:
            return _route_docx(zf, names, cfg)
        if "xl/workbook.xml" in names:
            return _route_xlsx(zf, names, cfg)
    raise UnsupportedFormat("Zip file is not a DOCX or XLSX.")


def _embedded_image_routes(zf: zipfile.ZipFile, names: set[str], prefix: str,
                           start_unit: int, cfg: RouterConfig) -> tuple[list[Route], list[str]]:
    routes: list[Route] = []
    warnings: list[str] = []
    skipped = 0
    unit = start_unit
    for name in sorted(n for n in names if n.startswith(prefix)):
        ext = PurePosixPath(name).suffix.lower()
        if ext in _VECTOR_EXT:
            routes.append(Route(unit, f"media:{name}", Kind.IMAGE, Engine.OCR,
                                "vector picture; rasterize before OCR", (), {"rasterizable": False}))
            warnings.append(f"{name}: vector picture ({ext}) may contain text; needs rasterizing.")
            unit += 1
            continue
        if ext not in _RASTER_EXT:
            continue
        try:
            info = _image_info(zf.read(name), cfg)
        except RouterError:
            warnings.append(f"{name}: unreadable picture, check manually.")
            routes.append(Route(unit, f"media:{name}", Kind.IMAGE, Engine.OCR,
                                "unreadable picture", (), {"rasterizable": False}))
            unit += 1
            continue
        if info["width"] < cfg.min_embedded_px and info["height"] < cfg.min_embedded_px:
            skipped += 1
            continue
        routes.append(Route(unit, f"media:{name}", Kind.IMAGE, Engine.OCR, "embedded picture",
                            (), {"width": info["width"], "height": info["height"]}))
        unit += 1
    if skipped:
        warnings.append(f"{skipped} tiny embedded picture(s) skipped (icons/bullets).")
    return routes, warnings


def _route_docx(zf: zipfile.ZipFile, names: set[str], cfg: RouterConfig) -> RoutePlan:
    warnings: list[str] = []
    aux = sorted(n for n in names if re.fullmatch(
        r"word/(header|footer|footnotes|endnotes|comments)\d*\.xml", n))
    body_xml = zf.read("word/document.xml")
    stats: dict[str, Any] = {"aux_parts": aux}
    if b"<w:del " in body_xml or b"<w:del>" in body_xml:
        warnings.append("Tracked deletions present; deleted text may still hold PII.")
    if b"<w:ins " in body_xml:
        warnings.append("Tracked insertions present; accept or reject changes for a clean output.")
    if "word/comments.xml" in names:
        warnings.append("Comments present; they are separate from body text.")

    routes = [Route(0, "body", Kind.TEXT, Engine.NATIVE, "DOCX text, tables, headers and footers", (), stats)]
    imgs, w = _embedded_image_routes(zf, names, "word/media/", 1, cfg)
    routes += imgs
    warnings += w
    if len(routes) > cfg.max_units:
        raise InputTooLarge("Too many units in document.")
    return RoutePlan(Format.DOCX, routes, warnings, ocr_dpi=cfg.ocr_dpi)


def _route_xlsx(zf: zipfile.ZipFile, names: set[str], cfg: RouterConfig) -> RoutePlan:
    warnings: list[str] = []
    routes: list[Route] = []
    try:
        root = ET.fromstring(zf.read("xl/workbook.xml"))
        sheets = [(s.get("name", f"sheet{i + 1}"), s.get("state", "visible"))
                  for i, s in enumerate(root.iter(f"{_XL_MAIN}sheet"))]
    except ET.ParseError as exc:
        raise UnsupportedFormat("Corrupt workbook.") from exc
    if not sheets:
        raise UnsupportedFormat("Workbook has no sheets.")
    if len(sheets) > cfg.max_units:
        raise InputTooLarge(f"Workbook has {len(sheets)} sheets; limit is {cfg.max_units}.")

    for i, (name, state) in enumerate(sheets):
        reason = "sheet cells" if state == "visible" else f"{state} sheet cells (still processed)"
        routes.append(Route(i, f"sheet:{name}", Kind.TEXT, Engine.NATIVE, reason, (), {"state": state}))
    if any(s != "visible" for _, s in sheets):
        warnings.append("Hidden sheets present; they are redacted like visible ones.")
    if any(n.startswith("xl/charts/") for n in names):
        warnings.append("Charts present; chart titles and labels are not in cell data.")

    imgs, w = _embedded_image_routes(zf, names, "xl/media/", len(routes), cfg)
    routes += imgs
    warnings += w
    return RoutePlan(Format.XLSX, routes, warnings, ocr_dpi=cfg.ocr_dpi)


# --------------------------------------------------------------------------- #
# CLI:  python -m redact.router some_file.pdf
# --------------------------------------------------------------------------- #

if __name__ == "__main__":  # pragma: no cover
    import json
    import sys

    if len(sys.argv) != 2:
        sys.exit("usage: python -m redact.router <file>")
    try:
        print(json.dumps(route_path(sys.argv[1]).to_dict(), indent=2))
    except RouterError as exc:
        sys.exit(f"router: {exc}")
