---
name: docx-agent
description: |
  Create and edit Word documents (.docx) for any general purpose using Node.js or Python. 
  Use this skill whenever you need to generate, modify, or customize DOCX files with formatting, tables, images, lists, headers, or styling. 
  Provides code templates for direct execution in container environments. 
  Covers common scenarios: letters, invoices, reports, certificates, forms, and custom documents. 
  Always generate ready-to-use output files with professional formatting.
---

## Quick Decision Tree

**Use Node.js (`docx`)** when:
- Creating document from scratch
- Need advanced styling (complex layouts, precise positioning)
- Building multi-section documents with varied formatting
- Performance is critical (Node.js faster for large documents)

**Use Python (`python-docx`)** when:
- Editing existing .docx file (read + modify + save)
- Simple content insertion into existing templates
- Working with document metadata/properties
- Python dependencies already available in container

---

## Common Document Templates for WhatsApp Scenarios

### 1. **Letter / Formal Document**
```
Header (logo/sender info)
Date
Recipient info
Greeting
Body paragraphs
Closing
Signature
```

### 2. **Invoice / Receipt**
```
Header (business name)
Invoice number + date
From/To sections
Line items table (description, qty, price, total)
Subtotal/Tax/Total
Payment instructions
```

### 3. **Report / Summary**
```
Title page
Table of contents
Sections with headings
Data tables
Charts/metrics
Conclusion
```

### 4. **Certificate / Award**
```
Centered header
Large text (recipient name)
Achievement text
Signature lines
Date
Seal/logo
```

### 5. **Form / Checklist**
```
Title
Instructions
Numbered/bulleted questions or checkboxes
Spacing for answers
Footer notes
```

### 6. **Academic Paper / Makalah**
```
Cover page (title, author, date, institution)
Table of contents
Introduction / Pendahuluan
Main sections / Bab utama
Conclusion / Kesimpulan
Bibliography / Daftar Pustaka
```

### 7. **Request Letter / Surat Permohonan**
```
Company header + logo area
Date
Recipient address
Greeting
Request statement (clear & specific)
Supporting reasons
Closing & signature
```

### 8. **Invitation Letter / Surat Undangan**
```
Header (event name/organizer)
Recipient name
Event details (date, time, location)
Brief description
RSVP details
Signature + organizer info
```

---

## Node.js (`docx`) – Create from Scratch


### Basic Template (Letter)

```javascript
const { Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, BorderStyle, convertInchesToTwip } = require("docx");
const fs = require("fs");

const doc = new Document({
  sections: [{
    children: [
      // Header
      new Paragraph({
        text: "PT Example Company",
        heading: HeadingLevel.HEADING_1,
        alignment: AlignmentType.CENTER,
        spacing: { after: 200 }
      }),
      new Paragraph({
        text: "Jl. Example No. 123, Jakarta",
        alignment: AlignmentType.CENTER,
        spacing: { after: 400 }
      }),
      
      // Date
      new Paragraph({
        text: `Jakarta, ${new Date().toLocaleDateString('id-ID')}`,
        spacing: { after: 400 }
      }),
      
      // Recipient
      new Paragraph({
        text: "Kepada Yth.",
        spacing: { after: 100 }
      }),
      new Paragraph({
        text: "[Recipient Name]",
        spacing: { after: 50 }
      }),
      new Paragraph({
        text: "[Address]",
        spacing: { after: 400 }
      }),
      
      // Greeting
      new Paragraph({
        text: "Dengan hormat,",
        spacing: { after: 300 }
      }),
      
      // Body
      new Paragraph({
        text: "[Letter content goes here. Replace with actual content.]",
        spacing: { after: 200 },
        alignment: AlignmentType.JUSTIFIED
      }),
      
      // Closing
      new Paragraph({
        text: "Hormat kami,",
        spacing: { after: 600 }
      }),
      new Paragraph({
        text: "[Sender Name]",
        spacing: { after: 100 }
      }),
      new Paragraph({
        text: "[Position]"
      })
    ]
  }]
});

// Save to file
Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync("letter.docx", buffer);
  console.log("✓ Document created: letter.docx");
});
```

