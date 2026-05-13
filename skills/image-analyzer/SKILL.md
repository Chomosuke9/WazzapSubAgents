---
name: image-analyzer
description: |
  Analyze images — extract metadata, detect colors, read EXIF, perform OCR on text
  within images, and generate detailed reports. Use this skill when the user asks to
  describe, inspect, or extract information from image files (JPEG, PNG, WebP, GIF,
  BMP, TIFF). Libraries: Pillow, pytesseract, opencv-python-headless (sparingly).
---

# Image Analyzer Agent

This skill analyzes images using lightweight, CPU-efficient tools. It produces
**reports** (`.md`, `.txt`, `.json`, `.csv`) describing what's inside an image —
no AI models, no upscaling, no heavy computation.

---

## Quick Reference

| Task | Primary Tool | Use When |
|------|-------------|----------|
| Basic info (size, format, mode) | `Pillow` (`PIL.Image`) | Always start here |
| EXIF / metadata | `Pillow.Exif` | Reading camera info, GPS, timestamps |
| Color palette / dominant colors | `Pillow` + `collections.Counter` | Color analysis, palette extraction |
| Color histogram | `Pillow.Image.histogram()` | Brightness, channel distribution |
| OCR (text in image) | `pytesseract` | Extracting visible text from images |
| Basic edge / feature detection | `opencv` (`cv2.Canny`, `cv2.findContours`) | ONLY when Pillow is insufficient |
| Image comparison | `Pillow.ImageChops` + pixel diff | Finding differences between two images |
| File size / compression analysis | `os.path.getsize`, `Pillow` | Checking file efficiency |

---

## Library Overview

### Pillow (`PIL`) — Primary Tool

| Capability | Key API |
|-----------|---------|
| Open & inspect | `Image.open()` → `.size`, `.mode`, `.format`, `.info` |
| EXIF reading | `Image.getexif()` |
| Color analysis | `.getcolors()`, `.histogram()`, `.getpixel()` |
| Resize (simple) | `.resize(size, LANCZOS)` |
| Crop | `.crop(box)` |
| Convert format | `.save("out.png", "PNG")` |
| Channel split/merge | `.split()`, `Image.merge()` |
| Image comparison | `ImageChops.difference()`, `.getbbox()` |

### pytesseract — OCR

| Capability | Key API |
|-----------|---------|
| Image to string | `image_to_string(img, lang='eng')` |
| Image to boxes | `image_to_boxes(img)` — character-level |
| Image to data | `image_to_data(img)` — word-level with confidence |

### opencv (cv2) — Use SPARINGLY

Only use `opencv` when Pillow genuinely cannot perform the task (e.g. contour
detection, Hough line transform, template matching). opencv is heavier than
Pillow — prefer Pillow for everything it can handle.

| Capability | Key API |
|-----------|---------|
| Edge detection | `cv2.Canny()` |
| Contour finding | `cv2.findContours()` |
| Line detection | `cv2.HoughLinesP()` |
| Template matching | `cv2.matchTemplate()` |

---

## Workflow by Category

### 1. BASIC IMAGE INSPECTION

Always start here. Get dimensions, format, file size, and mode.

```python
from PIL import Image
import os

path = "image.jpg"
img = Image.open(path)
file_size = os.path.getsize(path)

print(f"Format:    {img.format}")
print(f"Mode:      {img.mode}")         # RGB, RGBA, L, CMYK, etc.
print(f"Size:      {img.size[0]}x{img.size[1]} px")
print(f"File size: {file_size:,} bytes ({file_size/1024:.1f} KB)")
print(f"DPI:       {img.info.get('dpi', 'N/A')}")
```

**Batch inspection (multiple images):**

```python
import os
from PIL import Image

images = [f for f in os.listdir(".") if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.tiff'))]

for path in sorted(images):
    img = Image.open(path)
    size_kb = os.path.getsize(path) / 1024
    print(f"{path:40s} | {img.size[0]:>5d}x{img.size[1]:<5d} | {img.mode:6s} | {size_kb:8.1f} KB")
```

---

### 2. EXIF & METADATA EXTRACTION

