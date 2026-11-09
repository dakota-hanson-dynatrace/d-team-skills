---
name: dt-value-roadmap-v2
description: >
  Version 2 of dt-value-roadmap, built on the Observability Gap Analysis deck look, with effort and
  value wording only and no cost language. Produce a Dynatrace Value Roadmap for a customer or prospect tenant: a written report
  (Markdown + Word) with every finding, a phased implementation plan, and an effort and value
  breakdown, plus a short high-level PowerPoint in the Observability Gap Analysis look. A script collects live data via
  dtctl; the model only judges and writes. Covers configuration that exists but silently doesn't
  work, Gen2 (classic) vs Gen3 position with no-duplication upgrade paths, cloud/VMware coverage, and
  anomalies. Use when asked to do an account review, gap analysis, health check, cloud/VMware
  coverage review, Gen2/Gen3 review, or value roadmap for a Dynatrace customer or tenant. Triggers:
  "value roadmap", "gap analysis", "account review", "health check", "observability assessment",
  "cloud coverage review", "deck for customer X", "roadmap deck".
---

# Dynatrace Value Roadmap (v2)

This is v2 of `dt-value-roadmap`: Observability Gap Analysis look, effort and value wording only, merged effort and phase slide. It answers the same trigger phrases as v1, so install one or the other, or name the version when invoking it.

Three deliverables per tenant, all built from the same data so the numbers match:
1. **Report `.md`** - every finding with evidence, Gen2/Gen3 position, phased plan, effort and value breakdown, and an
   Additional Monitoring Opportunities section (every Hub extension the telemetry says would help, by type).
2. **Report `.docx`** - the same content, styled for the customer.
3. **Deck `.pptx`** - eight to ten high-level slides (including Additional Monitoring Opportunities: top 10 extension opportunities by volume, grouped by type) in the Observability Gap Analysis look (dark cover, white content
   slides, accent-bar cards, pill badges, Arial). See `references/scoring.md` for the layout.

## Language rule

Never write the word "cost" (or price, billing, DPS) in any deliverable or override. Customers should
not hesitate to adopt a capability, so every finding is described by **effort** (what it takes) and **value**
(what it unlocks). `test_generate.py` fails if either appears.

## Token budget rules

The expensive part of this skill used to be exploration. Keep it out of the run:
- **Read `digest.md` only.** Don't open `facts.json` or `raw/` unless a digest line is ambiguous,
  and then read just that one file.
- **Don't run ad hoc dtctl queries** for anything the digest already covers. If you must check one
  thing, run one query against a 1-hour window.
- **Write only `overrides.json`.** The library already writes text for standard findings.
- **Don't render slides to images** unless the generator code changed. Check the generator's printed
  warnings and the lint step instead.
- Run each tenant in a fresh session; don't carry a previous tenant's history.

## Workflow

### 1. Inputs
Customer display name, dtctl context, SE name for "Prepared by". If a prior gap analysis exists, read it
so `resolved` can list what changed (verify its claims against the digest, don't repeat them).

Check the context is authenticated and read-only (`dtctl config get-contexts`). If a login is needed,
`dtctl auth login --context "<ctx>"` resets it to readwrite-all: set it back with
`dtctl config set-context "<ctx>" --safety-level readonly`.

### 2. Collect (one command, ~3-5 minutes)
```bash
SK=~/.claude/skills/dt-value-roadmap-v2
uv run --python 3.11 python -X utf8 "$SK/collect.py" --context "<ctx>" --out "<work dir>" --readiness
```
Options: `--prod-prefixes p` (VM name prefixes that mean production, comma list), `--vdi vdi`
(Azure VDI pattern to exclude), `--ephemeral "worker|databricks|workerenv"` (hosts excluded from CPU).
The script runs everything sequentially, uses 1-hour log windows (24h log scans hit the 500 GB scan
cap), and runs `dt-upgrade-readiness` with one worker.

If the digest's "Errors and warnings" section shows a 403 on a core query (hosts, services, logs,
problems), report the missing scope and stop. A 403 on one count (e.g. Gen3 SLOs) goes into `caveats`.

### 3. Judge and write overrides.json
Read `digest.md`, then write `<work dir>/overrides.json` per `references/overrides.md`:
summary, summary_points, top_priorities, platform_matrix (from the readiness section), real
anomalies (from "Anomaly candidates"), custom_findings, caveats, and any fact corrections.