### Table Template (Invoice)

```javascript
const { Document, Packer, Paragraph, Table, TableRow, TableCell, TextRun, HeadingLevel, AlignmentType, WidthType, BorderStyle, convertInchesToTwip } = require("docx");
const fs = require("fs");

const doc = new Document({
  sections: [{
    children: [
      // Header
      new Paragraph({
        text: "INVOICE",
        heading: HeadingLevel.HEADING_1,
        alignment: AlignmentType.CENTER,
        spacing: { after: 200 }
      }),
      
      // Invoice info
      new Table({
        width: { size: 100, type: WidthType.PERCENTAGE },
        rows: [
          new TableRow({
            children: [
              new TableCell({
                children: [new Paragraph("Invoice No: INV-2025-001")],
                borders: { top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE }, left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE } }
              }),
              new TableCell({
                children: [new Paragraph("Date: 2025-01-15")],
                borders: { top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE }, left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE } }
              })
            ]
          })
        ]
      }),
      
      new Paragraph({ text: "", spacing: { after: 200 } }),
      
      // Items table
      new Table({
        width: { size: 100, type: WidthType.PERCENTAGE },
        rows: [
          // Header row
          new TableRow({
            children: [
              new TableCell({
                children: [new Paragraph({ children: [new TextRun({ text: "Description", bold: true })] })],
                shading: { fill: "D3D3D3" }
              }),
              new TableCell({
                children: [new Paragraph({ children: [new TextRun({ text: "Qty", bold: true })] })],
                shading: { fill: "D3D3D3" },
                width: { size: 10, type: WidthType.PERCENTAGE }
              }),
              new TableCell({
                children: [new Paragraph({ children: [new TextRun({ text: "Price", bold: true })] })],
                shading: { fill: "D3D3D3" },
                width: { size: 20, type: WidthType.PERCENTAGE }
              }),
              new TableCell({
                children: [new Paragraph({ children: [new TextRun({ text: "Total", bold: true })] })],
                shading: { fill: "D3D3D3" },
                width: { size: 20, type: WidthType.PERCENTAGE }
              })
            ]
          }),
          // Data rows
          new TableRow({
            children: [
              new TableCell({
                children: [new Paragraph("Item 1")]
              }),
              new TableCell({
                children: [new Paragraph("1")],
                width: { size: 10, type: WidthType.PERCENTAGE }
              }),
              new TableCell({
                children: [new Paragraph("100,000")],
                width: { size: 20, type: WidthType.PERCENTAGE }
              }),
              new TableCell({
                children: [new Paragraph("100,000")],
                width: { size: 20, type: WidthType.PERCENTAGE }
              })
            ]
          })
        ]
      }),
      
      new Paragraph({ text: "", spacing: { after: 400 } }),
      
      // Total
      new Paragraph({
        children: [new TextRun({ text: "Total: Rp 100,000", bold: true })],
        alignment: AlignmentType.RIGHT,
        spacing: { after: 200 }
      })
    ]
  }]
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync("invoice.docx", buffer);
  console.log("✓ Invoice created: invoice.docx");
});
```

### Academic Paper Template (Makalah)

