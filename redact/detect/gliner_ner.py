"""RE-DACT GLiNER NER detector module.

Conforms to AGENTS.md sections 4, 5, 7:
  * Model: urchade/gliner_multi_pii-v1 (zero-shot)
  * Default threshold: 0.4
  * Labels: person, address, city, organization, phone number, email, date, age, job title, medical condition, family relation
  * Ignore list: family relation (absorbed to avoid misclassifying as person)
  * Output: list[Entity] with source="gliner"
"""

from __future__ import annotations

import os
from typing import Sequence

from redact.entity import Entity
from redact.detect.merge import merge

# Default entity types targeted by GLiNER (AGENTS.md sections 6 & 7)
DEFAULT_LABELS = [
    "person",
    "address",
    "city",
    "organization",
    "phone number",
    "email",
    "date",
    "age",
    "job title",
    "medical condition",
    "family relation",
]

# Types that are absorbed so they do not leak into 'person', then discarded (AGENTS.md section 6)
IGNORE_LABELS = frozenset({"family relation"})

_MODEL = None


def get_gliner_model(model_name: str = "urchade/gliner_multi_pii-v1"):
    """Lazy singleton for GLiNER model to avoid reloading weights repeatedly."""
    global _MODEL
    if _MODEL is None:
        from gliner import GLiNER

        # Offline friendly: huggingface_hub uses cached files
        _MODEL = GLiNER.from_pretrained(model_name)
    return _MODEL


def _chunk_text(text: str, max_chunk_len: int = 1200, overlap: int = 150) -> list[tuple[int, str]]:
    """Split text into overlapping chunks along line breaks or whitespace to respect token limits."""
    if len(text) <= max_chunk_len:
        return [(0, text)]

    chunks: list[tuple[int, str]] = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + max_chunk_len, text_len)
        if end < text_len:
            # Try to break at a newline or space
            break_idx = text.rfind("\n", start, end)
            if break_idx == -1 or break_idx <= start + overlap:
                break_idx = text.rfind(" ", start, end)
            if break_idx > start + overlap:
                end = break_idx

        chunks.append((start, text[start:end]))
        if end >= text_len:
            break
        start = max(start + 1, end - overlap)

    return chunks


def detect_gliner(
    text: str,
    threshold: float = 0.4,
    labels: Sequence[str] | None = None,
) -> list[Entity]:
    """Run GLiNER NER model on text and return Entity objects.

    Args:
        text: Input string (NormalizedDoc.text or any document string).
        threshold: Model confidence threshold (default 0.4 per AGENTS.md).
        labels: Optional label list (defaults to DEFAULT_LABELS).

    Returns:
        list[Entity]: Recognized non-overlapping entities.
    """
    if not text or not text.strip():
        return []

    target_labels = list(labels) if labels is not None else DEFAULT_LABELS
    model = get_gliner_model()

    # Split into chunks if text is long to prevent token truncation
    chunks = _chunk_text(text)
    raw_ents: list[Entity] = []

    for chunk_offset, chunk_text in chunks:
        preds = model.predict_entities(
            chunk_text,
            target_labels,
            threshold=threshold,
        )

        for p in preds:
            label = p["label"]
            if label in IGNORE_LABELS:
                continue

            start_char = chunk_offset + int(p["start"])
            end_char = chunk_offset + int(p["end"])
            score = float(p.get("score", 1.0))

            raw_ents.append(
                Entity(
                    type=label,
                    start=start_char,
                    end=end_char,
                    score=score,
                    source="gliner",
                )
            )

    # Resolve any boundary overlaps between chunks
    return merge(raw_ents)
