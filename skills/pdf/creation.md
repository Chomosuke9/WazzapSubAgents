# PDF Creation & Generation

## Programmatic PDF Generation (reportlab)

### Basic Canvas Setup
```python
from reportlab.lib.pagesizes import letter, A4, landscape
from reportlab.lib.units import inch, cm, mm
from reportlab.pdfgen import canvas

# Letter size (default)
c = canvas.Canvas("simple.pdf", pagesize=letter)
width, height = letter  # (612, 792) in points

# A4 size
c = canvas.Canvas("document.pdf", pagesize=A4)
width, height = A4  # (595.27, 841.89) in points

# Landscape
c = canvas.Canvas("wide.pdf", pagesize=landscape(letter))

c.save()
```

### Text with Styling
```python
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib.pagesizes import letter

c = canvas.Canvas("text.pdf", pagesize=letter)
width, height = letter

# Simple text
c.drawString(1*inch, height - 1*inch, "Hello World")

# Styled text
c.setFont("Helvetica-Bold", 24)
c.drawString(1*inch, height - 1*inch, "Big Title")

c.setFont("Helvetica", 12)
c.setFillColor("#333333")
c.drawString(1*inch, height - 2*inch, "Regular paragraph text")

# Multi-line text
text_lines = ["Line 1", "Line 2", "Line 3"]
y = height - 1*inch
for line in text_lines:
    c.drawString(1*inch, y, line)
    y -= 0.25*inch

# Text wrapping with textobject
from reportlab.lib.colors import black
text_obj = c.beginText(1*inch, height - 3*inch)
text_obj.setFont("Helvetica", 11)
text_obj.setFillColor(black)
text_obj.textLines("""
This is a multi-line paragraph.
It wraps automatically when you use textLines().
Each line is separated by a newline character.
""")
c.drawText(text_obj)

c.save()
```

### Shapes & Graphics
```python
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib.colors import red, blue, green, HexColor

c = canvas.Canvas("shapes.pdf")

# Rectangle
c.rect(1*inch, 7*inch, 3*inch, 1*inch, stroke=1, fill=0)

# Filled rectangle
c.setFillColor(red)
c.rect(1*inch, 5.5*inch, 3*inch, 1*inch, stroke=1, fill=1)

# Circle
c.setFillColor(blue)
c.circle(2*inch, 4*inch, 0.5*inch, fill=1)

# Line
c.setLineWidth(2)
c.setStrokeColor(green)
c.line(1*inch, 3*inch, 4*inch, 3*inch)

# Rounded rectangle
c.setFillColor(HexColor("#4472C4"))
c.roundRect(1*inch, 1*inch, 3*inch, 1*inch, 0.2*inch, fill=1, stroke=0)

c.save()
```

### Images in PDFs
```python
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib.pagesizes import letter

c = canvas.Canvas("with_image.pdf", pagesize=letter)
width, height = letter

# Insert image (PNG, JPG supported)
c.drawImage("logo.png", 1*inch, height - 1.5*inch, width=2*inch, height=1*inch)

# Image with preserveAspectRatio
c.drawImage("photo.jpg", 1*inch, height - 5*inch, 
            width=4*inch, height=3*inch,
            preserveAspectRatio=True, anchor='c')

c.save()
```

### Multi-page Documents
```python
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch

c = canvas.Canvas("multipage.pdf", pagesize=letter)
width, height = letter

# Page 1
c.setFont("Helvetica-Bold", 20)
c.drawString(1*inch, height - 1*inch, "Page 1 - Cover")
c.showPage()  # Finish page 1, start page 2

# Page 2
c.setFont("Helvetica", 14)
c.drawString(1*inch, height - 1*inch, "Page 2 - Content")
c.showPage()  # Finish page 2, start page 3

# Page 3
c.drawString(1*inch, height - 1*inch, "Page 3 - Final")
c.showPage()

c.save()
```

---

## Platypus Flow-based Layout (reportlab)

### Simple Document with Paragraphs
```python
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch

doc = SimpleDocTemplate("flow_doc.pdf", pagesize=letter)
styles = getSampleStyleSheet()
story = []

# Title
story.append(Paragraph("Document Title", styles["Title"]))
story.append(Spacer(1, 0.3*inch))

# Body text
story.append(Paragraph(
    "This is a paragraph with <b>bold</b> and <i>italic</i> text. "
    "Reportlab supports inline HTML-like markup.",
    styles["Normal"]
))
story.append(Spacer(1, 0.2*inch))

# New page
story.append(PageBreak())
story.append(Paragraph("Page 2 Content", styles["Heading1"]))

doc.build(story)
```

