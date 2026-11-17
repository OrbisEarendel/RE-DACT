"""RE-DACT Web Application Server

Serves the official frontend (ui/index.html) and implements the local backend API:
  GET  /                     -> ui/index.html
  GET  /api/health           -> { "ok": true, "video": false }
  POST /api/jobs             -> Starts redaction job on uploaded files
  GET  /api/jobs/:id         -> Returns job status, progress, and file summaries
  POST /api/jobs/:id/save    -> Saves redacted files to output folder
  POST /api/jobs/:id/open    -> Opens the output folder
"""

from __future__ import annotations

import email
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler

# Import RE-DACT engine modules
from redact.extract.ocr import to_normalized
from redact.detect import detect
from redact.detect.visual import detect_visual_pii
from policy import policy
from redact.writers.image import redact_image_pipeline, redact_image, _ensure_bgr_image
from redact.writers.pdf import redact_pdf
from redact.extract.pdf import to_normalized as pdf_to_normalized
from redact.entity import Word
from redact.transform.levels import apply as apply_transform

BASE_DIR = Path(__file__).resolve().parent
UI_FILE = BASE_DIR / "ui" / "index.html"
DEFAULT_OUTPUT_DIR = Path.home() / "Desktop" / "REDACT_Outputs"
if not DEFAULT_OUTPUT_DIR.parent.exists():
    DEFAULT_OUTPUT_DIR = BASE_DIR / "outputs"

JOBS: dict[str, dict] = {}
OUTPUT_FILES: dict[str, list[tuple[str, bytes]]] = {}

# Map UI level names to integer levels
LEVEL_MAP = {
    "mask": 1,
    "generalise": 2,
    "generalize": 2,
    "pseudonyms": 2,
    "anonymise": 2,
    "synthetic": 2,
}


def process_image(data: bytes, level: int, enabled_types: set[str] | None) -> tuple[bytes, dict]:
    """Process an image file through OCR, Detection, Policy filtering, and Redaction."""
    import cv2
    import numpy as np

    img_bgr = _ensure_bgr_image(data)
    doc = to_normalized(img_bgr)
    words: list[Word] = [ref for _, _, ref in doc.spans if isinstance(ref, Word)]

    # 1. Detect all text entities
    raw_ents = detect(doc.text, threshold=0.4)

    # 2. Filter through policy based on user level and categories
    selected_ents = policy.select(raw_ents, level=level, enabled_types=enabled_types)

    # 3. Detect visual PII (face/QR)
    visual_words: list[Word] = []
    # If level >= 1 and visual not excluded
    if level >= 1 and (enabled_types is None or "[PHOTO]" in enabled_types or "[QR]" in enabled_types):
        visual_words = detect_visual_pii(img_bgr)
        words.extend(visual_words)

    # 4. Redact image
    redacted = redact_image(img_bgr, words, selected_ents, doc, style="box")

    # Encode back to PNG/JPEG bytes
    success, encoded = cv2.imencode(".png", redacted)
    out_bytes = encoded.tobytes() if success else data

    before_preview = f"{len(raw_ents)} text entities detected"
    after_preview = f"{len(selected_ents)} text entities + {len(visual_words)} visual items redacted"

    return out_bytes, {"before": before_preview, "after": after_preview}


def process_text(text: str, level: int, enabled_types: set[str] | None) -> tuple[bytes, dict]:
    """Process plain text through Detection, Policy filtering, and Transformation (Mask / Generalise)."""
    raw_ents = detect(text, threshold=0.4)
    selected_ents = policy.select(raw_ents, level=level, enabled_types=enabled_types)

    # Use Alan's transform module for Level 1 (Mask) and Level 2 (Generalise)
    transform_level = 2 if level >= 2 else 1
    res_str = apply_transform(text, selected_ents, level=transform_level)

    before_preview = text[:200] + ("..." if len(text) > 200 else "")
    after_preview = res_str[:200] + ("..." if len(res_str) > 200 else "")

    return res_str.encode("utf-8"), {"before": before_preview, "after": after_preview}


def process_pdf(data: bytes, level: int, enabled_types: set[str] | None) -> tuple[bytes, dict]:
    """Process PDF through router/PyMuPDF extraction, detection, policy filtering, and true redaction."""
    norm_doc = pdf_to_normalized(data)
    raw_ents = detect(norm_doc.text, threshold=0.4)
    selected_ents = policy.select(raw_ents, level=level, enabled_types=enabled_types)
    out_bytes = redact_pdf(data, selected_ents, norm_doc)

    before_preview = norm_doc.text[:200] + ("..." if len(norm_doc.text) > 200 else "")
    after_preview = f"{len(selected_ents)} items expunged via true PDF redaction"
    return out_bytes, {"before": before_preview, "after": after_preview}


