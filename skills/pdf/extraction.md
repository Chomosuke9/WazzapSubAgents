# PDF Extraction Operations

## Text Extraction Strategies

### Strategy 1: Simple Text (pdfplumber - default)
**Best for:** Most PDFs, when layout preservation needed
```python
import pdfplumber

with pdfplumber.open("file.pdf") as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        print(text)
```

### Strategy 2: Line-by-Line Extraction (preserve visual lines)
**Best for:** Identifying headers, paragraphs, reading order
```python
with pdfplumber.open("file.pdf") as pdf:
    page = pdf.pages[0]
    # extract_text_lines() returns per-visual-line dicts with position info.
    # (pdfplumber does NOT have extract_blocks() — group lines into
    # "blocks" yourself using x0 / top thresholds.)
    for line in page.extract_text_lines():
        print(f"Line at ({line['x0']}, {line['top']}): {line['text']}")
```

### Strategy 3: Word-by-Word Extraction
**Best for:** Precise positioning, search highlighting, reordering
```python
with pdfplumber.open("file.pdf") as pdf:
    page = pdf.pages[0]
    words = page.extract_words()
    for word in words:
        print(f"Word '{word['text']}' at ({word['x0']}, {word['top']})")
```

### Strategy 4: OCR Scanned PDFs
**Best for:** Image-based PDFs, scans, poor quality originals
```python
from pdf2image import convert_from_path
import pytesseract

images = convert_from_path("scan.pdf", dpi=300)
for i, image in enumerate(images):
    text = pytesseract.image_to_string(image, lang='eng+hin')  # Multi-language
    with open(f"page_{i+1}.txt", "w") as f:
        f.write(text)
```

**DPI tuning:**
- `dpi=150-200`: Fast, acceptable quality for clean scans
- `dpi=300`: Balanced (default)
- `dpi=400+`: High accuracy, slow, large temp files

**Language codes:** `eng`, `ind` (Indonesian), `fra`, `deu`, `spa`, `hin`, `tha`, `jpn`, `chi_sim`, etc.

### Strategy 5: OCR with Preprocessing
**Best for:** Low-quality scans, noisy images, skewed documents
```python
from pdf2image import convert_from_path
import pytesseract
import cv2
import numpy as np

images = convert_from_path("scan.pdf", dpi=300)
for i, image in enumerate(images):
    # Convert PIL to OpenCV format
    img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    
    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Deskew (fix rotation)
    coords = np.column_stack(np.where(gray > 0))
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    (h, w) = gray.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    
    # Threshold (binarize)
    thresh = cv2.threshold(rotated, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    
    # OCR the preprocessed image
    text = pytesseract.image_to_string(thresh, lang='eng')
    with open(f"page_{i+1}_ocr.txt", "w") as f:
        f.write(text)
```

### Strategy 6: CLI Text Extraction (poppler-utils)
**Best for:** Quick extraction without Python, large batch files
```bash
# Simple text extraction
pdftotext document.pdf output.txt

# Preserve layout
pdftotext -layout document.pdf output.txt

# Specific pages only
pdftotext -f 1 -l 5 document.pdf output.txt  # Pages 1-5

# Raw mode (no formatting)
pdftotext -raw document.pdf output.txt
```

---

## Table Extraction

### Method 1: Auto-detect (pdfplumber)
```python
with pdfplumber.open("report.pdf") as pdf:
    for page_num, page in enumerate(pdf.pages):
        tables = page.extract_tables()
        if tables:
            print(f"Found {len(tables)} tables on page {page_num+1}")
            for t_idx, table in enumerate(tables):
                print(f"Table {t_idx}: {len(table)} rows x {len(table[0])} cols")
```

### Method 2: Explicit Settings (advanced)
```python
# For tables with complex borders or spacing
tables = page.extract_table(
    settings={
        "vertical_strategy": "lines",  # or "lines_strict", "text"
        "horizontal_strategy": "lines",
        "snap_tolerance": 3,
        "join_tolerance": 3,
        "edge_min_length": 3,
        "min_words_vertical": 1,
    }
)
```

### Method 3: Export to Common Formats
```python
import csv
import json

# Export to CSV
with open("tables.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerows(tables[0])  # First table

# Export to JSON
with open("tables.json", "w") as f:
    json.dump(tables, f, indent=2)

# Export to pandas DataFrame
import pandas as pd
df = pd.DataFrame(tables[0][1:], columns=tables[0][0])
df.to_csv("table.csv", index=False)
```

### Method 4: Extract tables from specific page region
```python
with pdfplumber.open("report.pdf") as pdf:
    page = pdf.pages[0]
    # Crop to a region (x0, top, x1, bottom)
    cropped = page.crop((50, 200, 500, 500))
    tables = cropped.extract_tables()
```

---

## Image Extraction

### Option A: Extract embedded images (pdfplumber)
```python
import pdfplumber

with pdfplumber.open("document.pdf") as pdf:
    for page_num, page in enumerate(pdf.pages):
        # Get all images on page
        images = page.images
        for img_idx, img in enumerate(images):
            print(f"Image {img_idx} at ({img['x0']}, {img['top']}) "
                  f"size {img['width']}x{img['height']}")
```

