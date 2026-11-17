"""RE-DACT visual PII detector module (Face/Photo & QR Codes).

Detects non-text visual personal identifiers using OpenCV:
  * Frontal face detection via built-in Haar Cascade.
  * QR Code detection via built-in cv2.QRCodeDetector.
  * Returns list[Word] tagged as '[PHOTO]' or '[QR]' so they seamlessly integrate with Word-level writers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from redact.entity import Word


def _ensure_bgr_image(image: str | Path | bytes | Image.Image | np.ndarray) -> np.ndarray:
    if isinstance(image, (str, Path)):
        img = cv2.imread(str(image))
        if img is None:
            raise ValueError(f"Failed to load image from path: {image}")
        return img
    if isinstance(image, bytes):
        arr = np.frombuffer(image, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Failed to decode image from bytes.")
        return img
    if isinstance(image, Image.Image):
        rgb = np.array(image.convert("RGB"))
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    if isinstance(image, np.ndarray):
        if image.ndim == 2:
            return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        if image.ndim == 3 and image.shape[2] == 4:
            return cv2.cvtColor(image, cv2.COLOR_RGBA2BGR)
        return image
    raise TypeError(f"Unsupported image type: {type(image)}")


def detect_faces(image: str | Path | bytes | Image.Image | np.ndarray, page: int = 0) -> list[Word]:
    """Detect faces/personal portraits using OpenCV built-in Haar cascade."""
    img = _ensure_bgr_image(image)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)

    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=4,
        minSize=(25, 25),
    )

    face_words: list[Word] = []
    for (x, y, w, h) in faces:
        face_words.append(
            Word(
                text="[PHOTO]",
                x=int(x),
                y=int(y),
                w=int(w),
                h=int(h),
                conf=0.99,
                page=page,
            )
        )
    return face_words


def detect_qrcodes(image: str | Path | bytes | Image.Image | np.ndarray, page: int = 0) -> list[Word]:
    """Detect QR codes using OpenCV QRCodeDetector."""
    img = _ensure_bgr_image(image)
    detector = cv2.QRCodeDetector()
    retval, points = detector.detect(img)

    qr_words: list[Word] = []
    if retval and points is not None:
        pts = points[0]
        x1 = int(round(min(p[0] for p in pts)))
        y1 = int(round(min(p[1] for p in pts)))
        x2 = int(round(max(p[0] for p in pts)))
        y2 = int(round(max(p[1] for p in pts)))
        qr_words.append(
            Word(
                text="[QR]",
                x=x1,
                y=y1,
                w=max(1, x2 - x1),
                h=max(1, y2 - y1),
                conf=0.99,
                page=page,
            )
        )
    return qr_words


def detect_visual_pii(image: str | Path | bytes | Image.Image | np.ndarray, page: int = 0) -> list[Word]:
    """Detect all visual PII (faces and QR codes) on an image."""
    visual_words: list[Word] = []
    visual_words.extend(detect_faces(image, page=page))
    visual_words.extend(detect_qrcodes(image, page=page))
    return visual_words