Read camera settings, GPS coordinates, timestamps, and other embedded metadata.

```python
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

def get_exif_data(path):
    img = Image.open(path)
    exif = img.getexif()
    if not exif:
        return {"error": "No EXIF data found"}

    result = {}
    for tag_id, value in exif.items():
        tag_name = TAGS.get(tag_id, tag_id)

        # Decode GPS data
        if tag_name == "GPSInfo":
            gps = {}
            for key, val in value.items():
                gps_key = GPSTAGS.get(key, key)
                gps[gps_key] = str(val) if not isinstance(val, bytes) else val.hex()
            result[tag_name] = gps
        else:
            result[tag_name] = str(value) if not isinstance(value, bytes) else value.hex()

    return result

# Usage
import json
exif = get_exif_data("photo.jpg")
print(json.dumps(exif, indent=2))
```

**Quick EXIF summary (human-readable):**

```python
from PIL import Image

img = Image.open("photo.jpg")
exif = img.getexif()

# Common fields
fields = {
    271: "Make", 272: "Model", 306: "DateTime",
    33432: "Copyright", 34855: "ISO", 37378: "Aperture",
    37377: "ShutterSpeed", 37385: "Flash",
}

for tag, name in fields.items():
    val = exif.get(tag)
    if val is not None:
        print(f"{name:20s}: {val}")
```

---

### 3. COLOR ANALYSIS

Extract dominant colors, generate a palette, or compute color statistics.

**Dominant colors (quantized):**

```python
from PIL import Image
from collections import Counter

def dominant_colors(path, n=5):
    img = Image.open(path).convert("RGB")
    # Resize small for speed — color distribution is preserved
    img = img.resize((150, 150), Image.LANCZOS)
    pixels = list(img.getdata())
    counter = Counter(pixels)
    return counter.most_common(n)

palette = dominant_colors("image.jpg", n=5)
for rank, (rgb, count) in enumerate(palette, 1):
    pct = count / sum(c for _, c in palette) * 100
    hex_color = "#{:02x}{:02x}{:02x}".format(*rgb)
    print(f"{rank}. {hex_color}  {rgb}  ({pct:.1f}%)")
```

**Average color & brightness:**

```python
from PIL import Image, ImageStat

img = Image.open("image.jpg").convert("RGB")
stat = ImageStat.Stat(img)
avg_rgb = tuple(int(v) for v in stat.mean)
brightness = sum(avg_rgb) / (3 * 255) * 100  # 0-100%

print(f"Average color:  #{avg_rgb[0]:02x}{avg_rgb[1]:02x}{avg_rgb[2]:02x}")
print(f"Brightness:     {brightness:.1f}%")
print(f"Std deviation:  {tuple(int(v) for v in stat.stddev)}")
```

**Channel histograms:**

```python
from PIL import Image

img = Image.open("image.jpg")
r, g, b = img.split()

for channel, name in [(r, "Red"), (g, "Green"), (b, "Blue")]:
    hist = channel.histogram()
    # Bucket into 10 bins for readability
    bin_size = 256 // 10
    bins = [sum(hist[i:i+bin_size]) for i in range(0, 256, bin_size)]
    print(f"{name}: {bins}")
```

---

### 4. OCR — TEXT EXTRACTION

Extract visible text from images. Works best on screenshots, documents, signs,
and clear typography.

```python
import pytesseract
from PIL import Image

img = Image.open("screenshot.png")
text = pytesseract.image_to_string(img, lang='eng')
print(text)
```

**Confidence-aware extraction (word-level):**

```python
import pytesseract
from PIL import Image

data = pytesseract.image_to_data(Image.open("image.png"), lang='eng', output_type=pytesseract.Output.DICT)

for i, word in enumerate(data['text']):
    if word.strip():
        conf = int(data['conf'][i])
        marker = "✓" if conf > 60 else "⚠" if conf > 30 else "✗"
        print(f"[{marker} {conf:3d}%] {word}")
```

**Multi-language OCR:**

```python
# Language codes: eng, ind, jpn, chi_sim, ara, etc.
text = pytesseract.image_to_string(img, lang='eng+ind')
```

**OCR a specific region:**

