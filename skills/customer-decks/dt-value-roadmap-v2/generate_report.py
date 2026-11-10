#!/usr/bin/env python3
"""
dt-value-roadmap-v2: written report (Markdown + Word) companion to the deck.
Usage: python generate_report.py --customer NAME --tenant URL --data data.json --author "Name" --out-base PATH
Writes PATH.md and PATH.docx from the same findings the deck uses (generate_pptx.plan).
"""
import argparse, datetime, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tech_discovery
from generate_pptx import plan, load_data, PHASES, EFFORT_TIERS, EFFORT_SUB, _estate_stats

GEN_TEXT = {'Gen3': 'Gen3 (improve)', 'Gen2': 'Gen2 (classic feature)', 'Upgrade': 'Gen2 to Gen3 upgrade',
            'Both': 'Gen2 + Gen3 (consolidate)'}

# ── CONTENT ───────────────────────────────────────────────────────────────────
# Built once as a list of blocks, rendered to both Markdown and Word so the two
# documents can't drift apart.
def _paras(text):
    """Split a finding body into ('p', ...) and ('bullets', [...]) blocks."""
    blocks, bullets = [], []
    for line in (text or '').split('\n'):
        s = line.strip()
        if s.startswith('▸'):
            bullets.append(s.lstrip('▸ ').strip())
            continue
        if bullets:
            blocks.append(('bullets', bullets)); bullets = []
        if s:
            blocks.append(('p', s))
    if bullets:
        blocks.append(('bullets', bullets))
    return blocks

