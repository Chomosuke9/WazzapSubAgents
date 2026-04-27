# PPTX Extraction & Conversion Operations

## Content Extraction

### Extract Text with markitdown
```python
from markitdown import MarkItDown

md = MarkItDown()
result = md.convert("presentation.pptx")
text_content = result.text_content
print(text_content)

# Save to Markdown file
with open("presentation_content.md", "w", encoding="utf-8") as f:
    f.write(text_content)
```

### Extract Text with python-pptx (More Control)
```python
from pptx import Presentation

prs = Presentation("presentation.pptx")

all_text = []
for slide_idx, slide in enumerate(prs.slides):
    slide_text = []
    slide_text.append(f"## Slide {slide_idx + 1}\n")
    
    for shape in slide.shapes:
        if shape.has_text_frame:
            for paragraph in shape.text_frame.paragraphs:
                text = paragraph.text.strip()
                if text:
                    # Detect heading level based on font size
                    if paragraph.runs:
                        font_size = paragraph.runs[0].font.size
                        if font_size and font_size >= 200000:  # >= 16pt
                            slide_text.append(f"### {text}")
                        else:
                            slide_text.append(text)
                    else:
                        slide_text.append(text)
        
        # Extract table content
        if shape.has_table:
            slide_text.append("\n| " + " | ".join(
                cell.text for cell in shape.table.rows[0].cells
            ) + " |")
            slide_text.append("| " + " | ".join("---" for _ in shape.table.columns) + " |")
            for row in shape.table.rows[1:]:
                slide_text.append("| " + " | ".join(
                    cell.text for cell in row.cells
                ) + " |")
    
    all_text.append("\n".join(slide_text))

full_text = "\n\n".join(all_text)
with open("extracted_content.md", "w", encoding="utf-8") as f:
    f.write(full_text)
print("✓ Content extracted to Markdown")
```

### Extract All Text (Simple)
```python
from pptx import Presentation

prs = Presentation("presentation.pptx")

for slide_idx, slide in enumerate(prs.slides):
    print(f"\n=== Slide {slide_idx + 1} ===")
    for shape in slide.shapes:
        if shape.has_text_frame:
            for paragraph in shape.text_frame.paragraphs:
                if paragraph.text.strip():
                    print(paragraph.text)
        if shape.has_table:
            for row in shape.table.rows:
                row_text = [cell.text for cell in row.cells]
                print(" | ".join(row_text))
```

### Extract Speaker Notes
```python
from pptx import Presentation

prs = Presentation("presentation.pptx")

for i, slide in enumerate(prs.slides):
    if slide.has_notes_slide:
        notes = slide.notes_slide.notes_text_frame.text.strip()
        if notes:
            print(f"Slide {i+1} Notes: {notes}")
```

### Extract Presentation Metadata
```python
from pptx import Presentation

prs = Presentation("presentation.pptx")

# Core properties
props = prs.core_properties
print(f"Title: {props.title}")
print(f"Author: {props.author}")
print(f"Subject: {props.subject}")
print(f"Created: {props.created}")
print(f"Modified: {props.last_modified_by}")
print(f"Category: {props.category}")
print(f"Comments: {props.comments}")

# Slide dimensions
print(f"Width: {prs.slide_width / 914400:.2f} inches")
print(f"Height: {prs.slide_height / 914400:.2f} inches")
print(f"Total Slides: {len(prs.slides)}")
```

---

## Image Extraction

### Extract All Images from PPTX
```python
from pptx import Presentation
from PIL import Image
import io
import os

prs = Presentation("presentation.pptx")
output_dir = "extracted_images/"
os.makedirs(output_dir, exist_ok=True)

img_count = 0
for slide_idx, slide in enumerate(prs.slides):
    for shape in slide.shapes:
        if shape.shape_type == 13:  # Picture type
            # Get the image blob
            image = shape.image
            image_bytes = image.blob
            content_type = image.content_type  # e.g., 'image/png', 'image/jpeg'
            
            # Determine extension
            ext = content_type.split("/")[-1]
            if ext == "jpeg":
                ext = "jpg"
            
            # Save image
            filename = f"{output_dir}slide{slide_idx+1}_img{img_count+1}.{ext}"
            with open(filename, "wb") as f:
                f.write(image_bytes)
            
            img_count += 1
            print(f"✓ Extracted: {filename}")

print(f"✓ Total images extracted: {img_count}")
```

