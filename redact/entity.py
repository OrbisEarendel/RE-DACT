"""Shared types. Copied verbatim from AGENTS.md section 5.
DO NOT CHANGE WITHOUT TEAM AGREEMENT. If the repo already has this file, keep the repo's copy.
"""
from dataclasses import dataclass, field


@dataclass
class Entity:
    type: str            # "person", "phone number", "AADHAAR", ...
    start: int           # char offset into NormalizedDoc.text
    end: int
    score: float = 1.0   # 1.0 for regex+checksum, model confidence for NER
    source: str = ""     # "regex" | "gliner" | "custom"


@dataclass
class Word:              # one OCR word
    text: str
    x: int
    y: int
    w: int
    h: int
    conf: float
    page: int = 0


@dataclass
class NormalizedDoc:
    text: str                                   # whole document as one string
    # char range -> where it lives in the source (cell / page+bbox / line)
    spans: list = field(default_factory=list)   # list[(start, end, ref)]
