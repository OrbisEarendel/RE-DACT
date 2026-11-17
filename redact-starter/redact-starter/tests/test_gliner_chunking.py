"""Tests the chunking + offset logic with a FAKE model. No GLiNER install needed."""
from core.types import TextUnit
from detect.gliner_detector import GlinerDetector, chunk_text


class FakeModel:
    """Pretends to be GLiNER: 'finds' every occurrence of a known name."""
    def predict_entities(self, text, labels, threshold=0.3):
        out, name = [], "Priya Sharma"
        i = text.find(name)
        while i != -1:
            out.append({"text": name, "label": "person name", "start": i, "end": i + len(name), "score": 0.9})
            i = text.find(name, i + 1)
        return out


def test_short_text_is_one_chunk():
    assert chunk_text("hello world") == [(0, "hello world")]


def test_chunks_cover_whole_text_and_offsets_are_right():
    text = ("word " * 600).strip()
    chunks = chunk_text(text, max_chars=200, overlap=40)
    assert len(chunks) > 1
    for offset, chunk in chunks:
        assert text[offset:offset + len(chunk)] == chunk
    assert chunks[-1][0] + len(chunks[-1][1]) == len(text)


def test_span_offsets_map_back_to_original_text_across_chunks():
    text = ("filler " * 300) + "Priya Sharma" + (" filler" * 300)
    spans = GlinerDetector(model=FakeModel()).detect([TextUnit(text=text)])
    assert len(spans) == 1  # overlap must not create duplicates
    s = spans[0]
    assert text[s.start:s.end] == "Priya Sharma"
    assert s.type == "PERSON" and s.source == "gliner"