### Extract and Process Images with Pillow
```python
from pptx import Presentation
from PIL import Image
import io, os

prs = Presentation("presentation.pptx")
output_dir = "thumbnails/"
os.makedirs(output_dir, exist_ok=True)

for slide_idx, slide in enumerate(prs.slides):
    for shape in slide.shapes:
        if shape.shape_type == 13:  # Picture type
            image_bytes = shape.image.blob
            img = Image.open(io.BytesIO(image_bytes))
            
            # Create thumbnail (max 300px wide)
            img.thumbnail((300, 300), Image.Resampling.LANCZOS)
            
            # Save thumbnail
            thumb_path = f"{output_dir}slide{slide_idx+1}_thumb.jpg"
            img.convert("RGB").save(thumb_path, "JPEG", quality=85)
            print(f"✓ Thumbnail: {thumb_path} ({img.width}x{img.height})")
```

---

## Format Conversion

### PPTX to PDF (libreoffice)
```bash
# Single file
libreoffice --headless --convert-to pdf presentation.pptx --outdir output/

# Batch convert
libreoffice --headless --convert-to pdf *.pptx --outdir output/

# With specific PDF options
libreoffice --headless --convert-to pdf:"calc_pdf_Export:{'PageRange':{'type':0,'value':''}}" presentation.pptx
```

```python
# Python wrapper
import subprocess
import os

def pptx_to_pdf(pptx_path, output_dir="."):
    """Convert PPTX to PDF using LibreOffice."""
    result = subprocess.run(
        ["libreoffice", "--headless", "--convert-to", "pdf",
         pptx_path, "--outdir", output_dir],
        capture_output=True, text=True, timeout=120
    )
    
    if result.returncode != 0:
        raise RuntimeError(f"LibreOffice conversion failed: {result.stderr}")
    
    # Expected output path
    base_name = os.path.splitext(os.path.basename(pptx_path))[0]
    pdf_path = os.path.join(output_dir, f"{base_name}.pdf")
    
    if os.path.exists(pdf_path):
        print(f"✓ PDF created: {pdf_path}")
        return pdf_path
    else:
        raise FileNotFoundError(f"PDF not found at {pdf_path}")

# Usage
pdf_path = pptx_to_pdf("presentation.pptx", "output/")
```

### PPTX to Images (libreoffice + pdftoppm)
```bash
# Step 1: Convert PPTX to PDF
libreoffice --headless --convert-to pdf presentation.pptx --outdir /tmp/

# Step 2: Convert PDF to PNG images (one per slide)
pdftoppm -png -r 200 /tmp/presentation.pdf output/slide

# Result: slide-1.png, slide-2.png, etc.
# -r 200 = 200 DPI (use 300 for high quality)
```

```python
# Python equivalent
import subprocess
import os
from pdf2image import convert_from_path

def pptx_to_images(pptx_path, output_dir=".", dpi=200, fmt="png"):
    """Convert PPTX to image files (one per slide)."""
    os.makedirs(output_dir, exist_ok=True)
    
    # Step 1: Convert to PDF
    pdf_path = pptx_to_pdf(pptx_path, "/tmp/")
    
    # Step 2: Convert PDF to images
    images = convert_from_path(pdf_path, dpi=dpi, fmt=fmt)
    
    image_paths = []
    for i, img in enumerate(images):
        path = os.path.join(output_dir, f"slide_{i+1}.{fmt}")
        img.save(path, fmt.upper())
        image_paths.append(path)
        print(f"✓ Image: {path}")
    
    # Cleanup
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
    
    return image_paths

# Usage
paths = pptx_to_images("presentation.pptx", "output/slides/", dpi=200)
```

### PPTX to HTML (libreoffice)
```bash
# Convert to HTML
libreoffice --headless --convert-to html presentation.pptx --outdir output/

# Note: Output quality varies; complex layouts may not convert well
```

### PPTX to DOCX (libreoffice)
```bash
# Convert to Word document
libreoffice --headless --convert-to docx presentation.pptx --outdir output/
```

---

## Batch Conversion

### Convert All PPTX Files in Directory to PDF
```python
import subprocess
import os
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor

def convert_pptx_to_pdf(pptx_path, output_dir):
    """Convert a single PPTX to PDF."""
    result = subprocess.run(
        ["libreoffice", "--headless", "--convert-to", "pdf",
         str(pptx_path), "--outdir", output_dir],
        capture_output=True, text=True, timeout=120
    )
    return result.returncode == 0

input_dir = "presentations/"
output_dir = "pdfs/"
os.makedirs(output_dir, exist_ok=True)

pptx_files = list(Path(input_dir).glob("*.pptx"))
print(f"Found {len(pptx_files)} PPTX files")

# Sequential (LibreOffice doesn't support parallel well)
for pptx_file in pptx_files:
    success = convert_pptx_to_pdf(pptx_file, output_dir)
    status = "✓" if success else "✗"
    print(f"{status} {pptx_file.name}")
```

