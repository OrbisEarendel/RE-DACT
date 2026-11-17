
import cv2
import json
import numpy as np
from pathlib import Path
from paddleocr import PaddleOCR
from engine import detect

IMAGE = "WhatsApp Image 2026-11-16 at 10.43.03 PM.jpeg"
OUTPUT = "paddle_redaction_preview.png"

if not Path(IMAGE).exists():
    raise FileNotFoundError(IMAGE)

# 1. Run PaddleOCR on the ORIGINAL image
ocr = PaddleOCR(
    lang="en",
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
)

print("Running PaddleOCR...")
results = ocr.predict(IMAGE)

image = cv2.imread(IMAGE)
if image is None:
    raise RuntimeError("Could not open source image")

# 2. Extract text and coordinates
lines = []
all_text = []
offset = 0

for page in results:
    data = page.json
    if callable(data):
        data = data()

    if isinstance(data, str):
        data = json.loads(data)

    res = data.get("res", data)

    texts = res.get("rec_texts", [])
    boxes = res.get("rec_boxes", [])

    for i, text in enumerate(texts):
        if not text.strip():
            continue

        if i >= len(boxes):
            continue

        start = offset
        end = start + len(text)

        lines.append({
            "text": text,
            "start": start,
            "end": end,
            "box": boxes[i],
        })

        all_text.append(text)
        offset = end + 1

combined_text = "\n".join(all_text)

# 3. Detect sensitive entities using existing engine.py
print("\nRunning GLiNER + Regex...")
entities = detect(combined_text)

print("\nDETECTED ENTITIES")
print("=" * 60)

for entity in entities:
    value = combined_text[entity.start:entity.end]
    print(f"{entity.type:18} | {value} | {entity.score:.3f}")

# 4. Draw normal colored boxes around matching OCR regions
for entity in entities:
    for line in lines:
        overlaps = (
            entity.start < line["end"]
            and line["start"] < entity.end
        )

        if not overlaps:
            continue

        x1, y1, x2, y2 = map(int, line["box"])

        cv2.rectangle(
            image,
            (x1, y1),
            (x2, y2),
            (0, 0, 255),
            2
        )

        label = entity.type.upper()

        cv2.putText(
            image,
            label,
            (x1, max(20, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 0, 255),
            1,
            cv2.LINE_AA
        )

# 5. Save preview; original image remains untouched
cv2.imwrite(OUTPUT, image)

print("\n" + "=" * 60)
print(f"Entities detected: {len(entities)}")
print(f"Preview saved: {OUTPUT}")
print("Original image was not modified.")

