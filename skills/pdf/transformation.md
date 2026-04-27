# PDF Transformation Operations

## Merge Operations

### Simple Merge (pypdf)
```python
from pypdf import PdfReader, PdfWriter

writer = PdfWriter()

# Add multiple files in order
for filename in ["part1.pdf", "part2.pdf", "part3.pdf"]:
    reader = PdfReader(filename)
    for page in reader.pages:
        writer.add_page(page)

with open("merged.pdf", "wb") as f:
    writer.write(f)
```

### Merge with Compression & Metadata
```python
from pypdf import PdfReader, PdfWriter

writer = PdfWriter()
# ... add pages ...

with open("merged.pdf", "wb") as f:
    writer.write(f)
    writer.add_metadata({
        "/Title": "Merged Document",
        "/Author": "Script",
        "/Subject": "Combined PDF",
    })
```

### Merge with Page Bookmarks
```python
from pypdf import PdfReader, PdfWriter

writer = PdfWriter()

files_with_labels = [
    ("chapter1.pdf", "Chapter 1"),
    ("chapter2.pdf", "Chapter 2"),
    ("chapter3.pdf", "Chapter 3"),
]

for filename, label in files_with_labels:
    reader = PdfReader(filename)
    start_page = len(writer.pages)
    for page in reader.pages:
        writer.add_page(page)
    # Add bookmark for this section
    writer.add_outline_item(label, start_page)

with open("book.pdf", "wb") as f:
    writer.write(f)
```

### Batch Merge (all PDFs in directory)
```python
from pypdf import PdfReader, PdfWriter
from pathlib import Path
import os

output_file = "all_merged.pdf"
writer = PdfWriter()

# Process PDFs in alphabetical order
for pdf_file in sorted(Path("input/").glob("*.pdf")):
    print(f"Adding {pdf_file.name}...")
    reader = PdfReader(pdf_file)
    for page in reader.pages:
        writer.add_page(page)

with open(output_file, "wb") as f:
    writer.write(f)
print(f"✓ Merged {len(writer.pages)} pages into {output_file}")
```

### CLI (qpdf - faster for large batches)
```bash
# Merge two files
qpdf --empty --pages file1.pdf file2.pdf file3.pdf -- merged.pdf

# Merge with compression
qpdf --empty --pages file1.pdf file2.pdf -- merged.pdf --compress-streams=y

# Merge specific pages from each file
qpdf --empty --pages file1.pdf 1-5 file2.pdf 3-10 -- merged.pdf
```

---

## Split Operations

### Split Every N Pages (pypdf)
```python
from pypdf import PdfReader, PdfWriter

reader = PdfReader("large.pdf")
chunk_size = 10  # Split into 10-page chunks

for i in range(0, len(reader.pages), chunk_size):
    writer = PdfWriter()
    end = min(i + chunk_size, len(reader.pages))
    
    for page_num in range(i, end):
        writer.add_page(reader.pages[page_num])
    
    # Filename: chunk_1.pdf, chunk_2.pdf, ...
    output_file = f"chunk_{i//chunk_size + 1}.pdf"
    with open(output_file, "wb") as f:
        writer.write(f)
    print(f"✓ {output_file} ({end-i} pages)")
```

### Extract Specific Pages
```python
from pypdf import PdfReader, PdfWriter

reader = PdfReader("document.pdf")
writer = PdfWriter()

# Extract pages 5-15 (0-indexed: 4-14)
for page_num in range(4, 15):
    writer.add_page(reader.pages[page_num])

with open("pages_5-15.pdf", "wb") as f:
    writer.write(f)
```

### Split by Bookmark (pypdf)
```python
from pypdf import PdfReader, PdfWriter

reader = PdfReader("document.pdf")
outline = reader.get_outline()

if outline:
    for i, bookmark in enumerate(outline):
        writer = PdfWriter()
        # Add pages from bookmark[0] to next bookmark
        start_page = reader.get_destination_page_number(bookmark)
        end_page = reader.get_destination_page_number(outline[i+1]) if i+1 < len(outline) else len(reader.pages)
        
        for page_num in range(start_page, end_page):
            writer.add_page(reader.pages[page_num])
        
        with open(f"section_{i+1}.pdf", "wb") as f:
            writer.write(f)
```

### Split into Individual Pages
```python
from pypdf import PdfReader, PdfWriter

reader = PdfReader("document.pdf")
for i, page in enumerate(reader.pages):
    writer = PdfWriter()
    writer.add_page(page)
    with open(f"page_{i+1}.pdf", "wb") as f:
        writer.write(f)
```

### CLI (qpdf)
```bash
# Extract pages 1-10
qpdf input.pdf --pages . 1-10 -- output.pdf

# Extract pages 5-15 and 20-25
qpdf input.pdf --pages . 5-15 20-25 -- output.pdf

# All pages except 1-5
qpdf input.pdf --pages . 6-z -- output.pdf  # z = last page

# Split into individual pages
qpdf --split-pages input.pdf output_prefix
```

---

## Rotate Operations