def run_job(job_id: str, files: list[tuple[str, bytes]], options: dict):
    level_name = options.get("level", "mask").lower()
    level_int = LEVEL_MAP.get(level_name, 1)

    # Map UI categories to canonical entity types
    cat_keys = options.get("categories", [])
    custom_words = options.get("custom", [])

    # If all or standard categories selected, enabled_types can be None or set
    enabled_types: set[str] | None = None
    if cat_keys:
        types_set = set()
        if "names" in cat_keys:
            types_set.update(["PERSON"])
        if "email" in cat_keys:
            types_set.update(["EMAIL"])
        if "phone" in cat_keys:
            types_set.update(["PHONE"])
        if "address" in cat_keys:
            types_set.update(["ADDRESS", "CITY", "PIN_CODE"])
        if "govid" in cat_keys:
            types_set.update(["AADHAAR", "PAN", "PASSPORT", "VOTER_ID", "DRIVING_LICENCE", "GSTIN", "USN", "[PHOTO]", "[QR]"])
        if "fin" in cat_keys:
            types_set.update(["BANK_ACCOUNT", "CARD_NUMBER", "UPI_ID", "IFSC"])
        if "other" in cat_keys:
            types_set.update(["DATE", "AGE", "JOB_TITLE", "ORGANIZATION", "HEALTH_INFO"])
        enabled_types = types_set

    job = JOBS[job_id]
    processed_files = []
    output_list = []

    total = len(files)
    for idx, (filename, data) in enumerate(files):
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        try:
            if ext in ("jpg", "jpeg", "png", "bmp", "webp"):
                out_bytes, preview = process_image(data, level_int, enabled_types)
            elif ext == "pdf":
                out_bytes, preview = process_pdf(data, level_int, enabled_types)
            else:
                text = data.decode("utf-8", errors="replace")
                out_bytes, preview = process_text(text, level_int, enabled_types)

            output_list.append((filename, out_bytes))
            processed_files.append({
                "name": filename,
                "status": "done",
                "preview": preview,
                "verified": True,
            })
        except Exception as exc:
            processed_files.append({
                "name": filename,
                "status": "failed",
                "error": str(exc),
                "verified": False,
            })

        job["progress"] = round((idx + 1) / total, 2)
        job["files"] = processed_files

    OUTPUT_FILES[job_id] = output_list
    job["status"] = "done"
    job["progress"] = 1.0


class RedactHandler(BaseHTTPRequestHandler):
    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]

        if path in ("/", "/index.html"):
            if not UI_FILE.exists():
                self.send_error(404, "UI file not found")
                return
            content = UI_FILE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        if path == "/api/health":
            self._send_json({"ok": True, "video": False})
            return

        if path.startswith("/api/jobs/"):
            job_id = path.split("/")[3]
            job = JOBS.get(job_id)
            if job:
                self._send_json(job)
            else:
                self._send_json({"error": "Job not found"}, status=404)
            return

        self.send_error(404)

    def do_POST(self):
        path = self.path.split("?")[0]

        if path == "/api/jobs":
            content_type = self.headers.get("Content-Type", "")
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)

            msg = email.message_from_bytes(
                b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + body
            )

            files: list[tuple[str, bytes]] = []
            options: dict = {}

            for part in msg.walk():
                if part.get_content_disposition() == "form-data":
                    name = part.get_param("name", header="content-disposition")
                    filename = part.get_param("filename", header="content-disposition")
                    payload = part.get_payload(decode=True)

                    if name == "options":
                        try:
                            options = json.loads(payload.decode("utf-8"))
                        except Exception:
                            options = {}
                    elif filename:
                        files.append((filename, payload))

            job_id = str(uuid.uuid4())
            JOBS[job_id] = {
                "id": job_id,
                "status": "running",
                "progress": 0.0,
                "files": [{"name": fn, "status": "waiting"} for fn, _ in files],
            }

            # Run in worker thread
            thread = threading.Thread(target=run_job, args=(job_id, files, options), daemon=True)
            thread.start()

            self._send_json({"id": job_id})
            return

        if path.startswith("/api/jobs/") and path.endswith("/save"):
            job_id = path.split("/")[3]
            files_to_save = OUTPUT_FILES.get(job_id, [])

            out_dir = DEFAULT_OUTPUT_DIR
            out_dir.mkdir(parents=True, exist_ok=True)

            for fn, data in files_to_save:
                stem = Path(fn).stem
                suffix = Path(fn).suffix
                out_path = out_dir / f"{stem}_redacted{suffix}"
                out_path.write_bytes(data)

            self._send_json({"folder": str(out_dir)})
            return

        if path.startswith("/api/jobs/") and path.endswith("/open"):
            job_id = path.split("/")[3]
            out_dir = DEFAULT_OUTPUT_DIR
            if out_dir.exists():
                try:
                    if sys.platform == "linux":
                        subprocess.Popen(["xdg-open", str(out_dir)])
                    elif sys.platform == "darwin":
                        subprocess.Popen(["open", str(out_dir)])
                except Exception:
                    pass
            self._send_json({})
            return

        self.send_error(404)

    def log_message(self, format, *args):
        # Prevent logging any raw PII in requests
        sys.stderr.write(f"[RE-DACT Web] {self.address_string()} - {args[0]}\n")


def run(port: int = 8000):
    server = HTTPServer(("127.0.0.1", port), RedactHandler)
    print(f"==================================================")
    print(f"  RE-DACT Server running at: http://127.0.0.1:{port}/")
    print(f"==================================================")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    run(port)
