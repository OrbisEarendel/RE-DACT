import re, random
import numpy as np, cv2, pytesseract
from PIL import Image, ImageDraw, ImageFont, ImageFilter

random.seed(1); np.random.seed(1)
F = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# ---- fake ID card (all data is made up) ----
img = Image.new("RGB", (900, 560), (245, 240, 225))
d = ImageDraw.Draw(img)
d.rectangle([0, 0, 900, 70], fill=(30, 60, 120))
d.text((30, 18), "SAMPLE IDENTITY CARD (DUMMY)", font=ImageFont.truetype(FB, 30), fill="white")
rows = [
 ("Name:", "Ravi Kumar Shetty"),
 ("DOB:", "14/03/1992"),
 ("ID No:", "2345 6789 0123"),
 ("PAN:", "ABCDE1234F"),
 ("Phone:", "98450 12345"),
 ("Email:", "ravi.shetty@example.com"),
 ("Address:", "2nd Floor, Sri Residency, Kadri Hills,"),
 ("", "Mangaluru, Karnataka 575002"),
]
y = 110
for k, v in rows:
    d.text((40, y), k, font=ImageFont.truetype(FB, 28), fill=(20, 20, 20))
    d.text((220, y), v, font=ImageFont.truetype(F, 28), fill=(20, 20, 20))
    y += 55
img.save("card_clean.png")

# ---- degraded "phone photo" version ----
g = img.rotate(3, expand=True, fillcolor=(200, 200, 200)).filter(ImageFilter.GaussianBlur(1.3))
a = np.array(g).astype(np.int16) + np.random.normal(0, 14, (g.size[1], g.size[0], 3)).astype(np.int16)
Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save("card_noisy.png")

PATTERNS = {
 "ID":    re.compile(r"^\d{4}$|^\d{4}\s?\d{4}\s?\d{4}$"),
 "PAN":   re.compile(r"^[A-Z]{5}\d{4}[A-Z]$"),
 "EMAIL": re.compile(r"^[\w.+-]+@[\w-]+\.[\w.]+$"),
 "PIN":   re.compile(r"^\d{6}$"),
}

def run(path, preprocess):
    im = cv2.imread(path)
    if preprocess:
        gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        gray = cv2.fastNlMeansDenoising(gray, None, 15)
        proc = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)
        scale = 2
    else:
        proc, scale = im, 1
    data = pytesseract.image_to_data(proc, lang="eng", config="--psm 6", output_type=pytesseract.Output.DICT)
    words = []
    for i, t in enumerate(data["text"]):
        if t.strip() and float(data["conf"][i]) > 0:
            words.append((t, data["left"][i]//scale, data["top"][i]//scale,
                          data["width"][i]//scale, data["height"][i]//scale, float(data["conf"][i])))
    return im, words

for path in ["card_clean.png", "card_noisy.png"]:
    for pre in (False, True):
        im, words = run(path, pre)
        print(f"\n=== {path}  preprocess={pre}  words={len(words)} ===")
        print(" ".join(w[0] for w in words))
        hits = [w for w in words if any(p.match(w[0]) for p in PATTERNS.values())]
        print("regex hits on OCR words:", [h[0] for h in hits])
        out = im.copy()
        for t, x, y, w, h, c in words:
            col = (0, 0, 255) if (t, x, y, w, h, c) in hits else (0, 160, 0)
            cv2.rectangle(out, (x, y), (x + w, y + h), col, 2)
        cv2.imwrite(f"out_{path[:-4]}_{'pre' if pre else 'raw'}.png", out)
