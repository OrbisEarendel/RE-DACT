
from paddleocr import PaddleOCR
from pathlib import Path
import time
import json

image_path = "WhatsApp Image 2026-11-16 at 10.43.03 PM.jpeg"

if not Path(image_path).exists():
    raise FileNotFoundError(f"Image not found: {image_path}")

print("Initializing PaddleOCR...")

ocr = PaddleOCR(
    lang="en",
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
)

print("Running OCR...")
start = time.perf_counter()

results = ocr.predict(image_path)

elapsed = time.perf_counter() - start

print(f"\nCompleted in {elapsed:.2f} seconds")
print("=" * 60)

all_text = []

for page in results:
    data = page.json
    if callable(data):
        data = data()

    if isinstance(data, str):
        data = json.loads(data)

    res = data.get("res", data)

    texts = res.get("rec_texts", [])
    scores = res.get("rec_scores", [])

    for i, text in enumerate(texts):
        score = scores[i] if i < len(scores) else 0
        all_text.append(text)
        print(f"{score:.4f} | {text}")

Path("paddle_result.txt").write_text(
    "\n".join(all_text),
    encoding="utf-8"
)

print("=" * 60)
print(f"Recognized lines: {len(all_text)}")
print("Saved to paddle_result.txt")

