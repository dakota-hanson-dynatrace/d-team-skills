---
name: dynatrace-pptx
description: >
  Build PowerPoint presentations using the official Dynatrace 2026 Corporate Brand Template.
  Use this skill ANY TIME a Dynatrace employee asks to create a presentation, deck, slides,
  or pitch — even if they don't say "Dynatrace template" explicitly. This skill MUST be used
  for all DT slide creation to ensure brand compliance. It applies the correct backgrounds,
  colors, fonts, and layout patterns from the official TPLT_Corporate_PPT_2026 template.
  Triggers: "build a deck", "create slides", "make a presentation", "put together a pitch",
  "DT presentation", "Dynatrace slides", or any request to produce a .pptx file.
---

# Dynatrace Corporate PowerPoint Skill

Always follow the [pptx skill](../pptx/SKILL.md) workflow when building slides. This skill
adds Dynatrace brand constraints on top of that base workflow.

---

## Brand Foundations

### Colors

| Role | Hex | Use |
|------|-----|-----|
| **Navy (primary bg)** | `1A2440` | Dark slide backgrounds, section dividers |
| **True black** | `000000` | Deep dark elements |
| **White** | `FFFFFF` | Text on dark, light slide bg |
| **Mid-grey** | `6F747F` | Captions, secondary text |
| **Teal (Accent 1)** | `4AC2B3` | Primary accent, CTAs, highlights |
| **Sky Blue (Accent 2)** | `3BACF0` | Secondary accent, charts |
| **Electric Blue (Accent 3)** | `1966FF` | Links, interactive elements |
| **Purple (Accent 4)** | `5E29E5` | Gradient starts, premium feel |
| **Violet (Accent 5)** | `8D1CDC` | Gradient midpoints |
| **Magenta (Accent 6)** | `C93FDB` | Gradient ends, energy accents |

**Gradient rule**: The signature DT brand gradient runs Purple → Violet → Magenta (`5E29E5` → `8D1CDC` → `C93FDB`). Use it for decorative lines, pill shapes, and callout borders.

### Fonts

The font name in python-pptx (and PowerPoint) is **`'DT Flow'`** — use this string directly for every `run.font.name` and `font=` parameter. Medium/Light weight is handled by the `bold` flag, not separate font names.

| Element | python-pptx / pptxgenjs value |
|---------|-------------------------------|
| All elements | `'DT Flow'` |

### Typography Scale

Verified working sizes from production builds:

| Element | Size | Weight | Color |
|---------|------|--------|-------|
| Cover title | 42pt | Bold | White |
| Cover subtitle | 22pt | Regular | `4AC2B3` teal |
| Section header placeholder | 40pt | Bold | White |
| Slide title | 26pt | Bold | White |
| Card / callout title | 19pt | Bold | White |
| Body text | 17pt | Regular | White or `6F747F` |
| Labels / next-step text | 15pt | Regular/Bold | `4AC2B3` or `6F747F` |
| Badge labels | 13pt | Bold | White |
| Stat big number | 42pt | Bold | `4AC2B3` |
| Stat label | 15pt | Regular | `6F747F` |
| Roadmap header | 15pt | Bold | Navy |
| Roadmap row | 14pt | Regular | White |

---

## Slide Backgrounds

### Cover / Title slide
Use `assets/dt_cover_bg.png` as a full-bleed background (12192000 × 6858000 EMU = 10" × 7.5").
Place the Dynatrace logo (`assets/dt_logo.svg`) top-left (~0.3" from edges, ~1.2" wide).
Title text sits in the upper-left quadrant (dark area); keep the right side visually open for
the light-wave graphic.

```js
// pptxgenjs: cover slide background
slide.background = { data: fs.readFileSync('assets/dt_cover_bg.png').toString('base64'), type: 'png' };
```

### Content slides
Use `assets/dt_content_bg.png` as full-bleed background. This is a deep navy with subtle
particle effects at the bottom corners — text above the bottom 15% of the slide is safe.

```js
slide.background = { data: fs.readFileSync('assets/dt_content_bg.png').toString('base64'), type: 'png' };
```

### Light variant (optional)
For data-heavy slides where readability matters, use a plain `1A2440` navy fill with white text
instead of the image background.

---

## Layout Patterns

