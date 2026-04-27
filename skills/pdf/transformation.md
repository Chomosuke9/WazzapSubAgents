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

### Merge with Compression
```python
from pypdf import PdfWriter

writer = PdfWriter()
# ... add pages ...

with open("merged.pdf", "wb") as f:
    writer.write(f)
    writer.add_metadata({
        "/Title": "Merged Document",
        "/Author": "Script"
    })
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

### CLI (qpdf)
```bash
# Extract pages 1-10
qpdf input.pdf --pages . 1-10 -- output.pdf

# Extract pages 5-15 and 20-25
qpdf input.pdf --pages . 5-15 20-25 -- output.pdf

# All pages except 1-5
qpdf input.pdf --pages . 6-z -- output.pdf  # z = last page
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

---

## Performance Comparison

| Task | pypdf | qpdf | Speed |
|------|-------|------|-------|
| Merge 10×10MB PDFs | ~2sec | ~0.5sec | qpdf 4× faster |
| Split 100-page PDF | ~1sec | ~0.3sec | qpdf 3× faster |
| Rotate 1000 pages | ~3sec | N/A | pypdf only |
| Compress PDF | ~2sec | ~0.5sec | qpdf better |

**Rule of thumb:**
- **pypdf:** Flexibility, programmatic control, moderate batches (≤100 files)
- **qpdf:** Large batches, compression, system efficiency, no Python overhead

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| File larger after merge | No compression | Add `--compress-streams=y` in qpdf |
| Rotated text looks odd | Incorrect rotation value | Use 90, 180, 270 (not arbitrary angles) |
| Merge fails silently | Incompatible PDF versions | Try qpdf instead of pypdf |
| Memory spike on large PDF | Loading entire file | Use qpdf CLI or pypdf streaming mode |
| Pages out of order after merge | Iterator issue | Explicitly iterate `range()` |