### Rotate Specific Pages (pypdf)
```python
from pypdf import PdfReader, PdfWriter

reader = PdfReader("document.pdf")
writer = PdfWriter()

for i, page in enumerate(reader.pages):
    # Rotate every other page 90° clockwise
    if i % 2 == 1:
        page.rotate(90)
    writer.add_page(page)

with open("rotated.pdf", "wb") as f:
    writer.write(f)
```

### Smart Rotate (normalize portrait/landscape)
```python
from pypdf import PdfReader, PdfWriter

reader = PdfReader("mixed_orientation.pdf")
writer = PdfWriter()

for page in reader.pages:
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)
    
    # If portrait (height > width), rotate to landscape
    if height > width:
        page.rotate(90)
    
    writer.add_page(page)

with open("normalized.pdf", "wb") as f:
    writer.write(f)
print("✓ All pages normalized to landscape")
```

### Rotate by Page Number
```python
from pypdf import PdfReader, PdfWriter

reader = PdfReader("document.pdf")
writer = PdfWriter()

# Pages to rotate (1-indexed in config, 0-indexed in code)
pages_to_rotate = {2, 5, 10}  # Rotate pages 2, 5, 10

for i, page in enumerate(reader.pages):
    if (i + 1) in pages_to_rotate:
        page.rotate(90)
    writer.add_page(page)

with open("rotated.pdf", "wb") as f:
    writer.write(f)
```

### CLI (qpdf)
```bash
# Rotate pages 1-5 by 90° clockwise
qpdf input.pdf --rotate=90:1-5 -- output.pdf

# Rotate all pages 180°
qpdf input.pdf --rotate=180 -- output.pdf

# Different rotations for different page ranges
qpdf input.pdf --rotate=90:1-3 --rotate=180:4-5 -- output.pdf
```

---

## Compress & Optimize

### Compress with qpdf
```bash
# Basic compression
qpdf --compress-streams=y input.pdf output.pdf

# Flatten form fields + compress
qpdf --flatten-forms --compress-streams=y input.pdf output.pdf

# Linearize (optimize for web viewing)
qpdf --linearize input.pdf output.pdf

# Remove duplicate objects
qpdf --optimize-images input.pdf output.pdf

# Maximum compression
qpdf --compress-streams=y --object-streams=generate input.pdf output.pdf
```

### Compress with pypdf
```python
from pypdf import PdfReader, PdfWriter

reader = PdfReader("large.pdf")
writer = PdfWriter()

for page in reader.pages:
    writer.add_page(page)

# Add metadata
writer.add_metadata({
    "/Title": "Compressed Document",
    "/Author": "PDF Agent",
})

with open("compressed.pdf", "wb") as f:
    writer.write(f)

# Compare sizes
import os
original_size = os.path.getsize("large.pdf")
compressed_size = os.path.getsize("compressed.pdf")
reduction = (1 - compressed_size/original_size) * 100
print(f"Original: {original_size/1024:.1f}KB → Compressed: {compressed_size/1024:.1f}KB ({reduction:.1f}% reduction)")
```

---

## Encryption & Decryption

### Encrypt PDF (pypdf)
```python
from pypdf import PdfReader, PdfWriter

reader = PdfReader("document.pdf")
writer = PdfWriter()

for page in reader.pages:
    writer.add_page(page)

# Encrypt with password
writer.encrypt(user_password="view123", owner_password="admin456")

with open("encrypted.pdf", "wb") as f:
    writer.write(f)
```

### Decrypt PDF
```python
from pypdf import PdfReader, PdfWriter

reader = PdfReader("encrypted.pdf", password="view123")
writer = PdfWriter()

for page in reader.pages:
    writer.add_page(page)

with open("decrypted.pdf", "wb") as f:
    writer.write(f)
```

### CLI (qpdf)
```bash
# Decrypt (remove password)
qpdf --password=secret input.pdf output.pdf

# Encrypt with 256-bit AES
qpdf --encrypt user_password owner_password 256 -- input.pdf output.pdf
```

---

## Watermark & Stamp

### Add Text Watermark
```python
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import io

# Create watermark PDF
watermark_buffer = io.BytesIO()
c = canvas.Canvas(watermark_buffer, pagesize=letter)
width, height = letter

c.setFont("Helvetica-Bold", 60)
c.setFillColor((0.7, 0.7, 0.7, alpha=0.3))  # Semi-transparent
c.translate(width/2, height/2)
c.rotate(45)
c.drawCentredString(0, 0, "CONFIDENTIAL")

c.save()
watermark_buffer.seek(0)

# Apply watermark to each page
watermark_reader = PdfReader(watermark_buffer)
watermark_page = watermark_reader.pages[0]

reader = PdfReader("document.pdf")
writer = PdfWriter()

for page in reader.pages:
    page.merge_page(watermark_page)
    writer.add_page(page)

with open("watermarked.pdf", "wb") as f:
    writer.write(f)
```

