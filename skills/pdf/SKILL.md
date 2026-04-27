---
name: pdf-agent
description: Handle PDF document operations—read, extract, transform, and create. Use this skill whenever the user needs to merge/split/rotate PDFs, extract text with layout awareness, perform OCR on scanned documents, extract tables/images, fill forms, or generate PDFs from data. Covers text extraction, batch transformations, metadata handling, and visual document generation.
---

# PDF Document Agent

Sub-agent skill for comprehensive PDF manipulation: reading, extraction, transformation, and creation.

## Quick Reference

| Task | Primary Tool | Secondary | Use When |
|------|------------|-----------|----------|
| Merge/split/rotate | `pypdf` | `qpdf` | Batch ops, preserve layout |
| Text extraction | `pdfplumber` | `pypdf` | Layout matters (tables, columns) |
| OCR (scans) | `pytesseract` + `pdf2image` | `poppler` | Scanned PDFs, poor image quality |
| Extract tables | `pdfplumber` | `camelot` | Structured data, complex layouts |
| Extract images | `pdfplumber`, `pypdf` | `pdf2image` | Embedded images, page rasterization |
| Create/generate | `reportlab` | `pdf-lib` (Node) | Programmatic PDFs, invoices, certificates |
| Fill forms | `pdf-lib` (Node) | `pypdf` | AcroForm fields |
| System-level ops | `qpdf`, `poppler-utils` | — | No Python overhead, large batch |

---

## Workflow by Category

### 1. TEXT EXTRACTION & OCR

**Use `pdfplumber` (default)** for layout-aware text extraction:
- Preserves spatial structure (tables, columns, headers)
- Handles rotated text, multi-column layouts
- Outputs plain text or structured JSON

**Use `pytesseract` + `pdf2image` (for scans):**
- `pdf2image` rasterizes pages to PNG/JPG
- `pytesseract` applies OCR character recognition
- Slower but works on image-based PDFs

**Example: Extract text preserving layout**
```python
import pdfplumber

with pdfplumber.open("document.pdf") as pdf:
    for page in pdf.pages:
        text = page.extract_text()  # Layout-aware
        blocks = page.extract_blocks()  # Structured blocks
        tables = page.extract_tables()  # Table data as lists
```

**Example: OCR a scanned PDF**
```python
from pdf2image import convert_from_path
import pytesseract
from PIL import Image

# Rasterize PDF pages
images = convert_from_path("scan.pdf", dpi=300)

for i, img in enumerate(images):
    text = pytesseract.image_to_string(img, lang='eng')
    print(f"Page {i+1}: {text}")
```

**Metadata extraction:**
```python
with pdfplumber.open("doc.pdf") as pdf:
    print(f"Title: {pdf.metadata.get('Title')}")
    print(f"Pages: {len(pdf.pages)}")
```

---

### 2. TRANSFORMATION (merge, split, rotate)

**Use `pypdf` (Python)** for programmatic control:
- Merge multiple PDFs
- Split by page range or bookmark
- Rotate pages, compress, add metadata
- Fast, no external dependencies

**Use `qpdf` (CLI)** for batch operations:
- System-level efficiency
- Better compression sometimes
- When Python overhead unwanted

**Example: Merge & rotate**
```python
from pypdf import PdfWriter

writer = PdfWriter()

# Add file 1
with open("part1.pdf", "rb") as f:
    reader = PdfReader(f)
    for page in reader.pages:
        writer.add_page(page)

# Add file 2, rotated
with open("part2.pdf", "rb") as f:
    reader = PdfReader(f)
    for page in reader.pages:
        page.rotate(90)  # Rotate 90° clockwise
        writer.add_page(page)

with open("merged.pdf", "wb") as f:
    writer.write(f)
```

**Example: Split every N pages**
```python
from pypdf import PdfReader, PdfWriter

reader = PdfReader("large.pdf")
chunk_size = 10

for i in range(0, len(reader.pages), chunk_size):
    writer = PdfWriter()
    for j in range(i, min(i + chunk_size, len(reader.pages))):
        writer.add_page(reader.pages[j])
    
    with open(f"chunk_{i//chunk_size + 1}.pdf", "wb") as f:
        writer.write(f)
```

