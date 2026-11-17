"""GLiNER detector. Owner: P1.

GLiNER is a small encoder model that EXTRACTS spans from the input (it cannot generate text),
so it cannot invent or leak anything. It is still a model, not a rule: log source="gliner".
Keep the regex/checksum detectors running too. Results are unioned.

Turn it on with:  REDACT_USE_GLINER=1
Pick a model:     REDACT_GLINER_MODEL=knowledgator/gliner-pii-base-v1.0   (default, Apache-2.0)
Tune recall:      REDACT_GLINER_THRESHOLD=0.3   (lower = finds more, more false positives)

OFFLINE: from_pretrained downloads from Hugging Face on first use. Download once, bake the files
into the Docker image, and point REDACT_GLINER_MODEL at the local folder.
"""
import os

from core.types import DATE, EMAIL, ID_NUMBER, LOCATION, ORG, PERSON, PHONE, Span, TextUnit

# GLiNER is zero-shot: the label WORDS matter. Left side is what we ask the model for,
# right side is our contract type. Try rewording labels if recall is poor.
LABEL_MAP = {
    "person name": PERSON,
    "email address": EMAIL,
    "phone number": PHONE,
    "date of birth": DATE,
    "address": LOCATION,
    "organization": ORG,
    "national id number": ID_NUMBER,
}

DEFAULT_MODEL = "knowledgator/gliner-pii-base-v1.0"
DEFAULT_THRESHOLD = 0.3
# The model cards do not state a max input length. GLiNER truncates long inputs, so we
# chunk. TODO (P1): check the library's max_len and tune these two numbers.
CHUNK_CHARS = 800
CHUNK_OVERLAP = 100


def chunk_text(text: str, max_chars: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP):
    """Split text into (offset, chunk) pieces, cutting at whitespace where possible."""
    if len(text) <= max_chars:
        return [(0, text)]
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            cut = text.rfind(" ", start + max_chars // 2, end)
            cut = max(cut, text.rfind("\n", start + max_chars // 2, end))
            if cut > start:
                end = cut
        chunks.append((start, text[start:end]))
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


class GlinerDetector:
    def __init__(self, model=None, threshold: float | None = None):
        self._model = model  # injectable so tests can use a fake
        self.threshold = threshold if threshold is not None else float(
            os.environ.get("REDACT_GLINER_THRESHOLD", DEFAULT_THRESHOLD))

    def _get_model(self):
        if self._model is None:
            from gliner import GLiNER  # imported late so the repo runs without it
            self._model = GLiNER.from_pretrained(
                os.environ.get("REDACT_GLINER_MODEL", DEFAULT_MODEL))
        return self._model

    def detect(self, units: list[TextUnit]) -> list[Span]:
        model = self._get_model()
        labels = list(LABEL_MAP)
        best: dict = {}  # (unit, start, end, type) -> Span, keeps the highest score
        for ui, unit in enumerate(units):
            for offset, chunk in chunk_text(unit.text):
                for ent in model.predict_entities(chunk, labels, threshold=self.threshold):
                    etype = LABEL_MAP.get(ent["label"])
                    if etype is None:
                        continue
                    start, end = offset + ent["start"], offset + ent["end"]
                    span = Span(text=unit.text[start:end], start=start, end=end, type=etype,
                                unit=ui, confidence=float(ent.get("score", 0.0)),
                                source="gliner", rule_id=f"gliner:{ent['label']}")
                    key = (ui, start, end, etype)
                    if key not in best or span.confidence > best[key].confidence:
                        best[key] = span
        return list(best.values())
