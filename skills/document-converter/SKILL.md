---
name: document-converter-agent
description: |
  Perform universal document format conversion using LibreOffice in headless mode.
  Use this skill to convert between DOCX, XLSX, PPTX, PDF, HTML, and more.
  Ideal for generating PDFs from office formats or converting legacy formats to modern ones.
---

# Document Converter Agent

Sub-agent skill for fast, headless document format conversion using LibreOffice. This tool is the bridge between editable formats and distribution-ready formats (like PDF).

## Quick Reference

| Source Format | Target Format | Command Snippet |
|---------------|---------------|-----------------|
| `.docx`, `.doc` | `.pdf`        | `libreoffice --headless --convert-to pdf input.docx` |
| `.xlsx`, `.xls` | `.pdf`        | `libreoffice --headless --convert-to pdf input.xlsx` |
| `.pptx`, `.ppt` | `.pdf`        | `libreoffice --headless --convert-to pdf input.pptx` |
| `.docx`         | `.html`       | `libreoffice --headless --convert-to html input.docx` |
| `.xlsx`         | `.csv`        | `libreoffice --headless --convert-to csv input.xlsx` |
| `.doc` (Legacy) | `.docx`       | `libreoffice --headless --convert-to docx input.doc` |

---

## Usage Patterns

### 1. Basic Conversion
The most common use case is converting an Office document to PDF.

```bash
libreoffice --headless --convert-to pdf document.docx --outdir ./output/
```

### 2. Batch Conversion
LibreOffice can handle multiple files in a single command.

```bash
# Convert all DOCX files in a folder to PDF
libreoffice --headless --convert-to pdf *.docx --outdir ./pdf_exports/
```

### 3. Python Integration
You can wrap the CLI call in a Python script for automation.

```python
import subprocess
import os

def convert_to_pdf(input_path, output_dir="."):
    """
    Converts a document to PDF using LibreOffice.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"File not found: {input_path}")
        
    command = [
        "libreoffice",
        "--headless",
        "--convert-to", "pdf",
        input_path,
        "--outdir", output_dir
    ]
    
    result = subprocess.run(command, capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"Successfully converted {input_path}")
    else:
        print(f"Error: {result.stderr}")

convert_to_pdf("report.docx")
```

---

## Supported Formats

LibreOffice supports a vast array of formats. Common conversions include:

- **Writer (Text):** doc, docx, odt, rtf, txt -> pdf, html, docx
- **Calc (Spreadsheet):** xls, xlsx, ods, csv -> pdf, html, xlsx
- **Impress (Presentation):** ppt, pptx, odp -> pdf, html, pptx, svg

---

## Best Practices

1. **Output Directory:** Always use the `--outdir` flag to specify where the converted file should go. By default, it saves in the same directory as the source.
2. **Filenames:** Avoid spaces in filenames if possible, or ensure they are properly escaped in the terminal command.
3. **Headless Mode:** Always include the `--headless` flag to prevent LibreOffice from trying to open a GUI window, which will fail in server/container environments.
4. **Environment:** If running in a container, ensure `libreoffice` and its dependencies (like `java` or specific fonts) are installed.

---

## Troubleshooting

| Issue | Potential Cause | Fix |
|-------|-----------------|-----|
| `Command not found` | LibreOffice is not installed. | Install via `apt-get install libreoffice` or equivalent. |
| `Permission denied` | No write access to output dir. | Check directory permissions or change `--outdir`. |
| `Conversion failed` | Corrupted file or missing fonts. | Try opening the file locally or ensure system fonts are available. |
| `Hanging process` | Another instance is locked. | Ensure no other `soffice` or `libreoffice` processes are running. |

---

## Notes
- **Fonts:** LibreOffice relies on system fonts. If a document looks different after conversion (e.g., missing specific branding fonts), ensure those `.ttf` or `.otf` files are installed in the environment.
- **Complexity:** For extremely complex Excel sheets with macros or external data links, some formatting or values might not render perfectly in PDF compared to native Microsoft Office.