**Example: Extract page range**
```python
reader = PdfReader("doc.pdf")
writer = PdfWriter()

# Pages 5-10 only
for page_num in range(4, 10):  # 0-indexed
    writer.add_page(reader.pages[page_num])

with open("extracted.pdf", "wb") as f:
    writer.write(f)
```

---

### 3. TABLE & IMAGE EXTRACTION

**Tables:** `pdfplumber.extract_tables()` returns list of lists (grid format)

**Example: Extract all tables to CSV**
```python
import pdfplumber
import csv

with pdfplumber.open("report.pdf") as pdf:
    for page_num, page in enumerate(pdf.pages):
        tables = page.extract_tables()
        for table_idx, table in enumerate(tables):
            with open(f"table_p{page_num+1}_t{table_idx+1}.csv", "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerows(table)
```

**Images:** Extract embedded images
```python
from pypdf import PdfReader

reader = PdfReader("doc.pdf")
for page_idx, page in enumerate(reader.pages):
    image_list = page.get_images()
    for img_idx, img_id in enumerate(image_list):
        obj = reader.get_object(img_id)
        data = obj.get_data()
        with open(f"img_p{page_idx+1}_{img_idx+1}.png", "wb") as f:
            f.write(data)
```

---

### 4. PDF CREATION & GENERATION

**Use `reportlab` (Python)** for programmatic PDF creation:
- Canvas-based drawing (shapes, text, images, tables)
- Ideal for invoices, certificates, reports, labels
- Full control over layout

**Use `pdf-lib` (Node.js)** for:
- Form filling (AcroForm fields)
- Lightweight page manipulation
- Browser/Node interop

**Example: Generate invoice PDF**
```python
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from datetime import datetime

c = canvas.Canvas("invoice.pdf", pagesize=letter)
width, height = letter

# Header
c.setFont("Helvetica-Bold", 24)
c.drawString(1*inch, height - 1*inch, "INVOICE")

# Date
c.setFont("Helvetica", 10)
c.drawString(1*inch, height - 1.5*inch, f"Date: {datetime.now().strftime('%Y-%m-%d')}")

# Invoice details table
data = [
    ["Item", "Qty", "Price", "Total"],
    ["Widget A", "10", "$5.00", "$50.00"],
    ["Widget B", "5", "$10.00", "$50.00"],
]

from reportlab.platypus import Table, TableStyle
from reportlab.lib import colors

table = Table(data, colWidths=[2*inch, 1*inch, 1.5*inch, 1.5*inch])
table.setStyle(TableStyle([
    ("BACKGROUND", (0,0), (-1,0), colors.grey),
    ("TEXTCOLOR", (0,0), (-1,0), colors.whitesmoke),
    ("ALIGN", (0,0), (-1,-1), "CENTER"),
    ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
    ("FONTSIZE", (0,0), (-1,0), 12),
    ("BOTTOMPADDING", (0,0), (-1,0), 12),
    ("GRID", (0,0), (-1,-1), 1, colors.black),
]))

c.save()
```

**Example: Fill PDF form (Node.js)**
```javascript
const { PDFDocument } = require('pdf-lib');
const fs = require('fs');

async function fillForm() {
  const pdfBytes = fs.readFileSync('form.pdf');
  const pdfDoc = await PDFDocument.load(pdfBytes);
  const form = pdfDoc.getForm();
  
  // Fill text fields
  form.getTextField('name').setText('John Doe');
  form.getTextField('email').setText('john@example.com');
  form.getCheckBox('agree').check();
  
  const filledPdf = await pdfDoc.save();
  fs.writeFileSync('form_filled.pdf', filledPdf);
}

fillForm();
```

---

## System Tools Reference

### qpdf (CLI)
Fast, minimal overhead. Use for large batch operations.