```javascript
const { Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, PageBreak } = require("docx");
const fs = require("fs");

const doc = new Document({
  sections: [{
    children: [
      // Cover page
      new Paragraph({
        text: "JUDUL MAKALAH ANDA DI SINI",
        heading: HeadingLevel.HEADING_1,
        alignment: AlignmentType.CENTER,
        spacing: { after: 400 }
      }),
      new Paragraph({
        text: "Nama Penulis",
        alignment: AlignmentType.CENTER,
        spacing: { after: 50 }
      }),
      new Paragraph({
        text: "NIM/ID: 12345",
        alignment: AlignmentType.CENTER,
        spacing: { after: 200 }
      }),
      new Paragraph({
        text: "Universitas Indonesia",
        alignment: AlignmentType.CENTER,
        spacing: { after: 200 }
      }),
      new Paragraph({
        text: `Jakarta, ${new Date().toLocaleDateString('id-ID')}`,
        alignment: AlignmentType.CENTER
      }),
      new PageBreak(),
      
      // Table of Contents
      new Paragraph({
        text: "DAFTAR ISI",
        heading: HeadingLevel.HEADING_2,
        spacing: { after: 200 }
      }),
      new Paragraph({
        text: "1. Pendahuluan\n2. Tinjauan Pustaka\n3. Pembahasan\n4. Kesimpulan\n5. Daftar Pustaka",
        spacing: { after: 400 }
      }),
      new PageBreak(),
      
      // Introduction
      new Paragraph({
        text: "1. PENDAHULUAN",
        heading: HeadingLevel.HEADING_2,
        spacing: { after: 200 }
      }),
      new Paragraph({
        text: "[Tulis pendahuluan makalah Anda di sini. Jelaskan latar belakang, rumusan masalah, dan tujuan penelitian.]",
        spacing: { after: 200 },
        alignment: AlignmentType.JUSTIFIED
      }),
      
      // Main body
      new Paragraph({
        text: "2. TINJAUAN PUSTAKA",
        heading: HeadingLevel.HEADING_2,
        spacing: { after: 200 }
      }),
      new Paragraph({
        text: "[Tulis review literatur atau teori pendukung di sini.]",
        spacing: { after: 200 },
        alignment: AlignmentType.JUSTIFIED
      }),
      
      new Paragraph({
        text: "3. PEMBAHASAN",
        heading: HeadingLevel.HEADING_2,
        spacing: { after: 200 }
      }),
      new Paragraph({
        text: "[Tulis analisis dan pembahasan utama di sini.]",
        spacing: { after: 200 },
        alignment: AlignmentType.JUSTIFIED
      }),
      
      // Conclusion
      new Paragraph({
        text: "4. KESIMPULAN",
        heading: HeadingLevel.HEADING_2,
        spacing: { after: 200 }
      }),
      new Paragraph({
        text: "[Tulis kesimpulan dan saran penelitian di sini.]",
        spacing: { after: 400 },
        alignment: AlignmentType.JUSTIFIED
      }),
      
      // References
      new Paragraph({
        text: "5. DAFTAR PUSTAKA",
        heading: HeadingLevel.HEADING_2,
        spacing: { after: 200 }
      }),
      new Paragraph({
        text: "[1] Nama Penulis, \"Judul Artikel\", Jurnal/Konferensi, Tahun."
      })
    ]
  }]
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync("makalah.docx", buffer);
  console.log("✓ Makalah created: makalah.docx");
});
```

### Request Letter Template

