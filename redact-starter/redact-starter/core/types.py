"""THE CONTRACT. Everyone imports these. Do not change a field without telling the team.

Allowed after the first hour: ADD new optional fields or new entity types.
Not allowed without a team message: rename, remove, or change the meaning of a field.
"""
from dataclasses import dataclass, field
from typing import Optional

# Entity types every detector must use (add new ones here, never invent strings elsewhere).
PERSON = "PERSON"
EMAIL = "EMAIL"
PHONE = "PHONE"
ID_NUMBER = "ID_NUMBER"
DATE = "DATE"
LOCATION = "LOCATION"
ORG = "ORG"
ENTITY_TYPES = [PERSON, EMAIL, PHONE, ID_NUMBER, DATE, LOCATION, ORG]


@dataclass
class TextUnit:
    """One piece of text pulled out of a file (a whole .txt, one PDF page, one OCR line...)."""
    text: str
    locator: dict = field(default_factory=dict)  # e.g. {"kind": "text"} or {"page": 2}


@dataclass
class Span:
    """One piece of sensitive text found inside a TextUnit."""
    text: str                      # the original string, e.g. "priya@example.com"
    start: int                     # offset inside units[unit].text
    end: int                       # offset just after the last character
    type: str                      # one of ENTITY_TYPES
    unit: int = 0                  # index into the list of TextUnits
    confidence: float = 1.0
    source: str = "rule"           # "rule", "ner", "dictionary", "context"
    rule_id: str = ""              # name of the rule that fired (goes in the audit log)
    bbox: Optional[tuple] = None   # (x0, y0, x1, y1) for images and scanned pages


@dataclass
class Edit:
    """A span plus the text that should replace it."""
    span: Span
    replacement: str


@dataclass
class RedactResult:
    out_path: str
    log: dict   # METADATA ONLY: counts, types, rule ids. NEVER original text.
