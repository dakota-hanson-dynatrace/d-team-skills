---
name: dynatrace-pptx
description: >
  Build PowerPoint presentations using the official Dynatrace 2026 Corporate Brand Template.
  Use this skill ANY TIME a Dynatrace employee asks to create a presentation, deck, slides,
  or pitch — even if they don't say "Dynatrace template" explicitly. This skill MUST be used
  for all DT slide creation to ensure brand compliance. It applies the correct backgrounds,
  colors, fonts, and layout patterns from the official TPLT_Corporate_PPT_2026 template.
  Triggers: "build a deck", "create slides", "make a presentation", "put together a pitch",
  "DT presentation", "Dynatrace slides", or any request to produce a .pptx file. Not for the
  Value Roadmap deck specifically — that's the separate `dt-value-roadmap` skill, which
  builds on this one's assets.
---

# Dynatrace Corporate PowerPoint Skill

Generic DT-branded PowerPoint builder — any deck, any content. Build with python-pptx against
`assets/DT_template.potx` (the official template, 64 layouts) so decks inherit real DT theming
instead of approximating it with shapes on a plain background.

Read **`references/build-workflow.md`** before writing any deck code — it has the template
open/fix steps, reusable helper functions, layout index table, typography scale, layout
pattern designs, and known gotchas. Nothing below duplicates it.

---

## Brand Colors

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

**Gradient rule**: signature DT gradient runs Purple → Violet → Magenta (`5E29E5` →
`8D1CDC` → `C93FDB`). Use it for decorative lines, pill shapes, and callout borders.

**Font**: **`'DT Flow'`** everywhere (`run.font.name` / `font=`). Bold via the `bold` flag,
not a separate font name.

---

## Non-Negotiables

- Content slides use layout `[61]` (Blank_graphic) — never `[6]`, which shows ghost
  "click to add content" icons.
- Every slide needs an explicit background — no layout bakes one in (see `bg()` helper).
- The `.potx` needs a content-type patch before python-pptx can open it, and its 15 example
  slides must be deleted before adding content.
- No white backgrounds, no font other than `DT Flow`, no off-palette colors.

Full code for all of the above is in `references/build-workflow.md`.

---

## QA Checklist

Before delivering any DT deck, verify:

- [ ] Cover uses `dt_cover_bg.png`, content slides use `dt_content_bg.png`
- [ ] No white backgrounds (all slides dark navy or cover image)
- [ ] Content slides use layout `[61]` (Blank_graphic) — not `[6]`
- [ ] Template's 15 example slides deleted before adding content
- [ ] Titles white, accents teal `4AC2B3`
- [ ] Font is `DT Flow` throughout — no `Trebuchet MS` or `Calibri` remnants
- [ ] No generic blue (#0070C0 etc.) — use DT palette only
- [ ] Gradient used at least once (Purple→Violet→Magenta) for a decorative element
- [ ] Text boxes sized with enough height for wrapped content — open in PowerPoint and scan for overflows
- [ ] Slide titles that can wrap to 2 lines use title box h=1.0" and accent bar y=1.6", not the 1-line defaults (h=0.7"/y=1.35")
- [ ] Punctuation hyphens have spaces on both sides (` - `) including across split Python strings

---

## Asset Manifest

| File | Description |
|------|-------------|
| `assets/DT_template.potx` | Full official PowerPoint template (64 slide layouts) |
| `assets/dt_cover_bg.png` | Cover slide background (dark with light-wave particles) |
| `assets/dt_content_bg.png` | Content slide background (deep navy, subtle corner particles) |
| `assets/dt_logo.svg` | Dynatrace logo SVG |