### Option B: Rasterize pages as images (pdf2image)
```python
from pdf2image import convert_from_path

# Full page as image (useful for viewing/processing)
images = convert_from_path("doc.pdf", dpi=150, fmt="png")
for i, image in enumerate(images):
    image.save(f"page_{i+1}.png")
```

### Option C: Extract embedded images (pypdf)
```python
from pypdf import PdfReader

reader = PdfReader("doc.pdf")
for page_idx, page in enumerate(reader.pages):
    # `page.images` is the supported pypdf API and yields ImageFile objects
    # with .name, .data (raw bytes) and .image (PIL image).
    for img_idx, image in enumerate(page.images):
        out_path = f"extracted_p{page_idx+1}_{img_idx+1}_{image.name or 'img.bin'}"
        with open(out_path, "wb") as f:
            f.write(image.data)
```

### Option D: Extract images using poppler-utils (CLI)
```bash
# Extract all images
pdfimages -png document.pdf extracted_img

# Extract all images as JPEG
pdfimages -j document.pdf extracted_img

# List image info without extracting
pdfimages -list document.pdf
```

---

## Metadata Extraction

### Method 1: pdfplumber (simpler)
```python
import pdfplumber

with pdfplumber.open("doc.pdf") as pdf:
    meta = pdf.metadata
    print(f"Title: {meta.get('Title')}")
    print(f"Author: {meta.get('Author')}")
    print(f"Subject: {meta.get('Subject')}")
    print(f"Creator: {meta.get('Creator')}")
    print(f"Producer: {meta.get('Producer')}")
    print(f"Pages: {len(pdf.pages)}")
```

### Method 2: pypdf (more detailed)
```python
from pypdf import PdfReader

reader = PdfReader("doc.pdf")
print(f"Title: {reader.metadata.title}")
print(f"Author: {reader.metadata.author}")
print(f"Subject: {reader.metadata.subject}")
print(f"Creator: {reader.metadata.creator}")
print(f"Producer: {reader.metadata.producer}")
print(f"Encrypted: {reader.is_encrypted}")
print(f"Pages: {len(reader.pages)}")

# Get page dimensions
for i, page in enumerate(reader.pages):
    box = page.mediabox
    print(f"Page {i+1}: {float(box.width)} x {float(box.height)} pts")
```

### Method 3: pdfinfo (CLI - poppler-utils)
```bash
pdfinfo document.pdf
# Output: Title, Author, Creator, Producer, Page size, Pages, etc.

# Get page dimensions for all pages
pdfinfo -box document.pdf
```

---

## Batch Processing Pattern

```python
import os
from pathlib import Path
import pdfplumber

pdf_dir = "input/"
output_dir = "output/"

for pdf_file in Path(pdf_dir).glob("*.pdf"):
    print(f"Processing {pdf_file.name}...")
    try:
        with pdfplumber.open(pdf_file) as pdf:
            all_text = ""
            for page_num, page in enumerate(pdf.pages):
                all_text += f"\n--- Page {page_num+1} ---\n"
                all_text += page.extract_text()
            
            # Save extracted text
            output_file = Path(output_dir) / (pdf_file.stem + "_extracted.txt")
            output_file.write_text(all_text, encoding="utf-8")
            print(f"✓ Saved to {output_file}")
    except Exception as e:
        print(f"✗ Error: {e}")
```

---

## OCR Batch Processing

```python
import os
from pathlib import Path
from pdf2image import convert_from_path
import pytesseract

pdf_dir = "scans/"
output_dir = "ocr_output/"

for pdf_file in Path(pdf_dir).glob("*.pdf"):
    print(f"OCR processing {pdf_file.name}...")
    try:
        images = convert_from_path(pdf_file, dpi=200)
        extracted_text = ""
        
        for page_num, image in enumerate(images):
            text = pytesseract.image_to_string(image, lang='eng+ind')
            extracted_text += f"\n--- Page {page_num + 1} ---\n{text}"
        
        output_file = Path(output_dir) / (pdf_file.stem + "_ocr.txt")
        output_file.write_text(extracted_text, encoding="utf-8")
        print(f"✓ OCR saved to {output_file}")
    except Exception as e:
        print(f"✗ Error: {e}")
```

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| No text extracted | PDF is image-based | Use OCR (pytesseract + pdf2image) |
| Layout lost | Text extraction flattens structure | Use `extract_text_lines()` or `extract_words()` and group by `top` / `x0` |
| Tables not found | Complex formatting | Try manual `settings` or use crop regions |
| OCR too slow | High DPI | Reduce to 200 DPI or preprocess images with OpenCV |
| Memory error | Huge PDF | Process page-by-page, don't load all at once |
| Encoding issues | Non-ASCII text | Specify `encoding="utf-8"` in file write |
| pdf2image fails | Poppler not installed | Install `poppler-utils` system package |
| OCR accuracy low | Noisy/skewed scans | Preprocess with OpenCV (deskew, threshold, denoise) |
| Wrong column order | pdfplumber merges columns | Use `extract_words()` and sort by x-coordinate |