```bash
# Merge
qpdf --empty --pages file1.pdf file2.pdf -- output.pdf

# Split (extract pages 1-10)
qpdf input.pdf --pages . 1-10 -- output.pdf

# Rotate pages
qpdf input.pdf --rotate=90:1-5 -- output.pdf  # Rotate pages 1-5

# Decrypt (remove password)
qpdf --password=secret input.pdf output.pdf
```

### poppler-utils
Contains `pdftotext`, `pdftoppm`, `pdfimages`, etc.

```bash
# Extract text (simple)
pdftotext document.pdf output.txt

# Convert to images
pdftoppm document.pdf page -png  # Outputs page-1.png, page-2.png, ...

# Extract images
pdfimages document.pdf image  # Outputs image-*.png
```

---

## Common Patterns

### Batch OCR multiple files
```python
import os
from pathlib import Path
from pdf2image import convert_from_path
import pytesseract

pdf_dir = "scans/"
for pdf_file in Path(pdf_dir).glob("*.pdf"):
    print(f"Processing {pdf_file}...")
    images = convert_from_path(pdf_file, dpi=200)
    extracted_text = ""
    
    for page_num, image in enumerate(images):
        text = pytesseract.image_to_string(image)
        extracted_text += f"\n--- Page {page_num + 1} ---\n{text}"
    
    with open(pdf_file.stem + "_ocr.txt", "w") as f:
        f.write(extracted_text)
```

### Conditional rotation (rotate only portrait pages)
```python
from pypdf import PdfReader, PdfWriter

reader = PdfReader("mixed.pdf")
writer = PdfWriter()

for page in reader.pages:
    # Get page dimensions
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)
    
    # If portrait (height > width), rotate
    if height > width:
        page.rotate(90)
    
    writer.add_page(page)

with open("normalized.pdf", "wb") as f:
    writer.write(f)
```

### Extract text + preserve structure (markdown-like)
```python
import pdfplumber

with pdfplumber.open("doc.pdf") as pdf:
    for page_num, page in enumerate(pdf.pages, 1):
        print(f"# Page {page_num}\n")
        
        # Extract blocks (preserves hierarchy)
        blocks = page.extract_blocks()
        for block in blocks:
            if block.get('x0') < 100:  # Left margin = heading
                print(f"## {block['text']}\n")
            else:
                print(f"{block['text']}\n")
```

---

## Error Handling Checklist

| Scenario | Error | Solution |
|----------|-------|----------|
| Corrupted PDF | `pypdf.errors.PdfReadError` | Use `qpdf --fix-qdf` to repair |
| Encrypted/password-protected | `PdfReadError: File is encrypted` | Pass `password=""` to PdfReader |
| OCR fails (no tesseract) | `pytesseract.TesseractNotFoundError` | Install system `tesseract-ocr` package |
| Poor OCR quality | Low accuracy | Increase DPI in `convert_from_path(dpi=300+)` |
| Huge PDF (slow merge) | Timeout | Use `qpdf` CLI instead of `pypdf` |
| Tables not detected | Empty result | Check `extraction_settings` in `pdfplumber` or use manual coordinates |

---

## Recommended Flow

1. **User request** → Identify task category (extract, transform, create, OCR)
2. **Choose tool** → Use quick-reference table above
3. **Execute** → Write minimal, focused script for the task
4. **Output** → Save results to `/mnt/user-data/outputs/` if file-based
5. **Report** → Summary of what was done + file location/size

**For complex requests** (multi-step):
- Break into sequential operations
- Re-read intermediate files to validate structure
- Report checkpoint progress

---

## Notes

- **pdfplumber** is superior for text extraction when layout matters; falls back to `pypdf` for metadata-only reads
- **reportlab** output is always clean; use for generated/templated PDFs
- **pytesseract** quality depends on DPI and image preprocessing—experiment with 200-300 DPI for balance
- **qpdf** compression (`--compress-streams`) can reduce file size 20-50% with no quality loss
- For **very large PDFs (>1GB)**, process page-by-page in loops rather than loading entire file