### Batch Extract Text from All PPTX Files
```python
from markitdown import MarkItDown
from pathlib import Path
import os

md = MarkItDown()
input_dir = "presentations/"
output_dir = "markdown/"
os.makedirs(output_dir, exist_ok=True)

for pptx_file in Path(input_dir).glob("*.pptx"):
    try:
        result = md.convert(str(pptx_file))
        output_path = os.path.join(output_dir, f"{pptx_file.stem}.md")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result.text_content)
        print(f"✓ {pptx_file.name} → {output_path}")
    except Exception as e:
        print(f"✗ {pptx_file.name}: {e}")
```

---

## Image Processing for Presentations

### Create Thumbnail Grid from PPTX
```python
from pptx import Presentation
from PIL import Image
from pdf2image import convert_from_path
import subprocess, os, tempfile

def create_thumbnail_grid(pptx_path, output_path, cols=4, thumb_size=(240, 135)):
    """Create a thumbnail grid image from a PPTX file."""
    # Step 1: Convert to PDF
    temp_dir = tempfile.mkdtemp()
    subprocess.run([
        "libreoffice", "--headless", "--convert-to", "pdf",
        pptx_path, "--outdir", temp_dir
    ], capture_output=True)
    
    base_name = os.path.splitext(os.path.basename(pptx_path))[0]
    pdf_path = os.path.join(temp_dir, f"{base_name}.pdf")
    
    # Step 2: Convert PDF to images
    images = convert_from_path(pdf_path, dpi=150)
    
    # Step 3: Create thumbnails
    thumbs = []
    for img in images:
        img.thumbnail(thumb_size, Image.Resampling.LANCZOS)
        thumbs.append(img.convert("RGB"))
    
    if not thumbs:
        return None
    
    # Step 4: Arrange in grid
    rows = (len(thumbs) + cols - 1) // cols
    margin = 10
    grid_w = cols * thumb_size[0] + (cols + 1) * margin
    grid_h = rows * thumb_size[1] + (rows + 1) * margin
    
    grid = Image.new("RGB", (grid_w, grid_h), (255, 255, 255))
    
    for i, thumb in enumerate(thumbs):
        col = i % cols
        row = i // cols
        x = margin + col * (thumb_size[0] + margin)
        y = margin + row * (thumb_size[1] + margin)
        grid.paste(thumb, (x, y))
    
    grid.save(output_path, "PNG")
    
    # Cleanup
    os.remove(pdf_path)
    os.rmdir(temp_dir)
    
    print(f"✓ Thumbnail grid: {output_path}")
    return output_path

# Usage
create_thumbnail_grid("presentation.pptx", "thumbnails.png")
```

### Resize & Optimize Images for PPTX Insertion
```python
from PIL import Image
import os

def optimize_for_pptx(input_path, output_path, max_size=(1600, 900), quality=85):
    """
    Optimize an image for PPTX insertion:
    - Resize to fit within max_size
    - Convert RGBA to RGB (white bg)
    - Compress to reduce file size
    """
    img = Image.open(input_path)
    
    # Handle transparency
    if img.mode in ("RGBA", "LA"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "LA":
            img = img.convert("RGBA")
        background.paste(img, mask=img.split()[-1])
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")
    
    # Resize maintaining aspect ratio
    img.thumbnail(max_size, Image.Resampling.LANCZOS)
    
    # Save optimized
    ext = os.path.splitext(output_path)[1].lower()
    if ext in (".jpg", ".jpeg"):
        img.save(output_path, "JPEG", quality=quality, optimize=True)
    else:
        img.save(output_path, "PNG", optimize=True)
    
    size_kb = os.path.getsize(output_path) / 1024
    print(f"✓ Optimized: {output_path} ({size_kb:.0f}KB, {img.width}x{img.height})")
    return output_path

# Batch optimize
input_dir = "raw_images/"
output_dir = "optimized/"
os.makedirs(output_dir, exist_ok=True)

for img_file in os.listdir(input_dir):
    if img_file.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".webp")):
        optimize_for_pptx(
            os.path.join(input_dir, img_file),
            os.path.join(output_dir, img_file),
        )
```

---

