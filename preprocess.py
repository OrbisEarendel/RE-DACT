import cv2

filename = "WhatsApp Image 2026-11-16 at 10.43.03 PM.jpeg"

img = cv2.imread(filename)

if img is None:
    raise FileNotFoundError(filename)

# Upscale 2x
img = cv2.resize(img, None, fx=2, fy=2,
                 interpolation=cv2.INTER_CUBIC)

# Grayscale
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

# Contrast enhancement
clahe = cv2.createCLAHE(
    clipLimit=2.0,
    tileGridSize=(8, 8)
)
enhanced = clahe.apply(gray)

# Denoising
denoised = cv2.fastNlMeansDenoising(
    enhanced, None, 10, 7, 21
)

cv2.imwrite("processed_gray.png", denoised)

# Adaptive threshold
threshold = cv2.adaptiveThreshold(
    denoised, 255,
    cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
    cv2.THRESH_BINARY,
    31, 11
)

cv2.imwrite("processed_binary.png", threshold)

print("Preprocessing complete!")
