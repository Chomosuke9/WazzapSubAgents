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

### Strategy 2: Structured Block Extraction
**Best for:** Identifying headers, paragraphs, distinct sections
```python
with pdfplumber.open("file.pdf") as pdf:
    page = pdf.pages[0]
    blocks = page.extract_blocks()
    # blocks = [{"x0": ..., "top": ..., "text": "...", ...}, ...]
    for block in blocks:
        print(f"Block at ({block['x0']}, {block['top']}): {block['text']}")
```

### Strategy 3: OCR Scanned PDFs
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

**Language codes:** `eng`, `fra`, `deu`, `spa`, `hin`, `tha`, `jpn`, etc.

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
                print(f"Table {t_idx}: {len(table)} rows × {len(table[0])} cols")
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
                  f"size {img['width']}×{img['height']}")
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
import io
from PIL import Image

reader = PdfReader("doc.pdf")
for page_idx, page in enumerate(reader.pages):
    for obj_idx, obj in enumerate(page["/Resources"]["/XObject"].get_object().values()):
        if obj["/Subtype"] == "/Image":
            data = obj.get_data()
            image = Image.open(io.BytesIO(data))
            image.save(f"extracted_{page_idx}_{obj_idx}.png")
```

---

## Metadata Extraction

```python
import pdfplumber
from pypdf import PdfReader

# Method 1: pdfplumber (simpler)
with pdfplumber.open("doc.pdf") as pdf:
    meta = pdf.metadata
    print(f"Title: {meta.get('Title')}")
    print(f"Author: {meta.get('Author')}")
    print(f"Pages: {len(pdf.pages)}")

# Method 2: pypdf (more detailed)
reader = PdfReader("doc.pdf")
print(f"Title: {reader.metadata.title}")
print(f"Producer: {reader.metadata.producer}")
print(f"Encrypted: {reader.is_encrypted}")
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
            output_file.write_text(all_text)
            print(f"✓ Saved to {output_file}")
    except Exception as e:
        print(f"✗ Error: {e}")
```

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| No text extracted | PDF is image-based | Use OCR (pytesseract) |
| Layout lost | Text extraction flattens structure | Use `extract_blocks()` instead |
| Tables not found | Complex formatting | Try manual `settings` or use crop regions |
| OCR too slow | High DPI | Reduce to 200 DPI or preprocess images |
| Memory error | Huge PDF | Process page-by-page, don't load all at once |
| Encoding issues | Non-ASCII text | Specify `encoding="utf-8"` in file write |
