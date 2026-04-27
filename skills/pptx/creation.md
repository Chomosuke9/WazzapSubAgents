# PPTX Creation Operations

## Creating Presentations from Scratch with pptxgenjs (Node.js)

### Basic Setup & Metadata
```javascript
const pptxgen = require("pptxgenjs");

const pptx = new pptxgen();

// Presentation metadata
pptx.author = "Wazzap Agent";
pptx.company = "WazzapSubAgents";
pptx.subject = "Generated Presentation";
pptx.title = "My Presentation";
pptx.layout = "LAYOUT_WIDE"; // 13.33" x 7.5" (16:9)
// pptx.layout = "LAYOUT_4x3"; // 10" x 7.5" (4:3)

// Define theme colors for consistency
const THEME = {
  primary: "1B3A5C",      // Dark blue
  secondary: "3498DB",    // Blue
  accent: "E74C3C",       // Red
  success: "27AE60",      // Green
  warning: "F39C12",      // Orange
  dark: "2C3E50",         // Dark gray
  medium: "7F8C8D",       // Medium gray
  light: "ECF0F1",        // Light gray
  white: "FFFFFF",
  black: "333333",
};
```

### Title Slide Template
```javascript
function addTitleSlide(pptx, title, subtitle, author = "", date = "") {
  const slide = pptx.addSlide();
  slide.background = { color: THEME.primary };
  
  // Decorative accent line
  slide.addShape(pptx.shapes.RECTANGLE, {
    x: 0, y: 2.8, w: "100%", h: 0.05,
    fill: { color: THEME.secondary },
  });
  
  // Title
  slide.addText(title, {
    x: 0.8, y: 1.2, w: 11.7, h: 1.5,
    fontSize: 40, fontFace: "Arial",
    color: THEME.white, bold: true,
    align: "center", valign: "bottom",
  });
  
  // Subtitle
  slide.addText(subtitle, {
    x: 1.5, y: 3.2, w: 10.3, h: 0.8,
    fontSize: 20, fontFace: "Arial",
    color: THEME.light, align: "center",
  });
  
  // Author & Date
  const footerText = [author, date].filter(Boolean).join(" | ");
  if (footerText) {
    slide.addText(footerText, {
      x: 0.8, y: 6.3, w: 11.7, h: 0.5,
      fontSize: 12, fontFace: "Arial",
      color: THEME.medium, align: "center",
    });
  }
  
  return slide;
}
```

### Section Header Slide
```javascript
function addSectionSlide(pptx, sectionTitle, sectionNumber = null) {
  const slide = pptx.addSlide();
  slide.background = { color: THEME.white };
  
  // Left accent bar
  slide.addShape(pptx.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.3, h: "100%",
    fill: { color: THEME.secondary },
  });
  
  // Section number (optional)
  if (sectionNumber) {
    slide.addText(String(sectionNumber).padStart(2, "0"), {
      x: 0.8, y: 1.5, w: 2, h: 1.5,
      fontSize: 72, fontFace: "Arial",
      color: THEME.light, bold: true,
    });
  }
  
  // Section title
  slide.addText(sectionTitle, {
    x: 2.5, y: 2, w: 9, h: 2,
    fontSize: 36, fontFace: "Arial",
    color: THEME.primary, bold: true,
  });
  
  // Bottom line
  slide.addShape(pptx.shapes.RECTANGLE, {
    x: 2.5, y: 4.2, w: 3, h: 0.05,
    fill: { color: THEME.secondary },
  });
  
  return slide;
}
```

### Content Slide with Bullet Points
```javascript
function addContentSlide(pptx, title, bulletPoints, options = {}) {
  const slide = pptx.addSlide();
  slide.background = { color: THEME.white };
  
  // Title bar
  slide.addShape(pptx.shapes.RECTANGLE, {
    x: 0, y: 0, w: "100%", h: 0.9,
    fill: { color: THEME.primary },
  });
  
  slide.addText(title, {
    x: 0.8, y: 0.1, w: 11.7, h: 0.7,
    fontSize: 24, fontFace: "Arial",
    color: THEME.white, bold: true,
  });
  
  // Bullet points
  const textRows = bulletPoints.map(point => ({
    text: point,
    options: {
      bullet: { type: "bullet", color: THEME.secondary },
      fontSize: 16, fontFace: "Arial",
      color: THEME.black,
      paraSpaceAfter: 8,
      indentLevel: 0,
    }
  }));
  
  slide.addText(textRows, {
    x: 0.8, y: 1.2, w: options.twoColumn ? 5.5 : 11.7, h: 5,
    valign: "top",
  });
  
  // Page number
  slide.addText(`${pptx.slides.length}`, {
    x: 12, y: 7, w: 0.8, h: 0.3,
    fontSize: 10, fontFace: "Arial",
    color: THEME.medium, align: "right",
  });
  
  return slide;
}
```