```javascript
const { Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, BorderStyle, WidthType, convertInchesToTwip } = require("docx");
const fs = require("fs");

const doc = new Document({
  sections: [{
    children: [
      // Header
      new Paragraph({
        children: [new TextRun({ text: "KEMENTERIAN PENDIDIKAN, KEBUDAYAAN, RISET, DAN TEKNOLOGI", bold: true })],
        alignment: AlignmentType.CENTER,
        spacing: { after: 50 }
      }),
      new Paragraph({
        children: [new TextRun({ text: "UNIVERSITAS INDONESIA", bold: true })],
        alignment: AlignmentType.CENTER,
        spacing: { after: 50 }
      }),
      new Paragraph({
        text: "Gedung Rektorat, Kampus Depok, Indonesia",
        alignment: AlignmentType.CENTER,
        spacing: { after: 300 }
      }),
      
      // Subject
      new Paragraph({
        text: "Perihal: Permohonan Beasiswa Akademik",
        spacing: { after: 300 }
      }),
      
      // Date
      new Paragraph({
        text: `Jakarta, ${new Date().toLocaleDateString('id-ID')}`,
        spacing: { after: 300 }
      }),
      
      // Recipient
      new Paragraph({
        text: "Kepada Yth.",
        spacing: { after: 50 }
      }),
      new Paragraph({
        text: "Ketua Panitia Beasiswa",
        spacing: { after: 50 }
      }),
      new Paragraph({
        text: "Universitas Indonesia",
        spacing: { after: 50 }
      }),
      new Paragraph({
        text: "Jakarta",
        spacing: { after: 300 }
      }),
      
      // Greeting
      new Paragraph({
        text: "Dengan hormat,",
        spacing: { after: 200 }
      }),
      
      // Request statement
      new Paragraph({
        text: "Saya yang bertanda tangan di bawah ini:",
        spacing: { after: 100 }
      }),
      new Paragraph({
        text: "Nama\t\t: [NAMA LENGKAP]",
        spacing: { after: 50 }
      }),
      new Paragraph({
        text: "NIM\t\t: [NOMOR INDUK MAHASISWA]",
        spacing: { after: 50 }
      }),
      new Paragraph({
        text: "Program Studi\t: [PROGRAM STUDI]",
        spacing: { after: 50 }
      }),
      new Paragraph({
        text: "Semester\t\t: [SEMESTER]",
        spacing: { after: 300 }
      }),
      
      // Main request
      new Paragraph({
        text: "Dengan ini dengan hormat mengajukan permohonan untuk mendapatkan beasiswa akademik tahun akademik 2024/2025.",
        spacing: { after: 200 },
        alignment: AlignmentType.JUSTIFIED
      }),
      
      // Supporting reasons
      new Paragraph({
        children: [new TextRun({ text: "Alasan Permohonan:", bold: true })],
        spacing: { after: 100 }
      }),
      new Paragraph({
        text: "[Jelaskan alasan dan latar belakang permohonan beasiswa Anda dengan detail dan persuasif.]",
        spacing: { after: 100 },
        alignment: AlignmentType.JUSTIFIED
      }),
      new Paragraph({
        text: "[Sertakan prestasi akademik, bukti kondisi finansial, dan komitmen Anda terhadap studi.]",
        spacing: { after: 300 },
        alignment: AlignmentType.JUSTIFIED
      }),
      
      // Closing
      new Paragraph({
        text: "Demikian permohonan ini saya sampaikan. Atas perhatian dan pertimbangan Bapak/Ibu, saya ucapkan terima kasih.",
        spacing: { after: 300 },
        alignment: AlignmentType.JUSTIFIED
      }),
      
      // Signature
      new Paragraph({
        text: "Hormat saya,",
        spacing: { after: 400 }
      }),
      new Paragraph({
        text: "[NAMA LENGKAP]",
        spacing: { after: 50 }
      }),
      new Paragraph({
        text: "[NOMOR INDUK MAHASISWA]"
      })
    ]
  }]
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync("surat_permohonan.docx", buffer);
  console.log("✓ Surat Permohonan created: surat_permohonan.docx");
});
```

### Invitation Letter Template

