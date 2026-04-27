---
name: pptx-agent
description: |
  Create and edit PowerPoint presentations (.pptx) for any purpose using Node.js or Python. 
  Use this skill whenever you need to generate, modify, or customize PPTX files with slides, 
  text, images, charts, tables, shapes, or animations. 
  Provides code templates for direct execution in container environments. 
  Libraries: pptxgenjs (Node.js), python-pptx (Python), markitdown (extraction), 
  Pillow (image processing), libreoffice (conversion), pdftoppm (preview).
  Covers common scenarios: business presentations, pitch decks, reports, training slides, 
  photo galleries, and custom presentations. Always generate ready-to-use output files.
---

# PPTX Presentation Agent

Sub-agent skill for comprehensive PowerPoint manipulation: creation, editing, extraction, and conversion.

## Quick Reference

| Task | Primary Tool | Secondary | Use When |
|------|------------|-----------|----------|
| Create from scratch | `pptxgenjs` (Node.js) | `python-pptx` | New presentations, programmatic slides |
| Edit existing PPTX | `python-pptx` (Python) | — | Modify templates, add/remove slides |
| Extract text/content | `markitdown` (Python) | `python-pptx` | Convert slide content to Markdown |
| Image processing | `Pillow` (Python) | — | Thumbnails, resize, format conversion |
| Convert PPTX → PDF | `libreoffice` | — | Export for sharing, print-ready |
| Convert PDF → images | `pdftoppm` (CLI) | `pdf2image` | Preview/thumbnail generation |
| PPTX → images | `libreoffice` + `pdftoppm` | — | Slide previews, web thumbnails |

---

## Library Overview

### Node.js Libraries

| Library | Purpose | Key Features |
|---------|---------|--------------|
| `pptxgenjs` | Create presentations from scratch | Slides, text, images, charts, tables, shapes, animations |

### Python Libraries

| Library | Purpose | Key Features |
|---------|---------|--------------|
| `python-pptx` | Edit & manipulate PPTX | Modify templates, add slides, styling, placeholders |
| `markitdown` | Extract content to Markdown | Convert PPTX content to structured text |
| `Pillow` | Image processing | Thumbnails, resize, crop, format conversion |

### System Tools (CLI)

| Tool | Purpose | Key Features |
|------|---------|--------------|
| `libreoffice` | Format conversion | PPTX → PDF, DOCX, HTML; recalculate embedded charts |
| `pdftoppm` | PDF to image | Convert PDF preview to PNG/JPEG |

---

## Quick Decision Tree

**Use Node.js (`pptxgenjs`)** when:
- Creating presentation from scratch
- Need precise slide layout control
- Adding charts, tables, or complex shapes programmatically
- Performance is critical for large presentations
- Want clean, modern slide designs

**Use Python (`python-pptx`)** when:
- Editing existing .pptx file (read + modify + save)
- Working with slide templates/master layouts
- Manipulating placeholders, notes, or slide masters
- Python dependencies already available in container
- Need to batch-modify multiple presentations

---

## Detailed Documentation

This skill is organized into sub-documents for focused reference:

- **[creation.md](/skills/pptx/creation.md)** — Creating presentations from scratch with pptxgenjs and python-pptx
- **[editing.md](/skills/pptx/editing.md)** — Editing existing PPTX files, template manipulation, batch operations
- **[extraction.md](/skills/pptx/extraction.md)** — Content extraction, Markdown conversion, image processing, conversion

Read the relevant sub-document before implementing a solution.

---

## Common Presentation Templates

### 1. **Business Presentation / Pitch Deck**
```
Title slide (company name + tagline)
Problem / Opportunity
Solution / Product
Market Size / Traction
Business Model
Team
Financial Projections
Call to Action / Contact
```

### 2. **Report / Summary Presentation**
```
Title slide
Executive Summary
Key Metrics / KPIs
Detailed Findings (multiple slides)
Recommendations
Q&A / Discussion
```

