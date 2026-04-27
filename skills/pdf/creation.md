# PDF Creation & Generation

## Programmatic PDF Generation (reportlab)

### Basic Canvas Setup
```python
from reportlab.lib.pagesizes import letter, A4, landscape
from reportlab.lib.units import inch, cm
from reportlab.pdfgen import canvas

# Letter size (default)
c = canvas.Canvas("simple.pdf", pagesize=letter)
width, height = letter  # (612, 792) in points

# A4 size
c = canvas.Canvas("document.pdf", pagesize=A4)

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

# Arc (pie slice)
c.arc(1*inch, 1.5*inch, 1*inch, 45, 180)

c.save()
```

### Images in PDFs
```python
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib.pagesizes import letter

c = canvas.Canvas("with_image.pdf", pagesize=letter)
width, height = letter

# Insert image
c.drawImage("logo.png", 1*inch, height - 1.5*inch, width=2*inch, height=1*inch)

c.drawString(1*inch, height - 2.5*inch, "Image inserted above")

c.save()
```

---

## Tables & Structured Data (Platypus)

### Simple Table
```python
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

doc = SimpleDocTemplate("table.pdf", pagesize=letter)
styles = getSampleStyleSheet()

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

### Dynamic Table from CSV
```python
import csv
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors

# Read CSV
with open("data.csv") as f:
    reader = csv.reader(f)
    data = list(reader)

doc = SimpleDocTemplate("from_csv.pdf", pagesize=letter)

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

---

## Invoice Template Example

```python
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfgen import canvas
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

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| Text cut off | Coordinates outside page bounds | Check math: `y_position = height - distance_from_top` |
| Image not showing | File path wrong | Use absolute path or verify file exists |
| Table overlaps previous content | No spacing between elements | Add `Spacer(1, 0.5*inch)` |
| Blank PDF created | `doc.build([])` with empty story | Ensure items added before `build()` |
| Form fields not interactive | Missing `form.flatten()` call | Don't flatten if you want users to edit |
| Performance slow (100+ PDFs) | Serial generation | Use multiprocessing or batch at OS level |
