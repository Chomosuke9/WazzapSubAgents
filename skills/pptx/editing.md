# PPTX Editing Operations

## Editing Existing PPTX Files with python-pptx

### Load & Save
```python
from pptx import Presentation

# Load existing file
prs = Presentation("template.pptx")

# ... modifications ...

# Save (overwrite or new file)
prs.save("modified.pptx")
print("✓ Presentation saved")
```

### Inspect Presentation Structure
```python
from pptx import Presentation

prs = Presentation("presentation.pptx")

# Slide dimensions
print(f"Width: {prs.slide_width} EMU ({prs.slide_width / 914400:.2f} inches)")
print(f"Height: {prs.slide_height} EMU ({prs.slide_height / 914400:.2f} inches)")

# Available slide layouts
print(f"\nAvailable layouts ({len(prs.slide_layouts)}):")
for i, layout in enumerate(prs.slide_layouts):
    print(f"  [{i}] {layout.name}")

# Slide count
print(f"\nTotal slides: {len(prs.slides)}")

# Inspect each slide
for slide_idx, slide in enumerate(prs.slides):
    print(f"\n--- Slide {slide_idx + 1} ---")
    print(f"  Layout: {slide.slide_layout.name}")
    print(f"  Shapes: {len(slide.shapes)}")
    
    for shape in slide.shapes:
        print(f"  - {shape.shape_type}: name='{shape.name}' "
              f"pos=({shape.left/914400:.1f}\", {shape.top/914400:.1f}\") "
              f"size=({shape.width/914400:.1f}\" x {shape.height/914400:.1f}\")")
        if shape.has_text_frame:
            for para in shape.text_frame.paragraphs:
                if para.text.strip():
                    print(f"    Text: {para.text[:80]}")
```

---

## Working with Text

### Replace Text in All Slides
```python
from pptx import Presentation

prs = Presentation("template.pptx")

replacements = {
    "{{COMPANY}}": "PT Example Indonesia",
    "{{DATE}}": "2025-01-15",
    "{{NAME}}": "John Doe",
    "{{AMOUNT}}": "Rp 50,000,000",
}

for slide in prs.slides:
    for shape in slide.shapes:
        if shape.has_text_frame:
            for paragraph in shape.text_frame.paragraphs:
                for run in paragraph.runs:
                    for old, new in replacements.items():
                        if old in run.text:
                            run.text = run.text.replace(old, new)

prs.save("replaced.pptx")
print("✓ Text replaced successfully")
```

### Add Text to Existing Slide
```python
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

prs = Presentation("presentation.pptx")

# Get a specific slide (e.g., first slide)
slide = prs.slides[0]

# Add a new text box
left = Inches(1)
top = Inches(5)
width = Inches(8)
height = Inches(0.5)

txBox = slide.shapes.add_textbox(left, top, width, height)
tf = txBox.text_frame
tf.word_wrap = True

p = tf.paragraphs[0]
p.text = "Added text content"
p.font.size = Pt(14)
p.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
p.alignment = PP_ALIGN.LEFT

prs.save("modified.pptx")
```

### Format Text Runs
```python
from pptx import Presentation
from pptx.util import Pt
from pptx.dml.color import RGBColor

prs = Presentation("template.pptx")

for slide in prs.slides:
    for shape in slide.shapes:
        if shape.has_text_frame:
            for paragraph in shape.text_frame.paragraphs:
                for run in paragraph.runs:
                    # Apply formatting
                    run.font.size = Pt(14)
                    run.font.bold = True
                    run.font.italic = False
                    run.font.color.rgb = RGBColor(0x1B, 0x3A, 0x5C)
                    run.font.name = "Calibri"

prs.save("reformatted.pptx")
```

---

## Working with Slides

### Add New Slide
```python
from pptx import Presentation

prs = Presentation("template.pptx")

# Add slide using a specific layout
slide_layout = prs.slide_layouts[1]  # Title + Content layout
new_slide = prs.slides.add_slide(slide_layout)

# Add slide using blank layout
blank_layout = prs.slide_layouts[6]
blank_slide = prs.slides.add_slide(blank_layout)

prs.save("with_new_slides.pptx")
```

### Delete Slide
```python
from pptx import Presentation

prs = Presentation("presentation.pptx")

# Delete specific slide by index
def delete_slide(prs, index):
    """Delete slide at the given index."""
    rId = prs.slides._sldIdLst[index].get('r:id')
    prs.part.drop_rel(rId)
    del prs.slides._sldIdLst[index]

# Delete the 3rd slide (0-indexed: 2)
delete_slide(prs, 2)

prs.save("slide_deleted.pptx")
print("✓ Slide deleted")
```