def content(data, customer, tenant, author, today):
    f   = plan(data)
    est = _estate_stats(data)
    for i, x in enumerate(f, 1):
        x['n'] = i
    by_phase = {p: [x for x in f if x['phase'] == p] for p in PHASES}
    by_effort = {e: [x for x in f if x['effort_tier'] == e] for e in EFFORT_TIERS}
    matrix   = data.get('platform_matrix', [])

    b = [('title', f'{customer} - Dynatrace Value Roadmap'),
         ('meta', f'Prepared by: {author}, Dynatrace Solutions Engineering'),
         ('meta', f'Environment: {tenant}  |  {today}')]

    b += [('h1', 'Summary')]
    b += [('p', data.get('summary') or (
        f"This review covers what {customer} has in place on Dynatrace today and where the next gains are. "
        f"We found {len(f)} items. {len(by_effort['Low Effort'])} take an hour or less, "
        f"and {len(by_phase[1])} can be completed in the first two weeks."))]
    if data.get('summary_points'):
        b += [('bullets', data['summary_points'])]

    b += [('h1', 'Environment Snapshot'),
          ('table', ['Area', 'Today', 'Notes'], [
              ['Hosts (OneAgent)', str(est['oneagent_hosts']),
               f"{data.get('hosts_fullstack', 0)} FullStack, {data.get('hosts_infra', 0)} Infrastructure-only"],
              ['Cloud hosts without OneAgent', str(est['cloud_only']),
               _short(data.get('cloud_hosts_without_oneagent_names'))],
              ['Services', f"{data.get('services', 0):,}", f"{data.get('db_services', 0)} database services"],
              ['Service requests / day', str(data.get('traces_per_day', '?')), ''],
              ['Problems (7 days)', f"{data.get('problems_per_week', 0):,}", f"{data.get('problems_per_day', 0):,} per day"],
              ['Log records (24h)', f"{data.get('log_records_24h', 0):,}",
               f"{data.get('log_unattributed_pct', 0)}% not linked to a host or service"],
              ['Alerting profiles / notifications', f"{data.get('alerting_profiles', 0)} / {data.get('notifications_count', 0)}", ''],
              ['Workflows / SLOs (Gen3)', f"{data.get('workflow_count', 0)} / {data.get('slo_count', 0)}",
               f"{data['classic_slo_count']} classic SLO{'s' if data['classic_slo_count'] != 1 else ''}" if data.get('classic_slo_count') else ''],
              ['Synthetic monitors', str(data.get('synthetic_monitors', 0)), ''],
          ] + [list(r) for r in data.get('snapshot_extra', [])])]

    if matrix:
        b += [('h1', 'Platform Position: Gen2 and Gen3'),
              ('p', 'Each capability area below is marked by where it runs today. Areas already on Gen3 carry '
                    'improvement items in the findings. Areas still on classic (Gen2) features carry an upgrade '
                    'path, and that path only appears where it would not leave two copies of the same thing '
                    'running.'),
              ('table', ['Area', 'Gen2 (classic) today', 'Gen3 today', 'Status', 'Next step'],
               [[r['area'], r.get('gen2_today', '-'), r.get('gen3_today', '-'), r['status'],
                 r.get('matrix_next', r.get('next_step', ''))] for r in matrix])]

    if data.get('resolved'):
        b += [('h1', 'Resolved Since the Last Review'), ('bullets', data['resolved'])]

    b += [('h1', 'Findings')]
    for x in f:
        b += [('h2', f"{x['n']}. {x['title']}"),
              ('table', ['Effort', 'Effort level', 'Platform', 'Phase'],
               [[x['effort'], x['effort_tier'], GEN_TEXT.get(x['gen'], x['gen']),
                 PHASES[x['phase']][0].split(' - ')[0]]]),
              ('h3', 'What we found'), ('p', _sentence(x['headline']))]
        b += _paras(x['body'])
        b += [('h3', 'Recommendation'), ('p', x['fix'])]
        if x['value']:
            b += [('p_label', 'Value: ', x['value'])]
        if x['dup_guard']:
            b += [('p_label', 'Duplication check: ', x['dup_guard'])]

    b += [('h1', 'Phased Implementation Plan'),
          ('p', 'Items are phased by lift and complexity. Phase 1 is configuration a single admin can finish in '
                'under an hour per item. Phase 2 needs a few hours or coordination with an application team. '
                'Phase 3 covers multi-day work that needs planning with the owning teams.')]
    for p, (name, when, cx) in PHASES.items():
        b += [('h2', f'{name} ({when}, complexity: {cx})')]
        if by_phase[p]:
            b += [('table', ['#', 'Action', 'Effort', 'Value'],
                   [[str(x['n']), x['action'], x['effort'], x['value']] for x in by_phase[p]])]
        else:
            b += [('p', 'No items in this phase.')]

    b += [('h1', 'Effort and Value Breakdown'),
          ('p', 'The same findings grouped by how much work each one takes, with the value it delivers.')]
    for e in EFFORT_TIERS:
        b += [('h2', f'{e} ({len(by_effort[e])})'), ('p', f'Typically {EFFORT_SUB[e]}.')]
        if by_effort[e]:
            b += [('table', ['#', 'Action', 'Effort', 'Value'],
                   [[str(x['n']), x['action'], x['effort'], x['value']] for x in by_effort[e]])]

    ext_opp = tech_discovery.extension_opportunities(data)
    if ext_opp:
        b += [('h1', 'Additional Monitoring Opportunities'),
              ('p', 'These technologies already send telemetry to Dynatrace through OneAgent, traces, logs or metrics. '
                    'Each has a Dynatrace Hub extension that adds depth OneAgent alone does not provide, such as '
                    'database internals, queue depth, device health and configuration. Extensions that are already '
                    'installed are not listed here. Entries are ordered by telemetry volume within each type.')]
        if any('unreadable' in t.get('status', '') for t in ext_opp):
            b += [('p', 'Note: the installed extension list could not be read in this review (missing the '
                        'extensions:definitions:read scope), so some entries may already be covered. Confirm before planning.')]
        cats = []
        for t in ext_opp:
            if t['category'] not in cats:
                cats.append(t['category'])
        for cat in cats:
            rows = [[t['technology'], t['volume_label'], '; '.join(t['evidence'][:2]), '; '.join(h['name'] for h in t['hub_candidates'])]
                    for t in ext_opp if t['category'] == cat]
            b += [('h2', cat), ('table', ['Technology', 'Volume', 'What we see', 'Hub extension'], rows)]

    if data.get('caveats'):
        b += [('h1', 'Scope and Data Notes'), ('bullets', data['caveats'])]
    b += [('footer', f'Dynatrace Solutions Engineering  |  Confidential - prepared for {customer}')]
    return b

def _sentence(s):
    s = (s or '').strip()
    return s if not s or s[-1] in '.!?' else s + '.'

def _short(items, n=4):
    items = list(items or [])
    return ', '.join(items[:n]) + (f' and {len(items) - n} more' if len(items) > n else '')

# ── MARKDOWN ──────────────────────────────────────────────────────────────────
def _md_cell(s):
    return str(s).replace('|', '\\|').replace('\n', ' ')

def to_markdown(blocks):
    out = []
    for blk in blocks:
        kind = blk[0]
        if kind == 'title':   out += [f'# {blk[1]}', '']
        elif kind == 'meta':  out += [f'{blk[1]}  ']
        elif kind == 'h1':    out += ['', f'## {blk[1]}', '']
        elif kind == 'h2':    out += ['', f'### {blk[1]}', '']
        elif kind == 'h3':    out += [f'**{blk[1]}**', '']
        elif kind == 'p':     out += [blk[1], '']
        elif kind == 'p_label': out += [f'**{blk[1].strip()}** {blk[2]}', '']
        elif kind == 'bullets': out += [f'- {i}' for i in blk[1]] + ['']
        elif kind == 'table':
            hdr, rows = blk[1], blk[2]
            out += ['| ' + ' | '.join(hdr) + ' |', '|' + '---|' * len(hdr)]
            out += ['| ' + ' | '.join(_md_cell(c) for c in r) + ' |' for r in rows] + ['']
        elif kind == 'footer': out += ['', '---', '', f'*{blk[1]}*']
    return '\n'.join(out) + '\n'

