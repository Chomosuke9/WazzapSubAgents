---
name: xlsx-agent
description: |
  Create and edit Excel spreadsheets (.xlsx) using Python (openpyxl) or pandas.
  Use this skill whenever you need to read, write, transform, or style XLSX files:
  invoices, reports, data exports, financial tables, lookup sheets, or converting
  between CSV/Excel. openpyxl, pandas, and libreoffice are preinstalled in the
  sidecar.
---

# XLSX Spreadsheet Agent

Sub-agent skill for Excel workbook manipulation: reading, writing, styling, and
format conversion. Output goes into the **current working directory (workdir)** —
use relative paths like `./report.xlsx`. Never hard-code `/output/` or any other
absolute path.

## Quick Reference

| Task                    | Primary Tool       | Secondary         | Use When |
|-------------------------|--------------------|-------------------|----------|
| Bulk read/write tabular | `pandas`           | `openpyxl`        | Data analysis, CSV↔XLSX, joins |
| Styled workbook         | `openpyxl`         | `xlsxwriter`*     | Fonts, borders, merges, formulas |
| Edit existing template  | `openpyxl`         | —                 | Preserve existing styles + fill in |
| XLSX → PDF              | `libreoffice`      | —                 | Print-ready export |
| XLSX → CSV              | `pandas`           | `libreoffice`     | Downstream pipelines |
| CSV → XLSX              | `pandas`           | `openpyxl`        | Quick conversion |
| Multi-sheet workbook    | `pandas.ExcelWriter` + `openpyxl` engine | — | Tabs per category |

\* `xlsxwriter` is not installed by default; stick with `openpyxl` unless the
user explicitly asks for it.

---

## Quick Decision Tree

**Use `pandas`** when the task is fundamentally about **data**: filtering,
aggregating, joining, pivoting, converting to/from CSV.

**Use `openpyxl` directly** when you need to:
- Apply cell-level styling (fonts, fills, borders, number formats)
- Merge cells, freeze panes, set column widths
- Write Excel formulas that Excel will evaluate on open
- Add simple charts (bar, line, pie)
- Edit an existing `.xlsx` template without clobbering its styling

---

## 1. Read an existing workbook

### With pandas
```python
import pandas as pd

# Single sheet
df = pd.read_excel("./data.xlsx")                     # first sheet
df = pd.read_excel("./data.xlsx", sheet_name="Sales") # specific sheet

# All sheets as a dict of DataFrames
sheets = pd.read_excel("./data.xlsx", sheet_name=None)
for name, frame in sheets.items():
    print(name, frame.shape)
```

### With openpyxl (preserves formulas & styles)
```python
from openpyxl import load_workbook

wb = load_workbook("./data.xlsx", data_only=False)  # True = read computed values instead of formulas
ws = wb.active                                      # or wb["Sales"]

for row in ws.iter_rows(values_only=True):
    print(row)
```

---

## 2. Create a simple workbook (pandas)

```python
import pandas as pd

df = pd.DataFrame({
    "Item":  ["Widget A", "Widget B", "Widget C"],
    "Qty":   [10, 5, 8],
    "Price": [5.0, 10.0, 7.5],
})
df["Total"] = df["Qty"] * df["Price"]

df.to_excel("./inventory.xlsx", index=False, sheet_name="Inventory")
```

### Multiple sheets

```python
with pd.ExcelWriter("./report.xlsx", engine="openpyxl") as xw:
    sales.to_excel(xw, sheet_name="Sales",    index=False)
    costs.to_excel(xw, sheet_name="Costs",    index=False)
    totals.to_excel(xw, sheet_name="Summary", index=False)
```

---

## 3. Styled workbook (openpyxl)

```python
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

wb = Workbook()
ws = wb.active
ws.title = "Invoice"

# --- Header row ---
header = ["Description", "Qty", "Price", "Total"]
ws.append(header)

header_font   = Font(bold=True, color="FFFFFF")
header_fill   = PatternFill("solid", fgColor="1B3A5C")
center        = Alignment(horizontal="center", vertical="center")
thin_border   = Border(*(Side(style="thin", color="BFBFBF"),) * 4)

for col_idx, _ in enumerate(header, start=1):
    cell = ws.cell(row=1, column=col_idx)
    cell.font      = header_font
    cell.fill      = header_fill
    cell.alignment = center
    cell.border    = thin_border

# --- Data rows ---
items = [
    ("Service A", 1, 100_000),
    ("Service B", 2,  50_000),
]
for desc, qty, price in items:
    ws.append([desc, qty, price, qty * price])

# Currency format on price + total columns (C, D)
for row in ws.iter_rows(min_row=2, min_col=3, max_col=4):
    for cell in row:
        cell.number_format = '"Rp" #,##0'

# --- Total row with formula ---
last = ws.max_row
ws.cell(row=last + 1, column=1, value="TOTAL").font = Font(bold=True)
ws.cell(row=last + 1, column=4, value=f"=SUM(D2:D{last})").number_format = '"Rp" #,##0;[Red]-"Rp" #,##0'

# Column widths
for col_idx, width in enumerate([28, 8, 14, 16], start=1):
    ws.column_dimensions[get_column_letter(col_idx)].width = width

ws.freeze_panes = "A2"  # freeze header

wb.save("./invoice.xlsx")
```

