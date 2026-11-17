"""RE-DACT gate: validates an input and routes it, per page / frame / sheet, to
native extraction, OCR, or both. (AGENTS.md section 5: `gate.py` = file
validation + routing.)

Rules this module follows (AGENTS.md sections 2 and 9):
  * In memory only. Nothing is written to disk, nothing is cached.
  * No network. No third-party APIs.
  * No document content in plans, warnings or errors: counts and part names only.
  * Format comes from the bytes (magic numbers), the extension is only checked
    against them. The uploaded filename is never used as a path.
  * Extension allowlist and size cap come from the environment:
    REDACT_ALLOWED_EXT and REDACT_MAX_FILE_MB.
  * Fails closed: pages that might hide pixels a text-layer redaction would not
    remove (scan with hidden OCR layer, outlined text) go to OCR.

Usage:
    plan = route(data, filename="report.pdf")
    plan.native_units   # -> native extract
    plan.ocr_units      # -> OCR (includes units that need both)
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath
from typing import Any, Mapping

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
    JSON = "json"
    IMAGE = "image"
    PDF = "pdf"
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


class GateError(ValueError):
    """Base class. Messages never contain document content."""


class UnsupportedFormat(GateError):
    pass


class EncryptedInput(GateError):
    pass


class InputTooLarge(GateError):
    pass


DEFAULT_ALLOWED_EXT = frozenset(
    {"txt", "log", "csv", "json", "xlsx", "png", "jpg", "jpeg", "heic", "pdf"}
)
_TEXT_EXT = frozenset({"txt", "log", "csv", "json"})
_IMAGE_EXT = frozenset({"png", "jpg", "jpeg", "heic"})

# Extensions that are a valid way to name each detected format.
_FORMAT_EXT: dict[Format, frozenset[str]] = {
    Format.PDF: frozenset({"pdf"}),
    Format.XLSX: frozenset({"xlsx"}),
    Format.IMAGE: _IMAGE_EXT,
    Format.TEXT: frozenset({"txt", "log"}),
    Format.CSV: frozenset({"csv"}),
    Format.JSON: frozenset({"json"}),
}


@dataclass(frozen=True)
class GateConfig:
    # From .env (AGENTS.md section 8)
    max_input_bytes: int = 25 * 1024 * 1024        # REDACT_MAX_FILE_MB
    allowed_ext: frozenset[str] = DEFAULT_ALLOWED_EXT  # REDACT_ALLOWED_EXT
    # PDF page classification
    min_text_chars: int = 25            # alphanumeric chars for a page to count as "has text"
    scan_coverage: float = 0.80         # image area / page area => page is a picture
    sparse_scan_coverage: float = 0.30  # same, for pages with almost no text
    region_min_coverage: float = 0.03   # embedded picture worth OCRing on a text page
    max_garbage_ratio: float = 0.20     # unreadable glyphs in the text layer => distrust it
    hidden_text_ratio: float = 0.50     # share of invisible text that marks a fake OCR layer
    outlined_text_paths: int = 200      # vector paths on a textless page => maybe outlined text
    ocr_dpi: int = 300
    # Pictures embedded in XLSX
    min_embedded_px: int = 40           # skip icons smaller than this on both sides
    # Safety limits
    max_uncompressed_bytes: int = 300 * 1024 * 1024
    max_units: int = 200                # pages / frames / sheets
    max_pixels: int = 100_000_000
    low_res_px: int = 800               # warn when an image's long side is below this

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "GateConfig":
        env = os.environ if env is None else env
        kw: dict[str, Any] = {}
        mb = env.get("REDACT_MAX_FILE_MB", "").strip()
        if mb:
            try:
                value = float(mb)
            except ValueError as exc:
                raise GateError("REDACT_MAX_FILE_MB must be a number.") from exc
            if value <= 0:
                raise GateError("REDACT_MAX_FILE_MB must be positive.")
            kw["max_input_bytes"] = int(value * 1024 * 1024)
        raw = env.get("REDACT_ALLOWED_EXT", "").strip()
        if raw:
            exts = frozenset(e.strip().lower().lstrip(".") for e in raw.split(",") if e.strip())
            if not exts:
                raise GateError("REDACT_ALLOWED_EXT is empty.")
            kw["allowed_ext"] = exts
        return cls(**kw)


@dataclass(frozen=True)
class Route:
    unit: int                    # sequential index within the plan
    locator: str                 # "page:3", "frame:0", "sheet:Summary", "media:xl/media/image1.png", "text", "table", "json"
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

def _ext(filename: str | None) -> str:
    """Extension only. The uploaded name is never used as a path."""
    if not filename:
        return ""
    return PurePosixPath(filename.replace("\\", "/")).suffix.lower().lstrip(".")


def _safe_ext(ext: str) -> str:
    return re.sub(r"[^a-z0-9]", "", ext)[:10]


def _require(ext: str, fmt: Format, cfg: GateConfig) -> None:
    """Detected format must be allowed, and the extension (if any) must fit it."""
    if ext and ext not in _FORMAT_EXT[fmt]:
        raise UnsupportedFormat(
            f"File content looks like {fmt.value} but the extension '.{_safe_ext(ext)}' does not match."
        )
    if not (_FORMAT_EXT[fmt] & cfg.allowed_ext):
        raise UnsupportedFormat(f"{fmt.value} input is not allowed by configuration.")


def route(data: bytes, filename: str | None = None, config: GateConfig | None = None) -> RoutePlan:
    """Validate one input and build its routing plan.

    `filename` is only checked for its extension. `config` defaults to values
    read from the environment (REDACT_MAX_FILE_MB, REDACT_ALLOWED_EXT).
    """
    cfg = config or GateConfig.from_env()
    ext = _ext(filename)
    if ext and ext not in cfg.allowed_ext:
        raise UnsupportedFormat(
            f"File type '.{_safe_ext(ext)}' is not allowed. Allowed: {', '.join(sorted(cfg.allowed_ext))}."
        )
    if not data:
        raise UnsupportedFormat("Input is empty.")
    if len(data) > cfg.max_input_bytes:
        raise InputTooLarge(
            f"Input is {len(data) / 1048576:.1f} MB; limit is {cfg.max_input_bytes / 1048576:.0f} MB."
        )

    head = data[:1024]
    if head.startswith(b"%PDF-") or (b"%PDF-" in head and ext not in _TEXT_EXT):
        _require(ext, Format.PDF, cfg)
        return _route_pdf(data, cfg)
    if head.startswith(b"PK\x03\x04"):
        return _route_zip(data, ext, cfg)
    if head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        raise UnsupportedFormat(
            "Legacy Office or password-protected Office file is not supported."
        )
    if _is_heic(head) or _looks_like_image(head):
        return _route_image(data, ext, cfg, heic=_is_heic(head))
    return _route_text(data, ext, cfg)


def route_path(path: str, config: GateConfig | None = None) -> RoutePlan:
    """Convenience wrapper for the CLI and tests. Reads into memory; writes nothing."""
    with open(path, "rb") as fh:
        data = fh.read()
    return route(data, filename=path, config=config)


# --------------------------------------------------------------------------- #
# Text / CSV / JSON
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


def _valid_json(text: str) -> bool:
    stripped = text.lstrip()
    if not stripped or stripped[0] not in "{[":
        return False
    try:
        json.loads(text)
    except (ValueError, RecursionError):
        return False
    return True


def _looks_like_csv(text: str) -> bool:
    lines = [ln for ln in text.splitlines()[:20] if ln.strip()]
    if len(lines) < 2:
        return False
    for delim in (",", ";", "\t", "|"):
        counts = [len(row) - 1 for row in csv.reader(lines, delimiter=delim)]
        if counts and counts[0] >= 1 and len(set(counts)) == 1:
            return True
    return False


def _route_text(data: bytes, ext: str, cfg: GateConfig) -> RoutePlan:
    text, enc, warnings = _decode_text(data)

    if ext == "json":
        if _valid_json(text):
            fmt = Format.JSON
        else:
            fmt = Format.TEXT
            warnings.append("File is named .json but is not valid JSON; treated as plain text.")
    elif ext == "csv":
        fmt = Format.CSV
    elif ext in ("txt", "log"):
        fmt = Format.TEXT
    elif _valid_json(text):
        fmt = Format.JSON
    elif _looks_like_csv(text):
        fmt = Format.CSV
    else:
        fmt = Format.TEXT

    # Text content must carry a text-family extension (or none). Text named .png/.pdf/.xlsx is a mismatch.
    if ext and ext not in _TEXT_EXT:
        raise UnsupportedFormat(
            f"File content looks like text but the extension '.{_safe_ext(ext)}' does not match."
        )
    if not ext:
        _require("", fmt, cfg)

    locator = {Format.TEXT: "text", Format.CSV: "table", Format.JSON: "json"}[fmt]
    r = Route(0, locator, Kind.TEXT, Engine.NATIVE, f"{fmt.value} input", stats={"chars": len(text)})
    return RoutePlan(fmt, [r], warnings, encoding=enc, ocr_dpi=cfg.ocr_dpi)


# --------------------------------------------------------------------------- #
# Images (PNG, JPEG, HEIC)
# --------------------------------------------------------------------------- #

_PIL_FORMAT_EXT = {
    "PNG": frozenset({"png"}),
    "JPEG": frozenset({"jpg", "jpeg"}),
    "MPO": frozenset({"jpg", "jpeg"}),
    "HEIF": frozenset({"heic"}),
}
_HEIC_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"}


def _is_heic(head: bytes) -> bool:
    return len(head) >= 12 and head[4:8] == b"ftyp" and head[8:12] in _HEIC_BRANDS


def _looks_like_image(head: bytes) -> bool:
    """Magic numbers for formats Pillow reads. Disallowed ones are rejected later, with a clear message."""
    return (
        head.startswith(b"\x89PNG\r\n\x1a\n")
        or head.startswith(b"\xff\xd8\xff")
        or head.startswith((b"II*\x00", b"MM\x00*"))
        or head.startswith(b"BM")
        or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")
        or head.startswith((b"GIF87a", b"GIF89a"))
    )


def _heif_available() -> bool:
    """HEIC decoding needs pillow-heif (an optional dependency the team has not added yet)."""
    try:
        import pillow_heif  # type: ignore

        pillow_heif.register_heif_opener()
        return True
    except Exception:
        return False


def _image_info(data: bytes, cfg: GateConfig) -> dict[str, Any]:
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
    except GateError:
        raise
    except Image.DecompressionBombError as exc:
        raise InputTooLarge("Image is too large to process safely.") from exc
    except Exception as exc:
        raise UnsupportedFormat("Could not read image file.") from exc


def _route_image(data: bytes, ext: str, cfg: GateConfig, heic: bool) -> RoutePlan:
    if ext and ext not in _IMAGE_EXT:
        raise UnsupportedFormat(
            f"File content looks like an image but the extension '.{_safe_ext(ext)}' does not match."
        )
    warnings: list[str] = []

    if heic and not _heif_available():
        if not ({"heic"} & cfg.allowed_ext):
            raise UnsupportedFormat("heic input is not allowed by configuration.")
        warnings.append("HEIC image: pillow-heif is not installed, so it cannot be decoded for OCR yet.")
        route0 = Route(0, "frame:0", Kind.IMAGE, Engine.OCR, "HEIC image file")
        return RoutePlan(Format.IMAGE, [route0], warnings, ocr_dpi=cfg.ocr_dpi)

    info = _image_info(data, cfg)
    allowed_for_fmt = _PIL_FORMAT_EXT.get(info["format"])
    if not allowed_for_fmt:
        raise UnsupportedFormat(f"Image format {info['format']} is not allowed (PNG, JPEG, HEIC only).")
    if not (allowed_for_fmt & cfg.allowed_ext):
        raise UnsupportedFormat(f"{info['format']} input is not allowed by configuration.")

    frames = info["frames"]
    if frames > cfg.max_units:
        raise InputTooLarge(f"Image has {frames} frames; limit is {cfg.max_units}.")
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
            covered[y][x0:x1] = b"\x01" * (x1 - x0)
    return sum(sum(row) for row in covered) / (grid * grid)


def _garbage_ratio(text: str) -> float:
    visible = [c for c in text if not c.isspace()]
    if not visible:
        return 0.0
    bad = sum(1 for c in visible if c == "�" or unicodedata.category(c) in ("Co", "Cn", "Cc"))
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


def _classify_pdf_page(page: Any, index: int, cfg: GateConfig) -> Route:
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


def _route_pdf(data: bytes, cfg: GateConfig) -> RoutePlan:
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
        meta_keys = [k for k, v in (doc.metadata or {}).items()
                     if v and k in ("title", "author", "subject", "keywords", "creator")]
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
# XLSX (zip container)
# --------------------------------------------------------------------------- #

_RASTER_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp"}
_VECTOR_EXT = {".emf", ".wmf", ".svg"}
_XL_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _route_zip(data: bytes, ext: str, cfg: GateConfig) -> RoutePlan:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UnsupportedFormat("Corrupt zip container.") from exc
    with zf:
        infos = zf.infolist()
        if sum(i.file_size for i in infos) > cfg.max_uncompressed_bytes:
            raise InputTooLarge("Archive expands beyond the safe size limit.")
        names = {i.filename for i in infos}
        if "xl/workbook.xml" in names:
            _require(ext, Format.XLSX, cfg)
            return _route_xlsx(zf, names, cfg)
        if "word/document.xml" in names:
            raise UnsupportedFormat("DOCX is not supported. Allowed: " + ", ".join(sorted(cfg.allowed_ext)) + ".")
    raise UnsupportedFormat("Zip file is not an XLSX workbook.")


def _embedded_image_routes(zf: zipfile.ZipFile, names: set[str], prefix: str,
                           start_unit: int, cfg: GateConfig) -> tuple[list[Route], list[str]]:
    routes: list[Route] = []
    warnings: list[str] = []
    skipped = 0
    unit = start_unit
    for name in sorted(n for n in names if n.startswith(prefix)):
        suffix = PurePosixPath(name).suffix.lower()
        if suffix in _VECTOR_EXT:
            routes.append(Route(unit, f"media:{name}", Kind.IMAGE, Engine.OCR,
                                "vector picture; rasterize before OCR", (), {"rasterizable": False}))
            warnings.append(f"{name}: vector picture ({suffix}) may contain text; needs rasterizing.")
            unit += 1
            continue
        if suffix not in _RASTER_EXT:
            continue
        try:
            info = _image_info(zf.read(name), cfg)
        except GateError:
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


def _route_xlsx(zf: zipfile.ZipFile, names: set[str], cfg: GateConfig) -> RoutePlan:
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
# CLI:  python -m redact some_file.pdf   (see redact/__main__.py)
# --------------------------------------------------------------------------- #

def main(argv: list[str]) -> None:
    """Print the routing plan for one file as JSON. Exits with a short message on error."""
    import sys

    if len(argv) != 1:
        sys.exit("usage: python -m redact <file>")
    try:
        print(json.dumps(route_path(argv[0]).to_dict(), indent=2))
    except FileNotFoundError:
        sys.exit("gate: file not found")
    except GateError as exc:
        sys.exit(f"gate: {exc}")