```python
from PIL import Image
import pytesseract

img = Image.open("image.png")
# Crop to region: (left, top, right, bottom)
region = img.crop((100, 50, 500, 200))
text = pytesseract.image_to_string(region)
print(text)
```

---

### 5. IMAGE COMPARISON

Compare two images and report differences.

```python
from PIL import Image, ImageChops
import math

def compare_images(path1, path2, threshold=5):
    img1 = Image.open(path1).convert("RGB")
    img2 = Image.open(path2).convert("RGB")

    if img1.size != img2.size:
        return {
            "match": False,
            "reason": f"Size mismatch: {img1.size} vs {img2.size}",
            "diff_pct": 100.0,
        }

    diff = ImageChops.difference(img1, img2)
    # Count pixels that differ beyond threshold
    pixels = list(diff.getdata())
    different = sum(1 for p in pixels if sum(p) / 3 > threshold)
    total = len(pixels)
    diff_pct = different / total * 100

    return {
        "match": diff_pct < 1.0,
        "diff_pct": round(diff_pct, 2),
        "different_pixels": different,
        "total_pixels": total,
        "diff_image": diff,  # PIL Image showing differences
    }

result = compare_images("before.png", "after.png")
if result["match"]:
    print("Images are essentially identical")
else:
    print(f"Images differ by {result['diff_pct']}% ({result['different_pixels']} pixels)")
    # Save diff image for visual inspection
    result["diff_image"].save("diff_output.png")
```

---

### 6. BASIC FEATURE DETECTION (opencv — use sparingly)

Only use these when Pillow genuinely cannot do the job.

**Count objects via contour detection:**

```python
import cv2
import numpy as np

img = cv2.imread("objects.jpg")
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
blurred = cv2.GaussianBlur(gray, (5, 5), 0)
edges = cv2.Canny(blurred, 30, 150)
contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

# Filter tiny noise contours
min_area = 100
objects = [c for c in contours if cv2.contourArea(c) > min_area]
print(f"Detected {len(objects)} distinct objects (min area: {min_area}px)")
```

**Detect lines (for forms, tables, documents):**

```python
import cv2
import numpy as np

img = cv2.imread("form.jpg")
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
edges = cv2.Canny(gray, 50, 150)
lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=100, minLineLength=200, maxLineGap=10)

if lines is not None:
    print(f"Detected {len(lines)} lines")
    horiz = sum(1 for l in lines if abs(l[0][1] - l[0][3]) < 10)
    vert = sum(1 for l in lines if abs(l[0][0] - l[0][2]) < 10)
    print(f"  Horizontal: {horiz}")
    print(f"  Vertical:   {vert}")
```

**Template matching (find sub-image within larger image):**

```python
import cv2

img = cv2.imread("screenshot.png")
tmpl = cv2.imread("icon.png")
result = cv2.matchTemplate(img, tmpl, cv2.TM_CCOEFF_NORMED)
_, max_val, _, max_loc = cv2.minMaxLoc(result)

if max_val > 0.8:
    h, w = tmpl.shape[:2]
    print(f"Found at position ({max_loc[0]}, {max_loc[1]}), confidence: {max_val:.2f}")
    print(f"Match region: ({max_loc[0]}, {max_loc[1]}) → ({max_loc[0]+w}, {max_loc[1]+h})")
else:
    print(f"No match found (best confidence: {max_val:.2f})")
```

---

## Common Patterns

### Full image report (combine everything)

```python
from PIL import Image, ImageStat
import os, json

def full_image_report(path):
    img = Image.open(path)
    stat = ImageStat.Stat(img.convert("RGB"))

    report = {
        "file": os.path.basename(path),
        "size_bytes": os.path.getsize(path),
        "dimensions": f"{img.size[0]}x{img.size[1]}",
        "megapixels": round(img.size[0] * img.size[1] / 1_000_000, 1),
        "format": img.format,
        "mode": img.mode,
        "dpi": img.info.get("dpi"),
        "avg_color_rgb": tuple(int(v) for v in stat.mean),
        "has_alpha": img.mode in ("RGBA", "LA", "PA"),
        "has_exif": bool(img.getexif()),
        "aspect_ratio": f"{img.size[0]/img.size[1]:.2f}:1" if img.size[1] else "N/A",
    }

    # Aspect ratio classification
    ar = img.size[0] / img.size[1] if img.size[1] else 1
    if 0.95 < ar < 1.05:
        report["orientation"] = "square"
    elif ar > 1:
        report["orientation"] = "landscape"
    else:
        report["orientation"] = "portrait"

    return report

# Print as JSON
print(json.dumps(full_image_report("image.jpg"), indent=2))
```