---

## 4. Edit an existing template

Preserve styling — only overwrite cell values:

```python
from openpyxl import load_workbook

wb = load_workbook("./input/template.xlsx")
ws = wb["Invoice"]

ws["B2"] = "INV-2025-001"           # invoice number
ws["B3"] = "2025-01-15"              # date
ws["B4"] = "Client Name"             # client

# Fill line-items starting row 10
items = [("Service A", 1, 100_000), ("Service B", 2, 50_000)]
for offset, (desc, qty, price) in enumerate(items):
    r = 10 + offset
    ws.cell(row=r, column=1, value=desc)
    ws.cell(row=r, column=2, value=qty)
    ws.cell(row=r, column=3, value=price)

wb.save("./invoice_filled.xlsx")
```

Placeholder-style replacement (when the template contains `{{PLACEHOLDERS}}`):

```python
from openpyxl import load_workbook

wb = load_workbook("./input/template.xlsx")
replacements = {"{{NAME}}": "Budi", "{{DATE}}": "2025-01-15"}

for ws in wb.worksheets:
    for row in ws.iter_rows():
        for cell in row:
            if isinstance(cell.value, str):
                for token, value in replacements.items():
                    if token in cell.value:
                        cell.value = cell.value.replace(token, value)

wb.save("./filled.xlsx")
```

---

## 5. Format conversion

### XLSX → PDF (libreoffice)
```bash
libreoffice --headless --convert-to pdf ./report.xlsx --outdir ./
```

### XLSX → CSV (pandas, per sheet)
```python
import pandas as pd

sheets = pd.read_excel("./report.xlsx", sheet_name=None)
for name, df in sheets.items():
    df.to_csv(f"./{name}.csv", index=False)
```

### CSV → XLSX (pandas)
```python
import pandas as pd
pd.read_csv("./data.csv").to_excel("./data.xlsx", index=False)
```

---

## 6. Charts (openpyxl)

```python
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference

wb = Workbook(); ws = wb.active
ws.append(["Month", "Sales"])
for m, v in [("Jan", 120), ("Feb", 95), ("Mar", 140), ("Apr", 175)]:
    ws.append([m, v])

chart = BarChart()
chart.title    = "Monthly Sales"
chart.y_axis.title = "Revenue"
chart.x_axis.title = "Month"

data = Reference(ws, min_col=2, min_row=1, max_row=5, max_col=2)
cats = Reference(ws, min_col=1, min_row=2, max_row=5)
chart.add_data(data, titles_from_data=True)
chart.set_categories(cats)

ws.add_chart(chart, "D2")
wb.save("./sales_chart.xlsx")
```

---

## Error Handling Checklist

| Scenario                       | Error / Symptom                             | Fix |
|--------------------------------|---------------------------------------------|-----|
| Encrypted file                 | `InvalidFileException`                      | Decrypt first (ask user for password) or refuse |
| `.xls` (legacy format)         | openpyxl can't open it                      | Convert via libreoffice: `--convert-to xlsx` |
| Formula shows as string        | `data_only=False` (default)                 | Open with `data_only=True` **after** saving from Excel; openpyxl does not evaluate formulas |
| Dates read as floats           | Excel serial date                           | `pd.read_excel(..., parse_dates=[col])` or `cell.is_date` |
| Lost formatting after save     | Used pandas `.to_excel` on a styled file    | Use `openpyxl` directly for styled edits |
| Giant workbooks                | Memory blowup                                | `load_workbook(..., read_only=True)` for read-only streaming |
| Merged cell write fails        | `AttributeError` on MergedCell              | Unmerge first (`ws.unmerge_cells(...)`) then write |

---

## Best Practices for Sub-Agent

1. **Paths** — read inputs from the paths listed in your system prompt (usually
   `./input/*.xlsx`); write outputs to the workdir as `./<name>.xlsx`.
2. **Preserve templates** — if the user provides a styled template, use
   `openpyxl.load_workbook` and only overwrite cell values. Never rebuild from
   scratch.
3. **Validate output** — after saving, read the file back with `load_workbook`
   and spot-check a few cells; log file size (>0 bytes).
4. **Declare only deliverables** — list the final `.xlsx` (and PDF if you
   converted) in `end_task(output_files=[...])`. Skip scratch CSVs.
5. **Currency / number formats** — for Indonesian rupiah use
   `'"Rp" #,##0'`. Always apply number formats to numeric columns for
   readable Excel output.
