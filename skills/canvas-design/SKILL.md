---
name: canvas-design-agent
description: |
  Create original visual designs (posters, art, PDFs, PNGs) that look meticulously
  crafted and museum-quality. Use this skill when the user asks for a poster, piece
  of art, design, or other static visual artifact. Output only `.md`, `.pdf`, and
  `.png` files. Never copy existing artists' work.
---

# Canvas Design Agent

This skill produces **visual philosophies** and then **expresses them visually** as
a PDF or PNG. It is a two-step flow:

1. **Design Philosophy Creation** — a short `.md` aesthetic manifesto.
2. **Canvas Creation** — render that philosophy to a PDF (reportlab) or PNG (Pillow).

Output files go into the **current working directory (workdir)**. Do not use
absolute paths like `/output/`; that directory does not exist in the sidecar.

---

## Step 1 — Design Philosophy

Create a **visual philosophy**, not a layout or template. The philosophy will be
interpreted through form, space, color, composition, images, graphics, shapes,
patterns, and minimal text used as a visual accent.

### How to generate a visual philosophy

1. **Name the movement** (1–2 words): e.g. `"Brutalist Joy"`, `"Chromatic
   Silence"`, `"Metabolist Dreams"`.
2. **Write 4–6 concise paragraphs** describing how the philosophy manifests
   through:
   - Space and form
   - Color and material
   - Scale and rhythm
   - Composition and balance
   - Visual hierarchy

### Critical guidelines

- **Avoid redundancy.** Each design aspect should be mentioned once — don't
  repeat points about color theory, spatial relationships, or typography unless
  adding new depth.
- **Emphasize craftsmanship repeatedly.** The philosophy MUST stress multiple
  times that the final work should appear as though it took countless hours,
  was labored over with care, and comes from someone at the top of their field.
  Use phrases like "meticulously crafted", "the product of deep expertise",
  "painstaking attention", "master-level execution".
- **Leave creative space.** Be specific about the aesthetic direction, but
  concise enough that the render step has room to make interpretive choices at
  an equally high level of craftsmanship.
- **Stay generic.** Don't bake in the literal subject of the user's request —
  the philosophy should read as though it could apply to any artifact in that
  aesthetic.

Save the philosophy as `./philosophy.md` (or similar) in the workdir.

### Philosophy examples (condensed)

**"Concrete Poetry"** — Communication through monumental form and bold geometry.
Massive color blocks, sculptural typography (huge single words, tiny labels),
Brutalist spatial divisions, Polish poster energy meets Le Corbusier. Ideas
expressed through visual weight and spatial tension, not explanation. Every
element placed with the precision of a master craftsman.

**"Chromatic Language"** — Color as the primary information system. Geometric
precision where color zones create meaning. Typography minimal — small
sans-serif labels letting chromatic fields communicate. Josef Albers meets
data visualization. The result of painstaking chromatic calibration.

**"Analog Meditation"** — Quiet visual contemplation through texture and
breathing room. Paper grain, ink bleeds, vast negative space. Photography and
illustration dominate. Typography whispered. Japanese photobook aesthetic.

**"Organic Systems"** — Natural clustering and modular growth patterns. Rounded
forms, organic arrangements, color from nature through architecture. Information
shown through visual diagrams, spatial relationships, iconography.

**"Geometric Silence"** — Pure order and restraint. Grid-based precision, bold
photography or stark graphics, dramatic negative space. Swiss formalism meets
Brutalist material honesty. Structure communicates, not words.

---

## Step 2 — Deduce the Subtle Reference

Before rendering, identify the **subtle conceptual thread** from the original
request. The topic should be a refined reference embedded within the art —
someone familiar with the subject feels it intuitively; others simply experience
a masterful abstract composition. Think of a jazz musician quoting another
song: only those who know catch it, but everyone enjoys the music.

---

## Step 3 — Canvas Creation