### 1. Cover Slide
```
[DT logo — top left]
                                    [particle wave — right half]
[PRESENTATION TITLE]                
[Subtitle / date / presenter]
```
- Title: white, 40pt+, bold, left-aligned, upper-left quadrant
- Subtitle: teal `4AC2B3`, 20pt, below title
- Logo: SVG, top-left, ~1.2" wide

### 2. Section Divider
Full `1A2440` or cover bg. Large section number or label in teal. White heading centered or
left-aligned. Minimal text — one sentence max.

### 3. Two-Column Content
Left: text / bullets. Right: image, chart, or stat callout.
Divider: thin vertical line in teal `4AC2B3`.

### 4. Stat Callout Grid (2×2 or 3-up)
Large numbers (48–64pt, teal or white) with small label below (12pt, grey `6F747F`).
Each stat in a card with subtle `1A2440` fill and teal border or gradient border.

### 5. Content Cards
Rounded rectangles (`roundness: 0.05`), fill `1A2440` or slightly lighter `172036`.
Card header: teal top border (4pt) or gradient left bar.
Body text: white 13pt.

### 6. Timeline / Roadmap
Horizontal spine in teal `4AC2B3`. Nodes as filled circles (teal or purple).
Labels above/below alternating. Quarter or date labels in grey `6F747F`.

### 7. Closing / Thank You
Same as cover slide. "Thank you" or "Questions?" in large white text, teal accent line or
gradient shape beneath.

---

## pptxgenjs Quick Setup

```js
const pptx = new PptxGenJS();
pptx.layout = 'LAYOUT_WIDE'; // 13.33" × 7.5"
pptx.author = 'Dynatrace';

// Helper: load asset as base64
const assetB64 = (name) =>
  require('fs').readFileSync(`${__dirname}/assets/${name}`).toString('base64');

// Cover slide
const cover = pptx.addSlide();
cover.background = { data: assetB64('dt_cover_bg.png'), type: 'png' };
cover.addImage({ data: assetB64('dt_logo.svg'), type: 'svg', x: 0.3, y: 0.25, w: 1.2, h: 0.4 });
cover.addText('PRESENTATION TITLE', {
  x: 0.5, y: 1.5, w: 6.5, h: 1.2,
  fontSize: 44, bold: true, color: 'FFFFFF', fontFace: 'DT Flow',
  align: 'left', valign: 'middle'
});
cover.addText('Subtitle · Presenter · Date', {
  x: 0.5, y: 2.9, w: 6, h: 0.5,
  fontSize: 20, color: '4AC2B3', fontFace: 'DT Flow', align: 'left'
});

// Content slide
const slide = pptx.addSlide();
slide.background = { data: assetB64('dt_content_bg.png'), type: 'png' };
slide.addImage({ data: assetB64('dt_logo.svg'), type: 'svg', x: 0.3, y: 0.2, w: 1.0, h: 0.33 });
slide.addText('Slide Title', {
  x: 0.5, y: 0.7, w: 12.3, h: 0.7,
  fontSize: 26, bold: true, color: 'FFFFFF', fontFace: 'DT Flow', align: 'left'
});
// Teal accent line under title
slide.addShape(pptx.ShapeType.rect, {
  x: 0.5, y: 1.35, w: 12.3, h: 0.03, fill: { color: '4AC2B3' }
});
```

---

## QA Checklist

Before delivering any DT deck, verify:

- [ ] Cover uses `dt_cover_bg.png`, content slides use `dt_content_bg.png`
- [ ] No white backgrounds (all slides dark navy or cover image)
- [ ] Content slides use layout `[61]` (Blank_graphic) — not `[6]` which produces ghost icons
- [ ] Template's 15 example slides deleted before adding content (python-pptx)
- [ ] Titles white, accents teal `4AC2B3`
- [ ] Font is `DT Flow` throughout — no `Trebuchet MS` or `Calibri` remnants
- [ ] No generic blue (#0070C0 etc.) — use DT palette only
- [ ] Gradient used at least once (Purple→Violet→Magenta) for a decorative element
- [ ] Text boxes sized with enough height for wrapped content — open in PowerPoint and scan for overflows
- [ ] Punctuation hyphens have spaces on both sides (` - `) including across split Python strings

---

## Asset Manifest

| File | Description |
|------|-------------|
| `assets/DT_template.potx` | Full official PowerPoint template (all 15 slide layouts) |
| `assets/dt_cover_bg.png` | Cover slide background (dark with light-wave particles) |
| `assets/dt_content_bg.png` | Content slide background (deep navy, subtle corner particles) |
| `assets/dt_logo.svg` | Dynatrace logo SVG |

To use the official `.potx` directly in python-pptx (editing workflow), open it as a template:
```python
from pptx import Presentation
prs = Presentation('assets/DT_template.potx')
# Add slides using prs.slide_layouts[N] to inherit full DT theming
```

---

## python-pptx Gotchas

### Content-type fix for .potx
python-pptx rejects `.potx` files. Fix once by patching `[Content_Types].xml` inside the zip:
```python
import zipfile, shutil, os

shutil.copy('assets/DT_template.potx', 'dt_template_fixed.pptx')
with zipfile.ZipFile('dt_template_fixed.pptx', 'r') as z:
    z.extractall('_tmp')
ct = open('_tmp/[Content_Types].xml').read().replace(
    'presentationml.template.main+xml',
    'presentationml.presentation.main+xml')
open('_tmp/[Content_Types].xml', 'w').write(ct)
# repack: cd _tmp && zip -qr ../dt_template_fixed.pptx .
```

### Delete template slides before adding content
`Presentation('dt_template_fixed.pptx')` loads the template's 15 example slides. Delete them first or they appear at the front of the output:
```python
sldIdLst = prs.slides._sldIdLst
for sldId in list(sldIdLst):
    rId = sldId.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
    prs.part.drop_rel(rId)
    sldIdLst.remove(sldId)
```

### Slide layout selection (DT_template.potx — 64 layouts)
| Index | Name | Use |
|-------|------|-----|
| `[0]` | Title slide | Cover |
| `[20]` | Section Header | Section dividers |
| `[61]` | Blank_graphic | **All content slides** — only has SLIDE_NUMBER placeholder, no ghost icons |
| `[63]` | Thank you slide | Closing |

**Avoid `[6]` (`Title+content_left`)** — it has an OBJECT placeholder (idx=1) that renders as "click to add content" ghost icons when unfilled.

### Full-bleed background z-order
`add_picture` appends to the front of the shape tree. Push it behind everything else:
```python
def bg(slide, image):
    pic = slide.shapes.add_picture(asset(image), 0, 0,
                                   width=Emu(12192000), height=Emu(6858000))
    slide.shapes._spTree.remove(pic._element)
    slide.shapes._spTree.insert(2, pic._element)  # behind all other shapes
```

### Logo SVG → PNG conversion (qlmanage)
The DT logo SVG has white text on a transparent background. `qlmanage` adds a white background, producing a white-on-white box. Fix: patch the SVG to add a navy rect before converting.
```python
import re
svg = open('assets/dt_logo.svg').read()
m = re.search(r'viewBox=["\']([^"\']+)["\']', svg)
w, h = m.group(1).split()[2], m.group(1).split()[3]
svg = re.sub(r'(<svg[^>]*>)', r'\1' + f'<rect width="{w}" height="{h}" fill="#1A2440"/>', svg, 1)
open('dt_logo_navy.svg', 'w').write(svg)
# qlmanage -t -s 400 -o . dt_logo_navy.svg
# Then crop output: qlmanage squares it, crop to actual aspect ratio
```

### Content card geometry (gap card pattern)
Verified layout that avoids body/next-step overlap at 17pt body text:
```
badge:     x=0.5",  y=1.55",  w=1.3",   h=0.28"   ← 1.3" min for "START HERE"
title:     x+1.45", y=1.55",  w=10.8",  h=0.65"   ← 0.65" for 2-line bold title
body:      x+0.3",  y+0.75",  w=11.6",  h=2.8"
next box:  x=0.5",  y+3.8",   w=12.3",  h=1.4"    ← ends at 6.75" within 7.5" slide
label:     x+0.15", y+3.85",  w=2.4",   h=0.35"
fix text:  x+0.15", y+4.23",  w=12.0",  h=0.9"
```

### Punctuation hyphens
Use ` - ` (space on both sides) for em-dash replacements. Watch split-string concatenation: `'text -'` + `'word'` renders as `text -word` — add trailing space to the first string: `'text - '`.
