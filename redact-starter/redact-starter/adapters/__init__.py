"""Adapter registry. Owner: P2.

To add a format: write a class following core/interfaces.py and add it to ADAPTERS.
"""
import os

from adapters.image_adapter import ImageAdapter
from adapters.text_adapter import TextAdapter

ADAPTERS = [TextAdapter(), ImageAdapter()]  # P2: add PdfAdapter


def get_adapter(path: str):
    ext = os.path.splitext(path)[1].lower()
    for a in ADAPTERS:
        if ext in a.extensions:
            return a
    raise ValueError(f"Unsupported file type: {ext}")