### Custom Paragraph Styles
```python
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT

styles = getSampleStyleSheet()

# Custom title
custom_title = ParagraphStyle(
    "CustomTitle",
    parent=styles["Title"],
    fontSize=28,
    textColor=HexColor("#1B3A5C"),
    spaceAfter=12,
    alignment=TA_CENTER,
)

# Custom body
custom_body = ParagraphStyle(
    "CustomBody",
    parent=styles["Normal"],
    fontSize=11,
    leading=16,
    textColor=HexColor("#333333"),
    alignment=TA_JUSTIFY,
    spaceAfter=8,
)

# Custom footer
custom_footer = ParagraphStyle(
    "CustomFooter",
    parent=styles["Normal"],
    fontSize=8,
    textColor=HexColor("#999999"),
    alignment=TA_CENTER,
)
```

---

## Tables & Structured Data (Platypus)

### Simple Table
```python
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import inch

doc = SimpleDocTemplate("table.pdf", pagesize=letter)

# Data as list of lists
data = [
    ["Item", "Qty", "Price"],
    ["Widget A", "10", "$5.00"],
    ["Widget B", "5", "$10.00"],
    ["Total", "", "$75.00"],
]

# Create table
table = Table(data, colWidths=[2*inch, 1*inch, 1*inch])

# Style the table
table.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),  # Header row
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, 0), 14),
    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
    ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
    ("GRID", (0, 0), (-1, -1), 1, colors.black),
]))

# Build PDF
story = [table]
doc.build(story)
```

### Dynamic Table from CSV/Excel
```python
import csv
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import inch

# Read CSV
with open("data.csv") as f:
    reader = csv.reader(f)
    data = list(reader)

# OR read Excel
df = pd.read_excel("data.xlsx")
data = [df.columns.tolist()] + df.values.tolist()

doc = SimpleDocTemplate("from_data.pdf", pagesize=letter)

# Auto-calculate column widths
col_widths = [2*inch] * len(data[0])
table = Table(data, colWidths=col_widths)

table.setStyle(TableStyle([
    ("GRID", (0, 0), (-1, -1), 1, colors.black),
    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
]))

story = [table]
doc.build(story)
```

### Advanced Table Styling
```python
from reportlab.lib import colors

table.setStyle(TableStyle([
    # Header styling
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, 0), 12),
    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
    ("TOPPADDING", (0, 0), (-1, 0), 12),
    
    # Alternating row colors
    ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#ECF0F1")),
    ("BACKGROUND", (0, 2), (-1, 2), colors.white),
    ("BACKGROUND", (0, 3), (-1, 3), colors.HexColor("#ECF0F1")),
    
    # Last row (total) styling
    ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#3498DB")),
    ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
    ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
    ("LINEABOVE", (0, -1), (-1, -1), 2, colors.HexColor("#2C3E50")),
    
    # Grid
    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#BDC3C7")),
    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    
    # Cell padding
    ("TOPPADDING", (0, 0), (-1, -1), 6),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
]))
```

---

## Invoice Template Example

