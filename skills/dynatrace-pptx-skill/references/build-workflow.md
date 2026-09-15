# python-pptx Build Workflow

Read this before writing deck code. Covers: opening the template, the helper functions to
build on, the layout index table, and the gotchas that have actually broken decks before.

---

## 1. Open the template

python-pptx rejects `.potx` files directly. Fix once by patching `[Content_Types].xml` inside
the zip, then load the fixed copy:

```python
import zipfile, os

def _ensure_template(potx='assets/DT_template.potx', fixed='dt_template_fixed.pptx'):
    if os.path.exists(fixed):
        return fixed
    tmp = '_tmp_tmpl'
    with zipfile.ZipFile(potx) as z:
        z.extractall(tmp)
    ct_path = f'{tmp}/[Content_Types].xml'
    ct = open(ct_path).read().replace(
        'presentationml.template.main+xml',
        'presentationml.presentation.main+xml')
    open(ct_path, 'w').write(ct)
    os.system(f'cd {tmp} && zip -qr ../{fixed} .')
    return fixed
```

`Presentation(fixed)` then loads the template's 15 example slides — delete them before adding
content, or they appear at the front of the output:

```python
sldIdLst = prs.slides._sldIdLst
for sldId in list(sldIdLst):
    rId = sldId.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
    prs.part.drop_rel(rId)
    sldIdLst.remove(sldId)
```

## 2. Pick a layout (DT_template.potx — 64 layouts)

| Index | Name | Use |
|-------|------|-----|
| `[0]` | Title slide | Cover |
| `[20]` | Section Header | Section dividers |
| `[61]` | Blank_graphic | **All content slides** — only has SLIDE_NUMBER placeholder, no ghost icons |
| `[63]` | Thank you slide | Closing |

**Avoid `[6]` (`Title+content_left`)** — it has an OBJECT placeholder (idx=1) that renders as
"click to add content" ghost icons when unfilled.

## 3. Reusable helpers

None of the 64 layouts bake in the DT background image — add it explicitly on every slide.
`add_picture` appends to the front of the shape tree, so push it behind everything else:

```python
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

TEAL, WHITE = RGBColor(0x4A, 0xC2, 0xB3), RGBColor(0xFF, 0xFF, 0xFF)

def bg(slide, image='dt_content_bg.png'):
    pic = slide.shapes.add_picture(asset(image), 0, 0,
                                    width=Inches(13.333), height=Inches(7.5))
    slide.shapes._spTree.remove(pic._element)
    slide.shapes._spTree.insert(2, pic._element)  # push behind other shapes

def add_text(slide, text, x, y, w, h, size=16, bold=False, color=WHITE,
             align=PP_ALIGN.LEFT, font='DT Flow'):
    tf = slide.shapes.add_textbox(x, y, w, h).text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]; p.alignment = align
    run = p.add_run(); run.text = text
    run.font.size, run.font.bold, run.font.color.rgb, run.font.name = Pt(size), bold, color, font
    return tf

def slide_title(slide, text):
    # h=1.0 (not 0.7) — a 26pt bold title wraps to 2 lines when it carries a
    # "Scope - " or "Opportunity X of Y - " prefix; the box needs the room.
    add_text(slide, text, Inches(0.5), Inches(0.55), Inches(12.3), Inches(1.0),
             size=26, bold=True, color=WHITE)
    # Accent bar at y=1.6 (not 1.35) — a wrapped 2-line title's second line
    # renders to roughly y=1.5; 1.35 draws the bar straight through it.
    bar = slide.shapes.add_shape(1, Inches(0.5), Inches(1.6), Inches(12.3), Pt(2.5))
    bar.fill.solid(); bar.fill.fore_color.rgb = TEAL; bar.line.fill.background()
```

Use `dt_cover_bg.png` for the cover/closing slides, `dt_content_bg.png` for everything else.

Anything placed below the title's accent bar (stat cards, content cards, roadmap tables) must
start at y≥1.75" to clear it — the same wrap risk `slide_title()` guards against.

## 4. Typography scale

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

## 5. Layout patterns

### Cover Slide
```
[DT logo — top left]
                                    [particle wave — right half]
[PRESENTATION TITLE]
[Subtitle / date / presenter]
```
Title: white, 40pt+, bold, left-aligned, upper-left quadrant. Subtitle: teal `4AC2B3`, 20pt,
below title. Logo: SVG, top-left, ~1.2" wide, ~0.3" from edges.

### Section Divider
Full `1A2440` or cover bg. Large section number or label in teal. White heading centered or
left-aligned. Minimal text — one sentence max.

### Two-Column Content
Left: text / bullets. Right: image, chart, or stat callout. Divider: thin vertical line in
teal `4AC2B3`.

### Stat Callout Grid (2×2 or 3-up)
Large numbers (48–64pt, teal or white) with small label below (12pt, grey `6F747F`). Each stat
in a card with subtle `1A2440` fill and teal border or gradient border.

### Content Cards
Rounded rectangles (`roundness: 0.05`), fill `1A2440` or slightly lighter `172036`. Card
header: teal top border (4pt) or gradient left bar. Body text: white 13pt.

### Timeline / Roadmap
Horizontal spine in teal `4AC2B3`. Nodes as filled circles (teal or purple). Labels
above/below alternating. Quarter or date labels in grey `6F747F`.

### Closing / Thank You
Same as cover slide. "Thank you" or "Questions?" in large white text, teal accent line or
gradient shape beneath.

## 6. Gotchas

### Logo SVG → PNG conversion (qlmanage)
The DT logo SVG has white text on a transparent background. `qlmanage` adds a white
background, producing a white-on-white box. Fix: patch the SVG to add a navy rect before
converting.
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

### Punctuation hyphens
Use ` - ` (space on both sides) for em-dash replacements. Watch split-string concatenation:
`'text -'` + `'word'` renders as `text -word` — add trailing space to the first string:
`'text - '`.