### Duplicate Slide
```python
from pptx import Presentation
from copy import deepcopy
from lxml import etree

def duplicate_slide(prs, slide_index):
    """Duplicate a slide at the given index and add it at the end."""
    template_slide = prs.slides[slide_index]
    
    # Add a blank slide to get a new slide element
    blank_layout = prs.slide_layouts[6]
    new_slide = prs.slides.add_slide(blank_layout)
    
    # Copy all elements from template
    for shape in template_slide.shapes:
        el = deepcopy(shape._element)
        new_slide.shapes._spTree.append(el)
    
    # Remove the blank slide's default elements
    for shape in list(new_slide.shapes):
        if shape.name.startswith("Rectangle") or shape.name.startswith("TextBox"):
            pass  # Keep added shapes
    
    return new_slide

prs = Presentation("template.pptx")
duplicate_slide(prs, 0)  # Duplicate first slide
prs.save("duplicated.pptx")
```

### Reorder Slides
```python
from pptx import Presentation

def move_slide(prs, old_index, new_index):
    """Move slide from old_index to new_index."""
    xml_slides = prs.slides._sldIdLst
    slides = list(xml_slides)
    el = slides[old_index]
    slides.pop(old_index)
    slides.insert(new_index, el)
    
    # Rebuild the list
    for child in list(xml_slides):
        xml_slides.remove(child)
    for el in slides:
        xml_slides.append(el)

prs = Presentation("presentation.pptx")
# Move slide 5 to position 2
move_slide(prs, 4, 1)
prs.save("reordered.pptx")
```

---

## Working with Placeholders

### Find and Fill Placeholders
```python
from pptx import Presentation

prs = Presentation("template.pptx")

for slide in prs.slides:
    for shape in slide.placeholders:
        print(f"Placeholder idx={shape.placeholder_format.idx} "
              f"type={shape.placeholder_format.type} "
              f"name='{shape.name}'")
        
        # Fill based on placeholder index
        if shape.placeholder_format.idx == 1:
            # Title placeholder
            shape.text = "My Presentation Title"
        elif shape.placeholder_format.idx == 2:
            # Body/content placeholder
            shape.text = "This is the content of the slide."

prs.save("filled_placeholders.pptx")
```

### Common Placeholder Indices
```python
# Typical placeholder indices in standard layouts:
# 0 = Slide number
# 1 = Title
# 2 = Body / Content
# 3 = Date
# 4 = Footer
# 10 = Center title (for title slide)
# 11 = Subtitle (for title slide)
# 12 = Object (content area)
```

---

## Working with Tables

### Add Table to Slide
```python
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

prs = Presentation()
slide_layout = prs.slide_layouts[6]
slide = prs.slides.add_slide(slide_layout)

# Create table
rows, cols = 4, 3
left = Inches(1)
top = Inches(1.5)
width = Inches(11)
height = Inches(3)

table_shape = slide.shapes.add_table(rows, cols, left, top, width, height)
table = table_shape.table

# Set column widths
table.columns[0].width = Inches(5)
table.columns[1].width = Inches(3)
table.columns[2].width = Inches(3)

# Header row
headers = ["Item", "Quantity", "Price"]
for i, header in enumerate(headers):
    cell = table.cell(0, i)
    cell.text = header
    for paragraph in cell.text_frame.paragraphs:
        paragraph.font.size = Pt(14)
        paragraph.font.bold = True
        paragraph.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        paragraph.alignment = PP_ALIGN.CENTER
    # Header background
    cell.fill.solid()
    cell.fill.fore_color.rgb = RGBColor(0x1B, 0x3A, 0x5C)

# Data rows
data = [
    ["Product A", "10", "$50.00"],
    ["Product B", "5", "$25.00"],
    ["Product C", "8", "$40.00"],
]

for row_idx, row_data in enumerate(data, 1):
    for col_idx, cell_text in enumerate(row_data):
        cell = table.cell(row_idx, col_idx)
        cell.text = cell_text
        for paragraph in cell.text_frame.paragraphs:
            paragraph.font.size = Pt(12)
            paragraph.alignment = PP_ALIGN.CENTER

prs.save("table_presentation.pptx")
print("✓ Table presentation created")
```

### Modify Existing Table
```python
from pptx import Presentation

prs = Presentation("presentation_with_table.pptx")

for slide in prs.slides:
    for shape in slide.shapes:
        if shape.has_table:
            table = shape.table
            
            # Read table content
            print(f"Table: {len(table.rows)} rows x {len(table.columns)} cols")
            for row_idx, row in enumerate(table.rows):
                for col_idx, cell in enumerate(row.cells):
                    print(f"  Cell [{row_idx},{col_idx}]: {cell.text}")
            
            # Modify specific cell
            table.cell(1, 2).text = "Updated Value"
            
            # Add row (not natively supported - workaround)
            # python-pptx doesn't support adding rows to existing tables directly
            # Recreate the table if you need more rows

prs.save("modified_table.pptx")
```

---

## Working with Images