```python
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from datetime import datetime

def create_invoice(filename, invoice_data):
    """
    invoice_data = {
        "invoice_number": "INV-001",
        "date": "2024-01-15",
        "company": "My Company",
        "client": "Client Name",
        "items": [
            {"desc": "Service 1", "qty": 1, "rate": 100},
            {"desc": "Service 2", "qty": 2, "rate": 50},
        ],
        "tax_rate": 0.10,
    }
    """
    doc = SimpleDocTemplate(filename, pagesize=letter)
    width, height = letter
    styles = getSampleStyleSheet()
    story = []
    
    # Header
    title_style = ParagraphStyle("CustomTitle", 
                                  parent=styles["Heading1"],
                                  fontSize=24,
                                  textColor=colors.HexColor("#003366"))
    story.append(Paragraph(invoice_data["company"], title_style))
    story.append(Paragraph("INVOICE", styles["Heading2"]))
    story.append(Spacer(1, 0.3*inch))
    
    # Invoice details
    details = f"""
    <b>Invoice #:</b> {invoice_data['invoice_number']}<br/>
    <b>Date:</b> {invoice_data['date']}<br/>
    <b>Client:</b> {invoice_data['client']}
    """
    story.append(Paragraph(details, styles["Normal"]))
    story.append(Spacer(1, 0.3*inch))
    
    # Line items table
    items = invoice_data["items"]
    subtotal = sum(item["qty"] * item["rate"] for item in items)
    tax = subtotal * invoice_data["tax_rate"]
    total = subtotal + tax
    
    table_data = [["Description", "Qty", "Rate", "Amount"]]
    for item in items:
        amount = item["qty"] * item["rate"]
        table_data.append([
            item["desc"],
            str(item["qty"]),
            f"${item['rate']:.2f}",
            f"${amount:.2f}"
        ])
    
    # Add totals
    table_data.append(["", "", "Subtotal:", f"${subtotal:.2f}"])
    table_data.append(["", "", "Tax (10%):", f"${tax:.2f}"])
    table_data.append(["", "", "TOTAL:", f"${total:.2f}"])
    
    table = Table(table_data, colWidths=[3*inch, 1*inch, 1*inch, 1.25*inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 12),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
        ("BACKGROUND", (0, -3), (-1, -1), colors.lightgrey),
        ("FONTNAME", (0, -3), (-1, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ("LINEABOVE", (0, -3), (-1, -3), 2, colors.black),
    ]))
    
    story.append(table)
    
    # Footer
    story.append(Spacer(1, 0.5*inch))
    footer = f"<i>Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}</i>"
    story.append(Paragraph(footer, styles["Normal"]))
    
    doc.build(story)

# Usage
create_invoice("invoice.pdf", {
    "invoice_number": "INV-2024-001",
    "date": "2024-01-15",
    "company": "Acme Corp",
    "client": "BigBiz Inc",
    "items": [
        {"desc": "Consulting Services", "qty": 40, "rate": 150},
        {"desc": "Development", "qty": 60, "rate": 125},
    ],
    "tax_rate": 0.10,
})
```

---

## Certificate Template Example

```python
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.enums import TA_CENTER

def create_certificate(filename, data):
    """
    data = {
        "recipient": "John Doe",
        "course": "Advanced Python Programming",
        "date": "2024-06-15",
        "issuer": "Tech Academy",
        "signer": "Dr. Jane Smith"
    }
    """
    c = canvas.Canvas(filename, pagesize=landscape(letter))
    width, height = landscape(letter)
    
    # Border
    c.setStrokeColor(colors.HexColor("#1B3A5C"))
    c.setLineWidth(3)
    c.rect(0.5*inch, 0.5*inch, width - 1*inch, height - 1*inch)
    
    # Inner border
    c.setStrokeColor(colors.HexColor("#C9A84C"))
    c.setLineWidth(1)
    c.rect(0.6*inch, 0.6*inch, width - 1.2*inch, height - 1.2*inch)
    
    # Title
    c.setFont("Helvetica-Bold", 36)
    c.setFillColor(colors.HexColor("#1B3A5C"))
    c.drawCentredString(width/2, height - 1.5*inch, "CERTIFICATE")
    
    c.setFont("Helvetica", 16)
    c.setFillColor(colors.HexColor("#666666"))
    c.drawCentredString(width/2, height - 2*inch, "OF COMPLETION")
    
    # Recipient
    c.setFont("Helvetica-Bold", 28)
    c.setFillColor(colors.HexColor("#C9A84C"))
    c.drawCentredString(width/2, height - 3*inch, data["recipient"])
    
    # Description
    c.setFont("Helvetica", 14)
    c.setFillColor(colors.HexColor("#333333"))
    c.drawCentredString(width/2, height - 3.7*inch, 
                        f'Has successfully completed the course')
    c.drawCentredString(width/2, height - 4.1*inch, data["course"])
    
    # Date & Signer
    c.setFont("Helvetica", 12)
    c.drawString(1.5*inch, 1.5*inch, f"Date: {data['date']}")
    c.drawRightString(width - 1.5*inch, 1.5*inch, data["signer"])
    c.drawRightString(width - 1.5*inch, 1.2*inch, data["issuer"])
    
    # Signature line
    c.setStrokeColor(colors.HexColor("#333333"))
    c.setLineWidth(0.5)
    c.line(width - 4*inch, 1.6*inch, width - 1.5*inch, 1.6*inch)
    
    c.save()

create_certificate("certificate.pdf", {
    "recipient": "John Doe",
    "course": "Advanced Python Programming",
    "date": "2024-06-15",
    "issuer": "Tech Academy",
    "signer": "Dr. Jane Smith"
})
```

---

## Form Filling (Node.js - pdf-lib)