### Two-Column Content Slide
```javascript
function addTwoColumnSlide(pptx, title, leftContent, rightContent) {
  const slide = pptx.addSlide();
  slide.background = { color: THEME.white };
  
  // Title bar
  slide.addShape(pptx.shapes.RECTANGLE, {
    x: 0, y: 0, w: "100%", h: 0.9,
    fill: { color: THEME.primary },
  });
  
  slide.addText(title, {
    x: 0.8, y: 0.1, w: 11.7, h: 0.7,
    fontSize: 24, fontFace: "Arial",
    color: THEME.white, bold: true,
  });
  
  // Left column
  const leftRows = leftContent.map(point => ({
    text: point,
    options: {
      bullet: true, fontSize: 14,
      fontFace: "Arial", color: THEME.black,
    }
  }));
  
  slide.addText(leftRows, {
    x: 0.5, y: 1.2, w: 5.8, h: 5,
    valign: "top",
  });
  
  // Divider line
  slide.addShape(pptx.shapes.LINE, {
    x: 6.5, y: 1.2, w: 0, h: 5,
    line: { color: THEME.light, width: 1 },
  });
  
  // Right column
  const rightRows = rightContent.map(point => ({
    text: point,
    options: {
      bullet: true, fontSize: 14,
      fontFace: "Arial", color: THEME.black,
    }
  }));
  
  slide.addText(rightRows, {
    x: 6.8, y: 1.2, w: 5.8, h: 5,
    valign: "top",
  });
  
  return slide;
}
```

### Image Slide
```javascript
function addImageSlide(pptx, title, imagePath, caption = "", options = {}) {
  const slide = pptx.addSlide();
  slide.background = { color: THEME.white };
  
  // Title
  if (title) {
    slide.addText(title, {
      x: 0.5, y: 0.2, w: 12, h: 0.7,
      fontSize: 22, fontFace: "Arial",
      color: THEME.primary, bold: true,
    });
  }
  
  // Image (centered, with max dimensions)
  const imgWidth = options.width || 8;
  const imgHeight = options.height || 5;
  const imgX = (13.33 - imgWidth) / 2;
  const imgY = title ? 1.1 : 0.5;
  
  slide.addImage({
    path: imagePath,
    x: imgX, y: imgY, w: imgWidth, h: imgHeight,
    sizing: { type: "contain", w: imgWidth, h: imgHeight },
  });
  
  // Caption
  if (caption) {
    slide.addText(caption, {
      x: 0.5, y: imgY + imgHeight + 0.2, w: 12, h: 0.4,
      fontSize: 11, fontFace: "Arial",
      color: THEME.medium, align: "center", italic: true,
    });
  }
  
  return slide;
}
```

### Table Slide
```javascript
function addTableSlide(pptx, title, headers, rows) {
  const slide = pptx.addSlide();
  slide.background = { color: THEME.white };
  
  // Title
  slide.addText(title, {
    x: 0.5, y: 0.2, w: 12, h: 0.7,
    fontSize: 24, fontFace: "Arial",
    color: THEME.primary, bold: true,
  });
  
  // Prepare table data
  const tableData = [headers, ...rows];
  
  // Calculate column widths
  const colCount = headers.length;
  const totalWidth = 12;
  const colW = Array(colCount).fill(totalWidth / colCount);
  
  slide.addTable(tableData, {
    x: 0.5, y: 1.2, w: totalWidth,
    colW: colW,
    border: { type: "solid", pt: 0.5, color: "BDC3C7" },
    fontFace: "Arial",
    fontSize: 12,
    rowH: [0.5, ...Array(rows.length).fill(0.4)],
    autoPage: false,
  }, {
    // Header row styling
    fill: { color: THEME.primary },
    color: THEME.white,
    bold: true,
    fontSize: 13,
  });
  
  return slide;
}
```