```javascript
const { Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, BorderStyle, Table, TableRow, TableCell, WidthType } = require("docx");
const fs = require("fs");

const doc = new Document({
  sections: [{
    children: [
      // Header
      new Paragraph({
        text: "SURAT UNDANGAN",
        heading: HeadingLevel.HEADING_1,
        alignment: AlignmentType.CENTER,
        spacing: { after: 300 }
      }),
      
      // Event name
      new Paragraph({
        text: "Seminar Nasional Teknologi Informasi 2025",
        heading: HeadingLevel.HEADING_2,
        alignment: AlignmentType.CENTER,
        spacing: { after: 300 }
      }),
      
      // Recipient
      new Paragraph({
        text: "Kepada Yth.",
        spacing: { after: 50 }
      }),
      new Paragraph({
        children: [new TextRun({ text: "[NAMA PENERIMA UNDANGAN]", bold: true })],
        spacing: { after: 50 }
      }),
      new Paragraph({
        text: "[INSTITUSI/PERUSAHAAN]",
        spacing: { after: 300 }
      }),
      
      // Opening
      new Paragraph({
        text: "Dengan hormat,",
        spacing: { after: 200 }
      }),
      
      // Invitation statement
      new Paragraph({
        text: "Kami dengan senang hati mengundang Anda untuk menghadiri acara kami:",
        spacing: { after: 200 },
        alignment: AlignmentType.JUSTIFIED
      }),
      
      // Event details table
      new Table({
        width: { size: 100, type: WidthType.PERCENTAGE },
        rows: [
          new TableRow({
            children: [
              new TableCell({
                children: [new Paragraph("Nama Acara")],
                borders: { top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE }, left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE } },
                width: { size: 30, type: WidthType.PERCENTAGE }
              }),
              new TableCell({
                children: [new Paragraph(": Seminar Nasional Teknologi Informasi 2025")],
                borders: { top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE }, left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE } },
                width: { size: 70, type: WidthType.PERCENTAGE }
              })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({
                children: [new Paragraph("Tanggal")],
                borders: { top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE }, left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE } }
              }),
              new TableCell({
                children: [new Paragraph(": 20 Februari 2025")],
                borders: { top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE }, left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE } }
              })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({
                children: [new Paragraph("Waktu")],
                borders: { top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE }, left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE } }
              }),
              new TableCell({
                children: [new Paragraph(": 08:00 - 16:00 WIB")],
                borders: { top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE }, left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE } }
              })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({
                children: [new Paragraph("Lokasi")],
                borders: { top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE }, left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE } }
              }),
              new TableCell({
                children: [new Paragraph(": Gedung Auditorium, Universitas Indonesia, Jakarta")],
                borders: { top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE }, left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE } }
              })
            ]
          })
        ]
      }),
      
      new Paragraph({ text: "", spacing: { after: 300 } }),
      
      // Description
      new Paragraph({
        text: "Seminar ini akan menghadirkan pembicara tamu dari berbagai institusi terkemuka dan perusahaan teknologi untuk membahas perkembangan terbaru dalam bidang Teknologi Informasi.",
        spacing: { after: 200 },
        alignment: AlignmentType.JUSTIFIED
      }),
      
      // RSVP
      new Paragraph({
        children: [new TextRun({ text: "Konfirmasi Kehadiran:", bold: true })],
        spacing: { after: 100 }
      }),
      new Paragraph({
        text: "Mohon konfirmasi kehadiran Anda paling lambat tanggal 15 Februari 2025 melalui:",
        spacing: { after: 50 }
      }),
      new Paragraph({
        text: "Email: seminar@universitas.ac.id | Telepon: (021) 3456-7890",
        spacing: { after: 300 }
      }),
      
      // Closing
      new Paragraph({
        text: "Atas kehadiran Anda, kami ucapkan terima kasih.",
        spacing: { after: 300 },
        alignment: AlignmentType.JUSTIFIED
      }),
      
      // Signature
      new Paragraph({
        text: "Hormat kami,",
        spacing: { after: 400 }
      }),
      new Paragraph({
        text: "Jakarta, [TANGGAL]",
        spacing: { after: 50 }
      }),
      new Paragraph({
        text: "Panitia Penyelenggara Seminar",
        spacing: { after: 50 }
      }),
      new Paragraph({
        text: "[NAMA KOORDINATOR]"
      })
    ]
  }]
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync("surat_undangan.docx", buffer);
  console.log("✓ Surat Undangan created: surat_undangan.docx");
});
```

---

## Python (`python-docx`) – Edit Existing Document

### Edit Template (Add content to existing document)

