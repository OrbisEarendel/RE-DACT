import pytesseract
from PIL import Image, ImageOps, ImageDraw
from pillow_heif import register_heif_opener

register_heif_opener()

SRC = "20261116_221018.heic"

# open + fix phone rotation (EXIF)
img = ImageOps.exif_transpose(Image.open(SRC)).convert("RGB")
print("size:", img.size)

# plain OCR, no preprocessing
text = pytesseract.image_to_string(img, lang="eng")
print("\n----- FULL TEXT -----\n")
print(text)

# word boxes
data = pytesseract.image_to_data(img, lang="eng", output_type=pytesseract.Output.DICT)
draw = ImageDraw.Draw(img)
n = 0
for i, w in enumerate(data["text"]):
    if w.strip() and float(data["conf"][i]) > 30:
        x, y, bw, bh = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        draw.rectangle([x, y, x + bw, y + bh], outline="red", width=3)
        n += 1
print(f"\n{n} words boxed")
img.save("ocr_boxes.png")