### Chart Slide
```javascript
function addChartSlide(pptx, title, chartType, chartData, options = {}) {
  const slide = pptx.addSlide();
  slide.background = { color: THEME.white };
  
  // Title
  slide.addText(title, {
    x: 0.5, y: 0.2, w: 12, h: 0.7,
    fontSize: 24, fontFace: "Arial",
    color: THEME.primary, bold: true,
  });
  
  // Add chart
  slide.addChart(pptx.charts[chartType], chartData, {
    x: 0.8, y: 1.2, w: 11.5, h: 5.5,
    showTitle: false,
    showLegend: true,
    legendPos: "b",
    legendFontSize: 10,
    catAxisLabelFontSize: 10,
    valAxisLabelFontSize: 10,
    chartColors: options.colors || [THEME.secondary, THEME.primary, THEME.accent, THEME.success],
    dataLabelPosition: "outEnd",
    showValue: true,
    dataLabelFontSize: 9,
  });
  
  return slide;
}

// Usage: Bar chart
const chartData = [
  { name: "Q1", labels: ["Product A", "Product B", "Product C"], values: [12, 8, 5] },
  { name: "Q2", labels: ["Product A", "Product B", "Product C"], values: [15, 10, 7] },
];
addChartSlide(pptx, "Quarterly Sales", "BAR", chartData);

// Usage: Pie chart
const pieData = [
  { name: "Market Share", labels: ["Company A", "Company B", "Company C"], values: [45, 30, 25] },
];
addChartSlide(pptx, "Market Share", "DOUGHNUT", pieData);
```

---

## Complete Presentation Example: Pitch Deck

```javascript
const pptxgen = require("pptxgenjs");
const fs = require("fs");

const pptx = new pptxgen();
pptx.layout = "LAYOUT_WIDE";
pptx.title = "Startup Pitch Deck";
pptx.author = "Wazzap Agent";

const T = {
  primary: "1B3A5C", secondary: "3498DB",
  accent: "E74C3C", success: "27AE60",
  dark: "2C3E50", medium: "7F8C8D",
  light: "ECF0F1", white: "FFFFFF", black: "333333",
};

// --- SLIDE 1: TITLE ---
const s1 = pptx.addSlide();
s1.background = { color: T.primary };
s1.addText("STARTUP NAME", {
  x: 1, y: 1.5, w: 11, h: 1.5,
  fontSize: 48, fontFace: "Arial", color: T.white, bold: true, align: "center",
});
s1.addText("Revolutionizing [Industry] with [Solution]", {
  x: 1, y: 3.2, w: 11, h: 0.8,
  fontSize: 20, fontFace: "Arial", color: T.light, align: "center",
});
s1.addText("Pitch Deck 2025", {
  x: 1, y: 6.5, w: 11, h: 0.5,
  fontSize: 12, fontFace: "Arial", color: T.medium, align: "center",
});

// --- SLIDE 2: PROBLEM ---
const s2 = pptx.addSlide();
s2.background = { color: T.white };
s2.addShape(pptx.shapes.RECTANGLE, { x: 0, y: 0, w: "100%", h: 0.9, fill: { color: T.primary } });
s2.addText("THE PROBLEM", {
  x: 0.8, y: 0.1, w: 11.7, h: 0.7,
  fontSize: 28, fontFace: "Arial", color: T.white, bold: true,
});
s2.addText([
  { text: "75% of businesses struggle with X\n", options: { bullet: true, fontSize: 18, color: T.black } },
  { text: "Current solutions are expensive and slow\n", options: { bullet: true, fontSize: 18, color: T.black } },
  { text: "Market lacks an integrated platform\n", options: { bullet: true, fontSize: 18, color: T.black } },
], { x: 0.8, y: 1.5, w: 11, h: 4, valign: "top" });

// --- SLIDE 3: SOLUTION ---
const s3 = pptx.addSlide();
s3.background = { color: T.white };
s3.addShape(pptx.shapes.RECTANGLE, { x: 0, y: 0, w: "100%", h: 0.9, fill: { color: T.success } });
s3.addText("OUR SOLUTION", {
  x: 0.8, y: 0.1, w: 11.7, h: 0.7,
  fontSize: 28, fontFace: "Arial", color: T.white, bold: true,
});
s3.addText("AI-powered platform that automates X, reduces costs by 60%, and integrates seamlessly.", {
  x: 0.8, y: 1.5, w: 11, h: 1,
  fontSize: 18, fontFace: "Arial", color: T.dark, valign: "top",
});

// Key features in boxes
const features = [
  { title: "Fast", desc: "10x faster than competitors" },
  { title: "Smart", desc: "AI-driven automation" },
  { title: "Easy", desc: "No-code integration" },
];
features.forEach((feat, i) => {
  const x = 0.8 + (i * 4.2);
  s3.addShape(pptx.shapes.ROUNDED_RECTANGLE, {
    x: x, y: 3, w: 3.8, h: 2.5,
    fill: { color: T.light },
    rectRadius: 0.2,
  });
  s3.addText(feat.title, {
    x: x + 0.3, y: 3.3, w: 3.2, h: 0.6,
    fontSize: 20, fontFace: "Arial", color: T.primary, bold: true,
  });
  s3.addText(feat.desc, {
    x: x + 0.3, y: 4.1, w: 3.2, h: 0.8,
    fontSize: 14, fontFace: "Arial", color: T.medium,
  });
});

// --- SLIDE 4: MARKET ---
const s4 = pptx.addSlide();
s4.background = { color: T.white };
s4.addShape(pptx.shapes.RECTANGLE, { x: 0, y: 0, w: "100%", h: 0.9, fill: { color: T.primary } });
s4.addText("MARKET OPPORTUNITY", {
  x: 0.8, y: 0.1, w: 11.7, h: 0.7,
  fontSize: 28, fontFace: "Arial", color: T.white, bold: true,
});
s4.addChart(pptx.charts.BAR, [
  { name: "TAM", labels: ["Total Addressable"], values: [50] },
  { name: "SAM", labels: ["Serviceable"], values: [20] },
  { name: "SOM", labels: ["Obtainable"], values: [5] },
], {
  x: 0.8, y: 1.5, w: 11, h: 5,
  showTitle: false, showLegend: true, legendPos: "b",
  chartColors: [T.secondary, T.primary, T.accent],
  valAxisHidden: false,
});

// --- SLIDE 5: CTA ---
const s5 = pptx.addSlide();
s5.background = { color: T.primary };
s5.addText("LET'S TALK", {
  x: 1, y: 2, w: 11, h: 1.5,
  fontSize: 48, fontFace: "Arial", color: T.white, bold: true, align: "center",
});
s5.addText("contact@startup.com | startup.com", {
  x: 1, y: 4, w: 11, h: 0.8,
  fontSize: 18, fontFace: "Arial", color: T.light, align: "center",
});

// SAVE
pptx.writeFile({ fileName: "pitch_deck.pptx" })
  .then(() => console.log("✓ Pitch deck created"))
  .catch(err => console.error("Error:", err));
```