### Generate a color palette swatch image

```python
from PIL import Image, ImageDraw
from collections import Counter

def generate_palette_image(path, n=8, swatch_w=150, swatch_h=100):
    img = Image.open(path).convert("RGB")
    img_small = img.resize((100, 100), Image.LANCZOS)
    counter = Counter(img_small.getdata())
    top_colors = [c[0] for c in counter.most_common(n)]

    palette = Image.new("RGB", (swatch_w * n, swatch_h))
    draw = ImageDraw.Draw(palette)
    for i, rgb in enumerate(top_colors):
        draw.rectangle(
            [i * swatch_w, 0, (i + 1) * swatch_w, swatch_h],
            fill=rgb,
            outline=(200, 200, 200),
            width=1,
        )
    palette.save("palette.png")
    return top_colors

colors = generate_palette_image("image.jpg", n=6)
for i, rgb in enumerate(colors):
    print(f"{i+1}. #{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}")
```

---

## Error Handling Checklist

| Scenario | Error | Solution |
|----------|-------|----------|
| File not found | `FileNotFoundError` | Verify the input path; check staging directory |
| Corrupted image | `PIL.UnidentifiedImageError` | Try `Image.open()` with `mode='r'`; report as unreadable |
| No EXIF data | empty `getexif()` | Report "No EXIF metadata" — this is normal for screenshots/web images |
| OCR returns garbage | Low-quality text | Preprocess: convert to grayscale, increase contrast, resize larger |
| Image mode not RGB | `.convert("RGB")` | Always convert before color analysis |
| Large image (>50MP) | Memory slow | Resize down with `.resize()` before analysis; maintain aspect ratio |
| tesseract not found | `TesseractNotFoundError` | Skip OCR; report that text extraction is unavailable |
| opencv import fails | `ImportError` | Fall back to Pillow-only analysis; opencv is optional |

---

## Performance Guidelines

- **Resize before analysis**: For images > 20 MP, resize to ~2 MP for color
  analysis and ~4 MP for OCR. Use `LANCZOS` interpolation.
- **Stream don't load twice**: If doing multiple analyses on the same image,
  load it once and keep it in memory.
- **Avoid opencv unless necessary**: 90% of tasks can be done with Pillow alone.
- **Batch OCR is slow**: Process pages sequentially, report progress between pages.
- **Memory**: A 4000×3000 PNG takes ~36 MB uncompressed (RGB). Keep this in mind
  when working with many images in a single script.

---

## Recommended Flow

1. **User request** → Determine what they want extracted (info, colors, text, comparison)
2. **Load image** → `Image.open()` — always start here
3. **Quick inspection** → Size, format, mode — print a summary first
4. **Targeted analysis** → Run the specific analysis needed (EXIF, OCR, colors, etc.)
5. **Output report** → Save as `.md`, `.txt`, `.json`, or `.csv` in the workdir
6. **Declare deliverables** → Only include final report files in `end_task(output_files=[...])`

---

## Notes

- **Pillow** handles JPEG, PNG, WebP (static), GIF, BMP, TIFF, ICO natively.
- **pytesseract** requires `tesseract-ocr` (pre-installed in the container).
  Language data files are in `/usr/share/tesseract-ocr/4.00/tessdata/`.
- **opencv** is pre-installed but should be used only when Pillow is insufficient.
  Edge detection and template matching are the main valid use cases.
- EXIF data is primarily found in JPEG and TIFF files from cameras/phones.
  Screenshots and web downloads rarely have EXIF.
- OCR quality depends heavily on image clarity. Preprocessing (grayscale +
  thresholding) can dramatically improve results.
```