With philosophy + subtle reference established, render a single-page, highly
visual, design-forward PDF or PNG (unless more pages are requested).

- Use **repeating patterns and perfect shapes**; build meaning through patient
  repetition.
- Add **sparse, clinical typography** and systematic reference markers.
- Use a **limited, intentional color palette**.
- Never let text, graphics, or visual elements fall off the canvas or overlap.
  Every element must sit within canvas boundaries with proper margins.

### Available fonts

The `canvas-fonts/` directory sits next to this SKILL.md inside the read-only
`/skills/` mount. From the workdir, reference fonts via the absolute path:

```
/skills/canvas-design/canvas-fonts/<FontName>-Regular.ttf
```

Do **not** use `./canvas-fonts/` — the agent's current working directory is the
session workdir, not the skill directory.

The fonts are NOT indexed by `fontconfig`, so bare family names like `"Outfit"`
won't resolve. You must load each TTF explicitly:

#### Load a TTF in reportlab

```python
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

FONT_DIR = "/skills/canvas-design/canvas-fonts"
pdfmetrics.registerFont(TTFont("Outfit", f"{FONT_DIR}/Outfit-Regular.ttf"))
pdfmetrics.registerFont(TTFont("Outfit-Bold", f"{FONT_DIR}/Outfit-Bold.ttf"))

c = canvas.Canvas("./poster.pdf", pagesize=A4)
c.setFont("Outfit-Bold", 64)
c.drawString(72, 720, "CONCRETE POETRY")
c.setFont("Outfit", 12)
c.drawString(72, 690, "A study in monumental form.")
c.save()
```

#### Load a TTF in Pillow

```python
from PIL import Image, ImageDraw, ImageFont

FONT_DIR = "/skills/canvas-design/canvas-fonts"
img = Image.new("RGB", (2000, 2800), "#F4EFE6")
draw = ImageDraw.Draw(img)

title = ImageFont.truetype(f"{FONT_DIR}/BigShoulders-Bold.ttf", size=220)
body  = ImageFont.truetype(f"{FONT_DIR}/IBMPlexSerif-Regular.ttf", size=44)

draw.text((140, 180), "CHROMATIC", font=title, fill="#1B1B1B")
draw.text((140, 420), "LANGUAGE",  font=title, fill="#C63B2F")
draw.text((140, 780), "A quiet study in chromatic calibration.", font=body, fill="#333333")

img.save("./poster.png", "PNG", optimize=True)
```

### Rendering tips

- **Prefer reportlab for PDFs**, Pillow for PNGs. Pillow can also composite
  raster textures, gradients, and paper-grain overlays.
- **Repeating patterns** are cheap and powerful: render a motif inside a tight
  grid with `for x in range(...)`/`for y in range(...)` loops.
- **Breathing room** is non-negotiable — when in doubt, widen margins.
- Limit yourself to **2–4 colors** plus one neutral. Pick a HEX palette up front
  and reuse it everywhere.
- **Text as contextual element**: minimal and visual-first. A punk venue poster
  may use heavy, aggressive type; a minimalist identity whispers. Most fonts
  should be thin. No element should overlap or overflow the canvas.

---

## Final polish pass

After the first render, **do a second pass**. Look at the output and refine
what is already there — don't add more graphics. Make the composition crisper
and more cohesive. When tempted to draw a new shape, instead ask: *"How can I
make what's already here more of a piece of art?"*

This is often the difference between an acceptable design and a museum-quality
one.

---

## Multi-page option

If multiple pages are requested, bundle them into a single PDF (preferred) or
multiple PNGs. Treat the first page as one spread in a coffee-table book;
subsequent pages should be distinct variations that echo the philosophy — a
loose visual story, not repetition.

---

## Output checklist

- `./philosophy.md` — the design manifesto
- `./poster.pdf` or `./poster.png` (or both) — the final artifact(s)

Declare only the final deliverables in `end_task(output_files=[...])`. Do not
include scratch files, intermediate renders, or the font directory.