### 3. **Training / Educational Slides**
```
Title + Learning Objectives
Agenda / Overview
Content slides (one concept per slide)
Practice / Examples
Summary / Key Takeaways
Resources / Next Steps
```

### 4. **Photo Gallery / Portfolio**
```
Cover slide
Photo slides (1-4 images per slide)
Captions / Descriptions
Closing slide
```

### 5. **Project Status Update**
```
Project Title + Date
Timeline / Milestones
Progress (completed, in-progress, upcoming)
Risks & Issues
Budget Status
Next Steps
```

### 6. **Academic / Research Presentation (Indonesian: Presentasi Makalah)**
```
Cover (title, author, institution)
Outline / Daftar Isi
Introduction / Pendahuluan
Methodology / Metodologi
Results / Hasil
Discussion / Pembahasan
Conclusion / Kesimpulan
References / Daftar Pustaka
```

---

## Workflow by Category

### 1. CREATE PRESENTATION FROM SCRATCH (pptxgenjs)

```javascript
const pptxgen = require("pptxgenjs");
const fs = require("fs");

const pptx = new pptxgen();

// Set presentation metadata
pptx.author = "Wazzap Agent";
pptx.company = "WazzapSubAgents";
pptx.subject = "Generated Presentation";
pptx.title = "My Presentation";

// --- Slide 1: Title ---
const slide1 = pptx.addSlide();
slide1.background = { color: "1B3A5C" };

slide1.addText("PRESENTATION TITLE", {
  x: 0.8, y: 1.5, w: 8.4, h: 1.5,
  fontSize: 36, fontFace: "Arial",
  color: "FFFFFF", bold: true,
  align: "center",
});

slide1.addText("Subtitle or Tagline", {
  x: 0.8, y: 3.2, w: 8.4, h: 0.8,
  fontSize: 18, fontFace: "Arial",
  color: "BDC3C7", align: "center",
});

slide1.addText("Author Name | Date", {
  x: 0.8, y: 6.5, w: 8.4, h: 0.5,
  fontSize: 12, fontFace: "Arial",
  color: "95A5A6", align: "center",
});

// --- Slide 2: Content ---
const slide2 = pptx.addSlide();
slide2.addText("Section Title", {
  x: 0.5, y: 0.3, w: 9, h: 0.8,
  fontSize: 28, fontFace: "Arial",
  color: "1B3A5C", bold: true,
});

slide2.addText([
  { text: "Bullet point 1\n", options: { bullet: true, fontSize: 16, color: "333333" } },
  { text: "Bullet point 2\n", options: { bullet: true, fontSize: 16, color: "333333" } },
  { text: "Bullet point 3", options: { bullet: true, fontSize: 16, color: "333333" } },
], {
  x: 0.8, y: 1.5, w: 8, h: 3.5,
  valign: "top",
});

// Save
pptx.writeFile({ fileName: "/output/presentation.pptx" })
  .then(() => console.log("✓ Presentation created"))
  .catch(err => console.error("Error:", err));
```

---

### 2. EDIT EXISTING PPTX (python-pptx)

```python
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

# Load existing presentation
prs = Presentation("template.pptx")

# Add a new slide with blank layout
slide_layout = prs.slide_layouts[6]  # Blank layout
slide = prs.slides.add_slide(slide_layout)

# Add text box
left = Inches(1)
top = Inches(1)
width = Inches(8)
height = Inches(1)

txBox = slide.shapes.add_textbox(left, top, width, height)
tf = txBox.text_frame
tf.word_wrap = True

p = tf.paragraphs[0]
p.text = "Hello from python-pptx!"
p.font.size = Pt(28)
p.font.bold = True
p.font.color.rgb = RGBColor(0x1B, 0x3A, 0x5C)
p.alignment = PP_ALIGN.CENTER

# Save
prs.save("/output/modified.pptx")
print("✓ Presentation updated")
```