## Complete Pipeline: Extract → Process → Report

```python
"""
Complete pipeline to extract PPTX content, process it, and generate a report.
"""
from pptx import Presentation
from markitdown import MarkItDown
from PIL import Image
import subprocess, os, tempfile
from pdf2image import convert_from_path

def analyze_presentation(pptx_path, output_dir="."):
    """Full analysis pipeline for a PPTX file."""
    os.makedirs(output_dir, exist_ok=True)
    report = []
    
    # 1. Basic Info
    prs = Presentation(pptx_path)
    props = prs.core_properties
    
    report.append(f"# Presentation Analysis: {os.path.basename(pptx_path)}\n")
    report.append(f"- **Author:** {props.author or 'N/A'}")
    report.append(f"- **Created:** {props.created or 'N/A'}")
    report.append(f"- **Slides:** {len(prs.slides)}")
    report.append(f"- **Dimensions:** {prs.slide_width/914400:.1f}\" x {prs.slide_height/914400:.1f}\"")
    
    # 2. Extract text content
    md = MarkItDown()
    result = md.convert(pptx_path)
    content_path = os.path.join(output_dir, "content.md")
    with open(content_path, "w", encoding="utf-8") as f:
        f.write(result.text_content)
    report.append(f"- **Content extracted:** {content_path}")
    
    # 3. Extract images
    img_dir = os.path.join(output_dir, "images")
    os.makedirs(img_dir, exist_ok=True)
    img_count = 0
    for slide_idx, slide in enumerate(prs.slides):
        for shape in slide.shapes:
            if shape.shape_type == 13:
                image_bytes = shape.image.blob
                ext = shape.image.content_type.split("/")[-1].replace("jpeg", "jpg")
                path = os.path.join(img_dir, f"slide{slide_idx+1}_img{img_count+1}.{ext}")
                with open(path, "wb") as f:
                    f.write(image_bytes)
                img_count += 1
    report.append(f"- **Images extracted:** {img_count}")
    
    # 4. Generate thumbnail grid
    try:
        temp_dir = tempfile.mkdtemp()
        subprocess.run([
            "libreoffice", "--headless", "--convert-to", "pdf",
            pptx_path, "--outdir", temp_dir
        ], capture_output=True, timeout=120)
        
        base_name = os.path.splitext(os.path.basename(pptx_path))[0]
        pdf_path = os.path.join(temp_dir, f"{base_name}.pdf")
        
        if os.path.exists(pdf_path):
            images = convert_from_path(pdf_path, dpi=100)
            thumbs = []
            for img in images:
                img.thumbnail((240, 135), Image.Resampling.LANCZOS)
                thumbs.append(img.convert("RGB"))
            
            if thumbs:
                cols = min(4, len(thumbs))
                rows = (len(thumbs) + cols - 1) // cols
                margin = 5
                grid_w = cols * 240 + (cols + 1) * margin
                grid_h = rows * 135 + (rows + 1) * margin
                grid = Image.new("RGB", (grid_w, grid_h), (255, 255, 255))
                
                for i, thumb in enumerate(thumbs):
                    col = i % cols
                    row = i // cols
                    x = margin + col * (240 + margin)
                    y = margin + row * (135 + margin)
                    grid.paste(thumb, (x, y))
                
                thumb_path = os.path.join(output_dir, "thumbnail_grid.png")
                grid.save(thumb_path, "PNG")
                report.append(f"- **Thumbnail grid:** {thumb_path}")
            
            os.remove(pdf_path)
    except Exception as e:
        report.append(f"- **Thumbnail generation failed:** {e}")
    
    # Write report
    report_path = os.path.join(output_dir, "analysis_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report))
    
    print(f"✓ Analysis complete: {report_path}")
    return report_path

# Usage
analyze_presentation("presentation.pptx", "analysis_output/")
```

---

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| markitdown returns empty | PPTX has images only | Use python-pptx to inspect shapes directly |
| LibreOffice hangs | Another instance running | Kill existing processes: `killall soffice.bin` |
| Images not extracted | Shape type mismatch | Check `shape.shape_type` values (13=Picture) |
| PDF conversion fails | Complex animations | Remove animations or use simplified layout |
| PDF to images fails | Poppler not installed | Install `poppler-utils` system package |
| Thumbnail grid empty | No slides in PPTX | Verify the file has valid content |
| Encoding issues | Non-ASCII characters | Always use `encoding="utf-8"` in file operations |
| Memory error on batch | Too many files at once | Process sequentially, clean up temp files |