```python
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from datetime import datetime

# Load existing document
doc = Document("./input/template.docx")

# Add content
doc.add_heading("Report Title", level=1)
doc.add_paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d')}")

# Add table
table = doc.add_table(rows=3, cols=3)
table.style = 'Light Grid Accent 1'

# Fill table
hdr_cells = table.rows[0].cells
hdr_cells[0].text = "Item"
hdr_cells[1].text = "Value"
hdr_cells[2].text = "Status"

data_cells = table.rows[1].cells
data_cells[0].text = "Metric 1"
data_cells[1].text = "100"
data_cells[2].text = "OK"

# Add paragraph
doc.add_paragraph("This is a sample paragraph with some content.", style='Normal')

# Save
doc.save("report.docx")
print("✓ Document updated: report.docx")
```

### Replace Text in Existing Document

```python
from docx import Document

# Load document
doc = Document("./input/template.docx")

# Replace placeholder text
replacements = {
    "[RECIPIENT_NAME]": "John Doe",
    "[DATE]": "2025-01-15",
    "[AMOUNT]": "Rp 500,000"
}

for paragraph in doc.paragraphs:
    for old_text, new_text in replacements.items():
        if old_text in paragraph.text:
            paragraph.text = paragraph.text.replace(old_text, new_text)

# Also check in tables
for table in doc.tables:
    for row in table.rows:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                for old_text, new_text in replacements.items():
                    if old_text in paragraph.text:
                        paragraph.text = paragraph.text.replace(old_text, new_text)

doc.save("filled_template.docx")
print("✓ Template filled: filled_template.docx")
```

---

## Best Practices for Sub-Agent

### 1. **File Paths**
- Input files are staged by the orchestrator under `./input/` inside the agent's workdir; the exact paths are listed in the system prompt under "Input files". Use those paths verbatim.
- Write output to the current working directory (workdir) using a relative path (e.g. `./invoice.docx`). Never hard-code `/output/` or any other absolute path — that directory does not exist in the sidecar.
- Only list **deliverable** files in `end_task(output_files=[...])`; skip scratch/temp/intermediate files.

### 2. **Error Handling**
```javascript
// Node.js
try {
  Packer.toBuffer(doc).then(buffer => {
    fs.writeFileSync(outputPath, buffer);
  }).catch(err => {
    console.error("Error creating document:", err.message);
    process.exit(1);
  });
} catch (err) {
  console.error("Fatal error:", err);
  process.exit(1);
}
```

```python
# Python
try:
    doc.save(output_path)
    print(f"✓ Success: {output_path}")
except Exception as e:
    print(f"✗ Error: {str(e)}")
    exit(1)
```

### 3. **Output Validation**
- Verify file exists and > 0 bytes after creation
- Log file size for debugging
- Return file path for WhatsApp bot to send

### 4. **Template Customization**
- Accept parameters for dynamic content (names, dates, amounts, etc.)
- Use dictionary/object for multiple replacements
- Validate input before inserting (no null/undefined)

### 5. **Performance Tips**
- Node.js faster for creation from scratch
- Python better for batch edits
- Keep styling minimal for bot scenarios (smaller file size)
- Cache templates if reused

---

## Sub-Agent Integration Pattern

### Workflow for Sub-Agent
1. **Receive request** from main bot (document type, data)
2. **Choose method**: Create (Node.js) or Edit (Python)?
3. **Prepare template/code** with data
4. **Execute** (npm run / python script)
5. **Validate output** file
6. **Return deliverable paths** via `end_task(output_files=[...])` — use **absolute paths** (the workdir is in the system prompt)
7. **Bot sends** document via WhatsApp API

### Example Sub-Agent Request Structure
```json
{
  "action": "create_invoice",
  "type": "invoice",
  "data": {
    "invoice_no": "INV-2025-001",
    "date": "2025-01-15",
    "items": [
      { "desc": "Service A", "qty": 1, "price": 100000 }
    ],
    "total": 100000
  },
  "output_file": "./invoice_2025_001.docx"
}
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Module not found | Verify npm/pip install in container; check requirements.txt |
| File permission denied | Check /output directory writable; use chmod 777 if needed |
| Placeholder not replaced | Ensure exact text match; check for hidden characters |
| Large file size | Reduce images; remove unnecessary formatting; use compression |
| Memory error on large docs | Stream if possible; split document into sections |