---

## Creating Presentations with python-pptx (Python)

### Basic Setup
```python
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

prs = Presentation()
prs.slide_width = Inches(13.333)  # 16:9 wide
prs.slide_height = Inches(7.5)

# Theme colors
class Theme:
    PRIMARY = RGBColor(0x1B, 0x3A, 0x5C)
    SECONDARY = RGBColor(0x34, 0x98, 0xDB)
    ACCENT = RGBColor(0xE7, 0x4C, 0x3C)
    SUCCESS = RGBColor(0x27, 0xAE, 0x60)
    DARK = RGBColor(0x2C, 0x3E, 0x50)
    MEDIUM = RGBColor(0x7F, 0x8C, 0x8D)
    LIGHT = RGBColor(0xEC, 0xF0, 0xF1)
    WHITE = RGBColor(0xFF, 0xFF, 0xFF)
    BLACK = RGBColor(0x33, 0x33, 0x33)
```

### Title Slide
```python
def add_title_slide(prs, title, subtitle="", author="", date_str=""):
    """Add a styled title slide."""
    slide_layout = prs.slide_layouts[6]  # Blank
    slide = prs.slides.add_slide(slide_layout)
    
    # Background
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = Theme.PRIMARY
    
    # Title
    left = Inches(1)
    top = Inches(2)
    width = Inches(11.333)
    height = Inches(1.5)
    
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = title
    p.font.size = Pt(40)
    p.font.bold = True
    p.font.color.rgb = Theme.WHITE
    p.alignment = PP_ALIGN.CENTER
    
    # Subtitle
    if subtitle:
        txBox2 = slide.shapes.add_textbox(Inches(1), Inches(3.8), Inches(11.333), Inches(0.8))
        tf2 = txBox2.text_frame
        p2 = tf2.paragraphs[0]
        p2.text = subtitle
        p2.font.size = Pt(20)
        p2.font.color.rgb = Theme.LIGHT
        p2.alignment = PP_ALIGN.CENTER
    
    # Author & Date footer
    if author or date_str:
        txBox3 = slide.shapes.add_textbox(Inches(1), Inches(6.3), Inches(11.333), Inches(0.5))
        tf3 = txBox3.text_frame
        p3 = tf3.paragraphs[0]
        p3.text = " | ".join(filter(None, [author, date_str]))
        p3.font.size = Pt(12)
        p3.font.color.rgb = Theme.MEDIUM
        p3.alignment = PP_ALIGN.CENTER
    
    return slide
```