### Fill AcroForm Fields
```javascript
const { PDFDocument } = require('pdf-lib');
const fs = require('fs');

async function fillForm() {
  // Load existing form PDF
  const existingPdfBytes = fs.readFileSync('form_template.pdf');
  const pdfDoc = await PDFDocument.load(existingPdfBytes);
  
  // Get form
  const form = pdfDoc.getForm();
  
  // Fill text fields
  form.getTextField('full_name').setText('John Doe');
  form.getTextField('email').setText('john@example.com');
  form.getTextField('phone').setText('555-1234');
  
  // Set radio button
  form.getRadioGroup('gender').select('male');
  
  // Check checkbox
  form.getCheckBox('agree_terms').check();
  
  // Set dropdown
  form.getDropdown('country').select('USA');
  
  // Flatten form (make it read-only)
  form.flatten();
  
  // Save
  const pdfBytes = await pdfDoc.save();
  fs.writeFileSync('form_filled.pdf', pdfBytes);
  console.log('✓ Form filled and saved');
}

fillForm();
```

### List All Form Fields
```javascript
const { PDFDocument } = require('pdf-lib');
const fs = require('fs');

async function listFormFields() {
  const pdfBytes = fs.readFileSync('form.pdf');
  const pdfDoc = await PDFDocument.load(pdfBytes);
  
  try {
    const form = pdfDoc.getForm();
    const fields = form.getFields();
    
    fields.forEach(field => {
      const type = field.constructor.name;
      const name = field.getName();
      console.log(`${type}: ${name}`);
    });
  } catch (e) {
    console.log('No form fields found in this PDF');
  }
}

listFormFields();
```

### Programmatically Create Form
```javascript
const { PDFDocument, rgb } = require('pdf-lib');
const fs = require('fs');

async function createFormPDF() {
  const pdfDoc = await PDFDocument.create();
  const page = pdfDoc.addPage([600, 800]);
  
  const form = pdfDoc.getForm();
  
  // Add title
  page.drawText('Contact Form', {
    x: 50,
    y: 750,
    size: 24,
  });
  
  // Add text fields
  const nameField = form.createTextField('name');
  nameField.setText('');
  nameField.addToPage(page, { x: 50, y: 700, width: 300, height: 30 });
  page.drawText('Name:', { x: 50, y: 730, size: 12 });
  
  const emailField = form.createTextField('email');
  emailField.setText('');
  emailField.addToPage(page, { x: 50, y: 620, width: 300, height: 30 });
  page.drawText('Email:', { x: 50, y: 650, size: 12 });
  
  // Save
  const pdfBytes = await pdfDoc.save();
  fs.writeFileSync('form.pdf', pdfBytes);
}

createFormPDF();
```

---

## Batch PDF Generation

```python
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
import os

# Read data source (CSV, Excel, etc.)
df = pd.read_csv("recipients.csv")

output_dir = "generated_pdfs"
os.makedirs(output_dir, exist_ok=True)

for idx, row in df.iterrows():
    filename = f"{output_dir}/{row['name'].replace(' ', '_')}.pdf"
    
    c = canvas.Canvas(filename, pagesize=letter)
    width, height = letter
    
    # Personalized content
    c.setFont("Helvetica-Bold", 16)
    c.drawString(1*inch, height - 1*inch, f"Dear {row['name']},")
    
    c.setFont("Helvetica", 12)
    c.drawString(1*inch, height - 1.5*inch, f"Your account: {row['email']}")
    c.drawString(1*inch, height - 2*inch, f"Status: {row['status']}")
    
    c.save()
    print(f"✓ Generated {filename}")

print(f"✓ Created {len(df)} PDFs")
```

---

## Converting Other Formats to PDF (libreoffice)

```bash
# DOCX to PDF
libreoffice --headless --convert-to pdf document.docx --outdir output/

# XLSX to PDF
libreoffice --headless --convert-to pdf spreadsheet.xlsx --outdir output/

# PPTX to PDF
libreoffice --headless --convert-to pdf presentation.pptx --outdir output/

# Batch convert all DOCX files
libreoffice --headless --convert-to pdf *.docx --outdir output/
```

---

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| Text cut off | Coordinates outside page bounds | Check math: `y_position = height - distance_from_top` |
| Image not showing | File path wrong | Use absolute path or verify file exists |
| Table overlaps previous content | No spacing between elements | Add `Spacer(1, 0.5*inch)` |
| Blank PDF created | `doc.build([])` with empty story | Ensure items added before `build()` |
| Form fields not interactive | Missing `form.flatten()` call | Don't flatten if you want users to edit |
| Performance slow (100+ PDFs) | Serial generation | Use multiprocessing or batch at OS level |
| Unicode characters missing | Font doesn't support chars | Register a Unicode-capable TTF font |
| Custom font not found | Font not registered | Use `reportlab.pdfbase.pdfmetrics.registerFont()` |
