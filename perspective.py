
import cv2
import numpy as np

# Load original image
image = cv2.imread("ocrimagesample.png")

if image is None:
    raise FileNotFoundError("ocrimagesample.png not found")

original = image.copy()
height, width = image.shape[:2]

# Convert to grayscale
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

# Smooth image to reduce noise
blurred = cv2.GaussianBlur(gray, (5, 5), 0)

# Detect edges
edges = cv2.Canny(blurred, 50, 150)

# Connect broken edges
kernel = np.ones((5, 5), np.uint8)
edges = cv2.dilate(edges, kernel, iterations=2)

# Find contours
contours, _ = cv2.findContours(
    edges,
    cv2.RETR_LIST,
    cv2.CHAIN_APPROX_SIMPLE
)

# Find document quadrilateral
contours = sorted(
    contours,
    key=cv2.contourArea,
    reverse=True
)

document = None

for contour in contours:
    perimeter = cv2.arcLength(contour, True)

    approx = cv2.approxPolyDP(
        contour,
        0.02 * perimeter,
        True
    )

    if len(approx) == 4:
        document = approx.reshape(4, 2)
        break

if document is None:
    raise RuntimeError("Could not detect document corners")

# Order corners: top-left, top-right,
# bottom-right, bottom-left
def order_points(points):
    rect = np.zeros((4, 2), dtype="float32")

    sums = points.sum(axis=1)
    diffs = np.diff(points, axis=1)

    rect[0] = points[np.argmin(sums)]
    rect[2] = points[np.argmax(sums)]
    rect[1] = points[np.argmin(diffs)]
    rect[3] = points[np.argmax(diffs)]

    return rect

rect = order_points(document)
tl, tr, br, bl = rect

# Calculate output dimensions
w1 = np.linalg.norm(br - bl)
w2 = np.linalg.norm(tr - tl)

h1 = np.linalg.norm(tr - br)
h2 = np.linalg.norm(tl - bl)

output_width = int(max(w1, w2))
output_height = int(max(h1, h2))

# Define destination rectangle
destination = np.array([
    [0, 0],
    [output_width - 1, 0],
    [output_width - 1, output_height - 1],
    [0, output_height - 1]
], dtype="float32")

# Perspective transformation
matrix = cv2.getPerspectiveTransform(
    rect,
    destination
)

corrected = cv2.warpPerspective(
    original,
    matrix,
    (output_width, output_height)
)

# Save results
cv2.imwrite("perspective_corrected.png", corrected)

# Save debug image with detected corners
debug = original.copy()
cv2.polylines(
    debug,
    [document.astype(np.int32)],
    True,
    (0, 255, 0),
    3
)

cv2.imwrite("detected_corners.png", debug)

print("Document detected!")
print("Original size:", width, "x", height)
print("Corrected size:", output_width, "x", output_height)
print("Saved perspective_corrected.png")
print("Saved detected_corners.png")