### Add Page Numbers
```python
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import io

reader = PdfReader("document.pdf")
total_pages = len(reader.pages)
writer = PdfWriter()

for i, page in enumerate(reader.pages):
    # Create page number overlay
    overlay_buffer = io.BytesIO()
    c = canvas.Canvas(overlay_buffer, pagesize=letter)
    width, height = letter
    c.setFont("Helvetica", 10)
    c.drawCentredString(width/2, 0.5*72, f"Page {i+1} of {total_pages}")
    c.save()
    overlay_buffer.seek(0)
    
    # Merge overlay
    overlay_reader = PdfReader(overlay_buffer)
    page.merge_page(overlay_reader.pages[0])
    writer.add_page(page)

with open("numbered.pdf", "wb") as f:
    writer.write(f)
```

---

## Combined Operations

### Merge, then rotate, then compress
```python
from pypdf import PdfReader, PdfWriter

# Step 1: Merge
writer = PdfWriter()
for filename in ["file1.pdf", "file2.pdf"]:
    reader = PdfReader(filename)
    for page in reader.pages:
        writer.add_page(page)

# Step 2: Rotate pages 1-5
for i in range(min(5, len(writer.pages))):
    writer.pages[i].rotate(90)

# Step 3: Write (compression is automatic)
with open("merged_rotated.pdf", "wb") as f:
    writer.write(f)
```

### Extract section, rotate, add to another PDF
```python
from pypdf import PdfReader, PdfWriter

# Extract pages 10-20 from source
reader_src = PdfReader("large_document.pdf")
reader_base = PdfReader("base_document.pdf")

writer = PdfWriter()

# Add all pages from base
for page in reader_base.pages:
    writer.add_page(page)

# Add rotated pages from source
for page_num in range(9, 20):  # 0-indexed
    page = reader_src.pages[page_num]
    page.rotate(90)
    writer.add_page(page)

with open("combined.pdf", "wb") as f:
    writer.write(f)
```

### PDF to images → process → back to PDF
```python
from pdf2image import convert_from_path
from pypdf import PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import tempfile, os

# Step 1: Convert PDF to images
images = convert_from_path("input.pdf", dpi=200)

# Step 2: Process each image (e.g., with OpenCV)
import cv2
import numpy as np

temp_files = []
for i, img in enumerate(images):
    # Process image (e.g., add watermark, enhance, etc.)
    arr = np.array(img)
    # ... do processing ...
    processed = Image.fromarray(arr)
    
    temp_path = f"temp_page_{i}.png"
    processed.save(temp_path)
    temp_files.append(temp_path)

# Step 3: Combine processed images back into PDF
writer = PdfWriter()
for temp_path in temp_files:
    # Create a single-page PDF from each image
    img_pdf_path = temp_path.replace(".png", ".pdf")
    c = canvas.Canvas(img_pdf_path, pagesize=letter)
    c.drawImage(temp_path, 0, 0, width=612, height=792)
    c.save()
    
    reader = PdfReader(img_pdf_path)
    writer.add_page(reader.pages[0])

with open("processed.pdf", "wb") as f:
    writer.write(f)

# Cleanup
for f in temp_files:
    os.remove(f)
    os.remove(f.replace(".png", ".pdf"))
```

---

## Convert PDF to Other Formats (libreoffice)

```bash
# PDF to DOCX
libreoffice --headless --convert-to docx document.pdf --outdir output/

# PDF to HTML
libreoffice --headless --convert-to html document.pdf --outdir output/
```

**Note:** Libreoffice conversion is best-effort. Complex layouts may not convert perfectly.

---

## Performance Comparison

| Task | pypdf | qpdf | Speed |
|------|-------|------|-------|
| Merge 10x10MB PDFs | ~2sec | ~0.5sec | qpdf 4x faster |
| Split 100-page PDF | ~1sec | ~0.3sec | qpdf 3x faster |
| Rotate 1000 pages | ~3sec | N/A | pypdf only |
| Compress PDF | ~2sec | ~0.5sec | qpdf better |
| Encrypt PDF | ~1sec | ~0.5sec | qpdf slightly faster |

**Rule of thumb:**
- **pypdf:** Flexibility, programmatic control, moderate batches (≤100 files)
- **qpdf:** Large batches, compression, encryption, system efficiency, no Python overhead
- **libreoffice:** Format conversion (PDF ↔ DOCX/XLSX/PPTX)

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| File larger after merge | No compression | Add `--compress-streams=y` in qpdf |
| Rotated text looks odd | Incorrect rotation value | Use 90, 180, 270 (not arbitrary angles) |
| Merge fails silently | Incompatible PDF versions | Try qpdf instead of pypdf |
| Memory spike on large PDF | Loading entire file | Use qpdf CLI or pypdf streaming mode |
| Pages out of order after merge | Iterator issue | Explicitly iterate `range()` |
| Encrypted PDF can't be read | Password required | Pass `password=` to PdfReader |
| Watermark alignment off | Coordinate system mismatch | Remember: origin is bottom-left in PDF |
| Libreoffice conversion fails | Headless mode issue | Ensure no other LO instance running |