Judgment the digest leaves to you:
- Which anomaly candidates are real. Chronic 90-100% failures usually mean failure detection, not outages.
- Whether VMware or cloud gaps are production (the prefix split is a heuristic; check the names).
- Whether profiles without notifications are workflow triggers (when workflows exist, they may be).
- Which readiness items are Gen2 work vs already-migrated noise.

### 4. Generate
```bash
uv run --python 3.11 --with python-pptx --with python-docx python -X utf8 "$SK/generate_report.py" \
  --customer "<Customer>" --tenant "<env>.apps.dynatrace.com" --data facts.json overrides.json \
  --author "<SE name>" --out-base "<Customer>_Value_Roadmap_Report"
uv run --python 3.11 --with python-pptx python -X utf8 "$SK/generate_pptx.py" \
  --customer "<Customer>" --tenant "<env>.apps.dynatrace.com" --data facts.json overrides.json \
  --output "<Customer>_Value_Roadmap.pptx" --report-name "<Customer>_Value_Roadmap_Report.docx"
```
The deck builds on `dt_template_fixed.pptx` (the DT 2026 corporate master) and `assets/cover_art.png`, both shipped
in this skill, so nothing else is needed. The slide look (white content slides, accent-bar cards, pill badges, Arial)
is defined in `generate_pptx.py` and mirrors `assets/reference/Observability_Gap_Analysis_reference.pptx`; update the
generator and that reference together. These are large binaries: if `git clone` left ~130-byte Git LFS stubs, run
`git lfs pull`, or pass `--template <deck on the DT 2026 master>`. `dynatrace-pptx-skill/assets/` is only a fallback.

### 5. Review
- `grep -c '—'` and `grep -c '{'` on the Markdown must both be 0.
- Skim the finding titles (`grep '^### '`) and read only findings whose text came from the library
  default, checking it fits this tenant. Override with `label_overrides` or a correction if not.
- Copy the merged data to `$SK/benchmarks/<tenant-id>.json` for your own re-runs. It holds customer names and entity details, so `.gitignore` keeps it out of the shared repo.
- Tell the SE: output paths, caveats and inferences, readiness scope gaps, and the top priorities.
  Ask whether priorities should change before delivery.

### Technology and extension opportunities
`collect.py` calls `tech_discovery.py`, which maps what the tenant already emits (DB and messaging spans, OneAgent
technologies, log sources, metric namespaces) to Dynatrace Hub extensions and compares with what is installed.
The digest section lists every detected technology with a status. Rules:
- **Deck and report show only "Opportunity" statuses**: a Hub extension exists and is not installed (or the install
  list is unreadable). Installed, configured, disabled, already-flowing and "no Hub match" entries stay out of both.
  An installed-but-unused extension that matters (e.g. Oracle at high volume) belongs in a normal finding and the phased
  plan: raise it as a `custom_findings` item.
- The deck slide is skipped when there are 3 or fewer opportunities (`SLIDE_MIN_EXCLUSIVE` in `tech_discovery.py`); the report section is always kept.
- A 403 on `extensions:definitions:read` marks entries "install state unreadable": add a caveat, do not treat as confirmed.
- Network and security appliances (F5, Palo Alto, Cisco) only appear when logs, SNMP or metrics from them exist.
  If none appear, say so in `caveats` rather than implying none are present.
- Judge the digest list: drop entries that are clearly noise (e.g. a generic JMX extension on every Tomcat) via `tech_exclude`
  in overrides.json.
- To extend detection, add a rule to `RULES` in `tech_discovery.py` (the digest lists unmatched OneAgent technologies and log sources).

## References (read only when needed)
- `references/overrides.md` - overrides.json schema, platform_matrix rows, voice rules. **Read every run.**
- `references/scoring.md` - triggers, tiers, phasing, deliverable structure. When tuning priorities.
- `references/queries-coverage.md`, `references/queries-config.md` - the DQL behind collect.py.
  When debugging a wrong field or extending the collector.
- `test_generate.py` - run after any change to the opportunity library.

## Prerequisites
- dtctl authenticated against the target context (dtctl 0.28+; `--limit`/`--jq` not required).
- Python 3.11 via `uv` (no install needed) or a local Python with `python-pptx` and `python-docx`.
- `dt-upgrade-readiness` skill installed (for `--readiness`).