# ── WORD ──────────────────────────────────────────────────────────────────────
def to_docx(blocks, path):
    from docx import Document
    from docx.shared import Pt, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    NAVY, TEAL, GREY = RGBColor(0x1A, 0x24, 0x40), RGBColor(0x00, 0x8C, 0x95), RGBColor(0x6F, 0x74, 0x7F)

    def shade(cell, hex_fill):
        tcPr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement('w:shd')
        shd.set(qn('w:val'), 'clear'); shd.set(qn('w:color'), 'auto'); shd.set(qn('w:fill'), hex_fill)
        tcPr.append(shd)

    def rule(par):
        pPr = par._p.get_or_add_pPr()
        bdr = OxmlElement('w:pBdr'); bottom = OxmlElement('w:bottom')
        for k, v in (('val', 'single'), ('sz', '8'), ('space', '1'), ('color', '00A1B2')):
            bottom.set(qn(f'w:{k}'), v)
        bdr.append(bottom); pPr.append(bdr)

    doc = Document()
    for sec in doc.sections:
        sec.left_margin = sec.right_margin = Inches(0.9)
        sec.top_margin = sec.bottom_margin = Inches(0.8)
    normal = doc.styles['Normal']
    normal.font.name = 'Calibri'; normal.font.size = Pt(10.5)
    normal.element.rPr.rFonts.set(qn('w:eastAsia'), 'Calibri')
    for name, size, color in (('Heading 1', 15, NAVY), ('Heading 2', 12.5, NAVY), ('Heading 3', 11, TEAL)):
        st = doc.styles[name]
        st.font.name = 'Calibri'; st.font.size = Pt(size); st.font.bold = True; st.font.color.rgb = color

    for blk in blocks:
        kind = blk[0]
        if kind == 'title':
            p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(blk[1]); r.bold = True; r.font.size = Pt(22); r.font.color.rgb = NAVY
            rule(p)
        elif kind == 'meta':
            p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(0)
            r = p.add_run(blk[1]); r.font.size = Pt(9.5); r.font.color.rgb = GREY
        elif kind == 'h1':
            h = doc.add_heading(blk[1], level=1); rule(h)
        elif kind == 'h2':
            doc.add_heading(blk[1], level=2)
        elif kind == 'h3':
            doc.add_heading(blk[1], level=3)
        elif kind == 'p':
            doc.add_paragraph(blk[1])
        elif kind == 'p_label':
            p = doc.add_paragraph(); r = p.add_run(blk[1]); r.bold = True; p.add_run(blk[2])
        elif kind == 'bullets':
            for i in blk[1]:
                doc.add_paragraph(i, style='List Bullet')
        elif kind == 'table':
            hdr, rows = blk[1], blk[2]
            t = doc.add_table(rows=1, cols=len(hdr)); t.style = 'Table Grid'
            for c, h in zip(t.rows[0].cells, hdr):
                c.text = ''; r = c.paragraphs[0].add_run(h); r.bold = True
                r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF); r.font.size = Pt(9.5)
                shade(c, '1A2440')
            for n, row in enumerate(rows):
                cells = t.add_row().cells
                for c, v in zip(cells, row):
                    c.text = ''; r = c.paragraphs[0].add_run(str(v)); r.font.size = Pt(9.5)
                    if n % 2:
                        shade(c, 'F3F5F7')
            doc.add_paragraph()
        elif kind == 'footer':
            for sec in doc.sections:
                fp = sec.footer.paragraphs[0]; fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
                r = fp.add_run(blk[1]); r.italic = True; r.font.size = Pt(8.5); r.font.color.rgb = GREY
    doc.save(path)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Dynatrace Value Roadmap written report')
    ap.add_argument('--customer', required=True)
    ap.add_argument('--tenant',   required=True)
    ap.add_argument('--data',     required=True, nargs='+', help='facts.json then overrides.json (later files win)')
    ap.add_argument('--author',   required=True, help='SE name for the "Prepared by" line')
    ap.add_argument('--out-base', required=True, help='Output path without extension')
    args = ap.parse_args()
    data = load_data(args.data)
    data['customer'] = args.customer
    today = datetime.date.today().strftime('%B %d, %Y')
    blocks = content(data, args.customer, args.tenant, args.author, today)
    with open(args.out_base + '.md', 'w', encoding='utf-8') as fh:
        fh.write(to_markdown(blocks))
    to_docx(blocks, args.out_base + '.docx')
    print(f'Saved: {args.out_base}.md and {args.out_base}.docx')