### Content Slide with Bullet Points
```python
def add_content_slide(prs, title, bullets):
    """Add a content slide with bullet points."""
    slide_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(slide_layout)
    
    # Title bar background
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, Inches(0.9))
    shape.fill.solid()
    shape.fill.fore_color.rgb = Theme.PRIMARY
    shape.line.fill.background()
    
    # Title text
    txBox = slide.shapes.add_textbox(Inches(0.8), Inches(0.1), Inches(11.7), Inches(0.7))
    tf = txBox.text_frame
    p = tf.paragraphs[0]
    p.text = title
    p.font.size = Pt(24)
    p.font.bold = True
    p.font.color.rgb = Theme.WHITE
    
    # Bullet points
    txBox2 = slide.shapes.add_textbox(Inches(0.8), Inches(1.3), Inches(11.7), Inches(5))
    tf2 = txBox2.text_frame
    tf2.word_wrap = True
    
    for i, bullet in enumerate(bullets):
        if i == 0:
            p = tf2.paragraphs[0]
        else:
            p = tf2.add_paragraph()
        p.text = bullet
        p.font.size = Pt(16)
        p.font.color.rgb = Theme.BLACK
        p.space_after = Pt(8)
        p.level = 0
    
    return slide
```

### Save Presentation
```python
prs.save("presentation.pptx")
print("✓ Presentation created")
```

---

## Shapes & Styling Reference (pptxgenjs)

### Available Shapes
```javascript
// Commonly used shapes
pptx.shapes.RECTANGLE
pptx.shapes.ROUNDED_RECTANGLE
pptx.shapes.OVAL          // Circle/Ellipse
pptx.shapes.LINE
pptx.shapes.TRIANGLE
pptx.shapes.RIGHT_ARROW
pptx.shapes.CHEVRON
pptx.shapes.STAR_5_POINT
pptx.shapes.HEART
pptx.shapes.DIAMOND
```

### Shape Styling
```javascript
slide.addShape(pptx.shapes.ROUNDED_RECTANGLE, {
  x: 1, y: 1, w: 4, h: 2,
  fill: { color: "3498DB" },          // Solid fill
  // fill: { type: "gradient", stops: [...] },  // Gradient fill
  line: { color: "2C3E50", width: 1 },  // Border
  rectRadius: 0.2,                     // Corner radius for rounded rect
  shadow: { type: "outer", blur: 6, offset: 2, color: "000000", opacity: 0.3 },
  rotate: 0,                           // Rotation in degrees
});
```

### Text Formatting Options
```javascript
slide.addText("Styled Text", {
  x: 1, y: 1, w: 5, h: 1,
  fontSize: 24,
  fontFace: "Arial",
  color: "333333",
  bold: true,
  italic: false,
  underline: { style: "sng", color: "FF0000" },
  strikethrough: false,
  align: "left",         // left, center, right, justify
  valign: "top",          // top, middle, bottom
  wrap: true,
  shrinkText: true,       // Auto-shrink to fit
  paraSpaceBefore: 6,
  paraSpaceAfter: 6,
  lineSpacingMultiple: 1.2,
  hyperlink: { url: "https://example.com" },
});
```

---

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| Image not showing | Path issue | Use absolute path; verify file exists |
| Font looks different | Font not in PPTX | Use standard fonts (Arial, Calibri, etc.) |
| Layout misaligned | Wrong coordinates | Remember: x=left, y=top, w=width, h=height |
| Chart data error | Wrong data format | Check pptxgenjs chart data format requirements |
| Large file size | Unoptimized images | Resize/compress images with Pillow before inserting |
| Blank slide | No shapes added | Verify addText/addShape calls are executed |
