import re
from dataclasses import dataclass
from gliner import GLiNER
from faker import Faker

LABELS = ["person", "address", "city", "organization", "phone number",
          "email", "date", "age", "job title", "medical condition",
          "family relation"]          # the last one soaks up "my cousin", then we ignore it
IGNORE = {"family relation"}

REGEX = {
    "phone number": re.compile(r"\b[6-9]\d{4}\s?\d{5}\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"),
    "PAN": re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
}

model = GLiNER.from_pretrained("urchade/gliner_multi_pii-v1")
fake = Faker("en_IN")

FAKERS = {
    "person": fake.name, "phone number": fake.phone_number,
    "email": fake.email, "organization": fake.company,
    "city": fake.city, "address": fake.address,
    "date": fake.date, "job title": fake.job,
    "age": lambda: str(fake.random_int(20, 60)),
    "PAN": lambda: fake.bothify("?????####?").upper(),
}

@dataclass
class Entity:
    type: str
    start: int
    end: int
    score: float

def detect(text, threshold=0.4):
    ents = []
    for e in model.predict_entities(text, LABELS, threshold=threshold):
        if e["label"] not in IGNORE:
            ents.append(Entity(e["label"], e["start"], e["end"], e["score"]))
    for label, rx in REGEX.items():
        for m in rx.finditer(text):
            ents.append(Entity(label, m.start(), m.end(), 1.0))
    return merge(ents)

def merge(ents):
    # higher score wins, then longer span; drop anything overlapping a winner
    ents = sorted(ents, key=lambda e: (-e.score, -(e.end - e.start)))
    kept = []
    for e in ents:
        if not any(e.start < k.end and k.start < e.end for k in kept):
            kept.append(e)
    return sorted(kept, key=lambda e: e.start)

def redact(text, ents, mode="mask"):
    mapping = {}
    for e in sorted(ents, key=lambda e: e.start, reverse=True):
        original = text[e.start:e.end]
        if mode == "mask":
            repl = f"[{e.type.upper()}]"
        else:  # fake, consistent: same real value -> same fake value
            if original not in mapping:
                mapping[original] = FAKERS.get(e.type, lambda: "[REDACTED]")()
            repl = mapping[original]
        text = text[:e.start] + repl + text[e.end:]
    return text