### Add Image to Slide
```python
from pptx import Presentation
from pptx.util import Inches

prs = Presentation("presentation.pptx")
slide = prs.slides[0]

# Add image at specific position
slide.shapes.add_picture(
    "logo.png",
    left=Inches(0.5),
    top=Inches(0.3),
    width=Inches(2),
    height=Inches(1),
)

# Add image that maintains aspect ratio (only specify width OR height)
slide.shapes.add_picture(
    "photo.jpg",
    left=Inches(4),
    top=Inches(1.5),
    width=Inches(5),  # Height auto-calculated
)

prs.save("with_images.pptx")
```

### Process Images with Pillow Before Inserting
```python
from PIL import Image
from pptx import Presentation
from pptx.util import Inches
import os

def prepare_image(input_path, output_path, max_width=1920, max_height=1080):
    """Resize and optimize image for PPTX insertion."""
    img = Image.open(input_path)
    
    # Convert RGBA to RGB (PPTX doesn't handle transparency well)
    if img.mode == "RGBA":
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        img = background
    
    # Resize maintaining aspect ratio
    img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
    
    # Save as optimized PNG
    img.save(output_path, "PNG", optimize=True)
    return output_path

# Usage
prs = Presentation()
slide = prs.slides.add_slide(prs.slide_layouts[6])

prepared = prepare_image("large_photo.jpg", "temp_photo.png")
slide.shapes.add_picture(prepared, Inches(1), Inches(1), width=Inches(8))

prs.save("with_optimized_images.pptx")

# Cleanup
os.remove("temp_photo.png")
```

---

## Working with Slide Masters & Layouts

### List All Masters and Layouts
```python
from pptx import Presentation

prs = Presentation("template.pptx")

for master in prs.slide_masters:
    print(f"Slide Master: {master.name if hasattr(master, 'name') else 'default'}")
    for layout in master.slide_layouts:
        print(f"  Layout [{prs.slide_layouts.index(layout)}]: {layout.name}")
```

### Apply Slide Layout
```python
from pptx import Presentation

prs = Presentation("template.pptx")

# When adding a new slide, choose the layout
# Common layouts by index:
# 0 = Title Slide
# 1 = Title and Content
# 2 = Section Header
# 3 = Two Content
# 4 = Comparison
# 5 = Title Only
# 6 = Blank

slide = prs.slides.add_slide(prs.slide_layouts[1])  # Title and Content
```

---

## Working with Notes

### Add Speaker Notes
```python
from pptx import Presentation

prs = Presentation("presentation.pptx")

for slide in prs.slides:
    # Add notes to each slide
    notes_slide = slide.notes_slide
    notes_slide.notes_text_frame.text = "Speaker notes for this slide..."

prs.save("with_notes.pptx")
```

### Read Speaker Notes
```python
from pptx import Presentation

prs = Presentation("presentation.pptx")

for i, slide in enumerate(prs.slides):
    if slide.has_notes_slide:
        notes = slide.notes_slide.notes_text_frame.text
        if notes.strip():
            print(f"Slide {i+1} notes: {notes}")
```

---

## Batch Operations

### Batch Replace Across Multiple Files
```python
from pptx import Presentation
from pathlib import Path
import os

replacements = {
    "{{YEAR}}": "2025",
    "{{COMPANY}}": "PT New Company",
}

input_dir = "templates/"
output_dir = "output/"
os.makedirs(output_dir, exist_ok=True)

for pptx_file in Path(input_dir).glob("*.pptx"):
    print(f"Processing {pptx_file.name}...")
    prs = Presentation(str(pptx_file))
    
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    for run in paragraph.runs:
                        for old, new in replacements.items():
                            if old in run.text:
                                run.text = run.text.replace(old, new)
    
    output_path = os.path.join(output_dir, pptx_file.name)
    prs.save(output_path)
    print(f"✓ Saved {output_path}")
```

### Merge Multiple Presentations
```python
from pptx import Presentation
from copy import deepcopy

def merge_presentations(output_path, input_files):
    """Merge multiple PPTX files into one."""
    base_prs = Presentation(input_files[0])
    
    for input_file in input_files[1:]:
        src_prs = Presentation(input_file)
        
        for slide in src_prs.slides:
            # Add blank slide to base
            new_slide = base_prs.slides.add_slide(base_prs.slide_layouts[6])
            
            # Copy shapes from source slide
            for shape in slide.shapes:
                el = deepcopy(shape._element)
                new_slide.shapes._spTree.append(el)
    
    base_prs.save(output_path)
    print(f"✓ Merged {len(input_files)} presentations into {output_path}")

merge_presentations(
    "merged.pptx",
    ["part1.pptx", "part2.pptx", "part3.pptx"]
)
```

---

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| Placeholder not found | Wrong index | Inspect with `slide.placeholders` first |
| Table row count wrong | python-pptx limitation | Recreate table if you need more rows |
| Image appears stretched | Both width & height set | Set only width OR height for auto-aspect |
| Font not applied | Font not in template | Use common fonts or embed font |
| Slide order wrong after move | Index shift | Move slides from end to start |
| Corrupted output | Missing rels | Always use `prs.save()`, don't modify XML directly |
| Large file size | Uncompressed images | Resize with Pillow before insertion |