---

### 3. EXTRACT CONTENT (markitdown)

```python
from markitdown import MarkItDown

md = MarkItDown()
result = md.convert("presentation.pptx")
text_content = result.text_content
print(text_content)

# Save extracted content
with open("presentation_content.md", "w", encoding="utf-8") as f:
    f.write(text_content)
```

---

### 4. CONVERT PPTX TO PDF (libreoffice)

```bash
libreoffice --headless --convert-to pdf presentation.pptx --outdir output/
```

### 5. GENERATE SLIDE PREVIEWS (libreoffice + pdftoppm)

```bash
# Step 1: Convert PPTX to PDF
libreoffice --headless --convert-to pdf presentation.pptx --outdir /tmp/

# Step 2: Convert PDF to images (one per slide)
pdftoppm -png -r 200 /tmp/presentation.pdf /tmp/slide_preview

# Result: slide_preview-1.png, slide_preview-2.png, etc.
```

```python
# Python equivalent for generating previews
import subprocess
import os

def generate_previews(pptx_path, output_dir, dpi=200):
    """Generate PNG previews for each slide of a PPTX file."""
    os.makedirs(output_dir, exist_ok=True)
    
    # Step 1: Convert to PDF
    pdf_path = os.path.join(output_dir, "temp.pdf")
    subprocess.run([
        "libreoffice", "--headless", "--convert-to", "pdf",
        pptx_path, "--outdir", output_dir
    ], check=True, capture_output=True)
    
    # Step 2: Convert PDF to images
    from pdf2image import convert_from_path
    images = convert_from_path(pdf_path, dpi=dpi)
    
    preview_paths = []
    for i, img in enumerate(images):
        path = os.path.join(output_dir, f"slide_{i+1}.png")
        img.save(path, "PNG")
        preview_paths.append(path)
    
    # Cleanup temp PDF
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
    
    return preview_paths
```

---

## Error Handling Checklist

| Scenario | Error | Solution |
|----------|-------|----------|
| Template not found | `FileNotFoundError` | Verify input path exists before loading |
| Invalid PPTX format | `KeyError` in python-pptx | Try opening in PowerPoint first, or recreate |
| Image too large | Slow performance / OOM | Resize with Pillow before inserting |
| Font not available | Fallback to default font | Use common fonts (Arial, Calibri, etc.) |
| Libreoffice fails | No output / hangs | Ensure no other LO instance is running |
| markitdown fails | ImportError or empty output | Check markitdown is installed with `[pptx]` extra |
| Shape positioning off | Wrong units | Use `Inches()` or `Emu()` helpers in python-pptx |
| Slide layout missing | `IndexError` on `slide_layouts[N]` | Check available layouts with `len(prs.slide_layouts)` |

---

## Recommended Flow

1. **User request** → Identify task category (create, edit, extract, convert)
2. **Choose tool** → Use quick-reference table above
3. **Read sub-doc** → Check `creation.md`, `editing.md`, or `extraction.md` for detailed examples
4. **Execute** → Write minimal, focused script for the task
5. **Output** → Save results to `/mnt/user-data/outputs/` if file-based
6. **Report** → Summary of what was done + file location/size

**For complex requests** (multi-step):
- Break into sequential operations
- Re-read intermediate files to validate structure
- Report checkpoint progress

---

## Notes

- **pptxgenjs** is the best choice for creating new presentations from scratch — clean API, good defaults
- **python-pptx** excels at editing existing files and working with templates
- **markitdown** provides quick content extraction to Markdown format
- **Pillow** handles image preprocessing (resize, crop, thumbnail) before inserting into slides
- **libreoffice** is the most reliable tool for PPTX → PDF conversion
- **pdftoppm** generates high-quality slide preview images from PDF
- For **very large presentations** (50+ slides), consider building incrementally and saving periodically
- Use **common fonts** (Arial, Calibri, Helvetica) for maximum compatibility across platforms
