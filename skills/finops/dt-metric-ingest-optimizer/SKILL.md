---
name: dt-metric-ingest-optimizer
description: >
  Analyze everything a Dynatrace tenant is billed for under Metrics - Ingest & Process, plus the Metric - Query load,
  and turn it into findings, remediation steps and a phased plan. Produces a customer-facing Word report and Markdown file,
  a findings notebook in the tenant, and a dashboard that compares any selected window (24 hours, 1 hour, any length) with
  the same-length window 7 days earlier. Breaks billed volume down by data type, source and monitoring source, finds metrics
  nobody reads, rarely used, API-only or detector-only metrics, histogram bucket and OpenTelemetry sampling-interval
  opportunities, duplicate signals, cost-center attribution gaps, and anomaly detectors that are copies of one template.
  Can run against one tenant or several (one at a time). Use whenever the user mentions metric ingest, metric volume,
  metric cost or DPS for metrics, unused or never-queried metrics, reducing or optimizing metrics, OpenTelemetry or
  Prometheus metric volume, _bucket or histogram metrics, collection or sampling interval, metric standardization,
  cardinality, anomaly detector consolidation, or a metric ingest review for a customer, even if they do not name the skill.
---

# Metric ingest optimizer

Per tenant, four deliverables built from the same data so the numbers match:
1. **Report** `.docx` and `.md`: findings, how to manage the metrics coming in, remediation steps, a phased plan.
2. **Findings notebook** in the tenant: live queries on the last 24 hours against the same 24 hours a week earlier, next to the findings.
3. **Comparison dashboard** in the tenant: follows the timeframe picker and compares the selected window with a window of the
   same length shifted back 7 days (24h against 24h, 1h against 1h). It is a dashboard because notebooks cannot read the
   picker variables.
4. **Digest and facts** for the next run or a cross-tenant rollup.

Scripts count. You judge. Do not recompute numbers by hand and do not run ad hoc queries for anything the digest covers.

## Rules that save a debugging session

- **One dtctl call at a time.** Concurrent calls refreshed the OAuth token together and wiped it. Never run two tenants or two scripts in parallel.
- **Read-only unless the user agrees to a write.** Contexts are usually `readonly`. Creating the notebook and dashboard needs a temporary
  raise to `readwrite-mine`. Ask first, explain what will be created, and let `build_assets.py --apply --yes-write` raise and then
  restore the level. If a login happens (`dtctl auth login`), the context resets to `readwrite-all`: set it back to the level it had.
- **Pass DQL through files.** The scripts do. If you test by hand, use `dtctl query -f file.dql` from Bash, not PowerShell inline.
- **Run Python with `uv`:** `uv run --with pyyaml python -X utf8 ...`, and `--with python-docx` for the report.
- **Notebook and dashboard content must carry the UI's schema version.** Content saved without it is treated as a legacy document and every
  tile opens as Raw response, whatever `visualization` says. `build_assets.py` writes the version the tenant itself uses (`"7"` for
  notebooks, a string; about 21 for dashboards, an integer) and reads it from the tenant's exported documents when it can. Never publish
  generated content without it, and never embed synthetic cached results: that produced tiles showing `[object Object]`.
- **No em dashes** in anything written for the user or the customer. Use a plain hyphen.
- **Customer-facing language.** The report is written to hand to the customer. State what was found, why it matters and what to do.
  Describe configuration, never blame a person.
- **Dollars are indicative.** The default rate is 0.15 per million datapoints, an assumed list rate. Ask for the contracted rate and pass it with `--rate`.
- **Run each tenant in a fresh work folder**, and do not carry one tenant's numbers into another's text.

## Workflow

### 1. Choose tenants and inputs
Run `dtctl config get-contexts -o json --plain` and show the user the contexts (name, environment, safety level). Ask which tenants to
run. For each one capture: customer display name, the contracted rate if known, and the SE name for "Prepared by". Verify each
context is authenticated (`dtctl auth whoami --context "<ctx>" --plain`). If the user wants several tenants, run steps 2 to 6 for the
first tenant completely, then the next, never interleaved. Use a work folder per tenant, for example `<project>/mio/<customer>/`.

If a tenant has never been onboarded, use the `dtctl-onboard-customer` skill first.

### 2. Collect (about 1 to 2 minutes without config, 5 to 15 with it)
```bash
SK=~/.claude/skills/finops/dt-metric-ingest-optimizer/scripts
uv run --with pyyaml python -X utf8 "$SK/collect.py" --context "<ctx>" --out "<work dir>"
```
Options: `--skip-config` (skips the dashboards, notebooks, workflows, SLO and settings export, the slowest step; usage evidence is
then query history only), `--usage-days 30` (if the 90 day query-log scan times out), `--otel-top 15` (metrics to probe for series and
interval), `--probe-sources opentelemetry,` plus any other `grail.metric.source` to probe, `--skip-probe`.

It runs sequentially and writes `raw/*.json`, `corpus/*`, `meta.json`. Read the end of the output: every query that failed is
listed as an ERROR. A 403 on billing usage events means the token lacks the scope to read `dt.system.events`. Report it and stop.
A 403 on a single settings schema goes into the caveats. Run the collector again to resume the config export (existing files are kept).

### 3. Analyze
```bash
uv run --with pyyaml python -X utf8 "$SK/analyze.py" --dir "<work dir>"
```
Writes `facts.json` and `digest.md`. No tenant calls.

### 4. Judge and write overrides.json
Read `digest.md` only. Then write `<work dir>/overrides.json` following `references/overrides.md`: a summary, priorities, notes per
opportunity, any extra finding, and caveats. Use `references/analysis-guide.md` for how to read the usage classes and what to
check, `references/otel-guidance.md` for the OpenTelemetry section and `references/remediation-catalog.md` for concrete steps.
Check every number you write against the digest.

What the digest leaves to you:
- Whether API-only metrics are real use (who is the client?).
- Whether rarely used metrics are exploration or a small live dashboard (last-queried date).
- Whether detector-only metrics belong to alerts that matter.
- Whether the interval estimates are credible (the digest shows raw and snapped values).
- Whether Metric - Query is billed as its own type here. If the digest says it is not, say so plainly and frame the query findings as load
  and efficiency: detector runs, API pollers, heavy dashboards.

### 5. Build the tenant assets
```bash
uv run --with pyyaml python -X utf8 "$SK/build_assets.py" --dir "<work dir>" --customer "<Customer>" --test-queries
```
This writes `assets/findings_notebook.yaml` and `assets/compare_dashboard.yaml` and runs every query once (the dashboard queries at
both a 24 hour and a 1 hour window). Fix any ERROR and any `SHAPE PROBLEM` before going on. Every tile has an explicit visualization
chosen from the shape of its result (charts for comparisons, shares and time series, tables for detail), and the test checks each
result against its choice. Read `references/visualization-guide.md` before adding or changing a tile. A tile left on a default or
shown as raw records is a defect. Then ask the user for permission to write, and apply:
```bash
uv run --with pyyaml python -X utf8 "$SK/build_assets.py" --dir "<work dir>" --customer "<Customer>" --apply --yes-write
```
It raises the safety level, creates both, restores the original level in a `finally`, and writes `assets/created.json` with the URLs.
Confirm in the output that the level is back to what it was. Then export each item (`dtctl get notebook <id> -o yaml --plain`, decode the
byte-array `content`) and confirm `content.version` is present and every tile's `visualization` matches the registry. Tell the user the two links and say that you have
not seen them render. Both items are private to the person who created them, so say so. Ask the user to open them and name any tile
that looks wrong. If they change a visualization, update `NB_TILES` in `build_assets.py` so the next run starts from their choice.

Dashboard behavior to tell the user: the default timeframe is yesterday. Billed tiles use billing records matched on the usage period,
which arrive a few hours late, so avoid ending the window in the last 6 hours. The live "ingested" tiles have no such lag.

### 6. Generate the report
```bash
uv run --with python-docx python -X utf8 "$SK/generate_report.py" --facts "<work dir>/facts.json" --overrides "<work dir>/overrides.json" \
  --customer "<Customer>" --author "<SE name>" --rate <rate> --created "<work dir>/assets/created.json" --out-base "<work dir>/<Customer>_Metric_Ingest_Review"
```
Produces the `.md` and `.docx`. Open the markdown, read the executive summary and the first findings, and check that nothing
contradicts the digest. The report ends with a phased plan (foundations, quick wins, reduce at the source, standardize and
consolidate, govern) built from the opportunities that exist for the tenant.

### 7. Several tenants
After each tenant is done:
```bash
uv run python -X utf8 "$SK/rollup.py" --out "<project>/mio/rollup.md" "<dir1>/facts.json" "<dir2>/facts.json"
```
Gives one comparison table. Offer it to the user. Do not merge tenants into one report.

### 8. Hand off
Tell the user: the report paths, the two tenant links (if created), the headline numbers (billed volume and week-over-week change,
unused and rarely used volume, the biggest source), and what you could not verify (errors from collection, the interval estimate
being an estimate, API-only metrics needing an owner check). Offer the next step, usually a review with the metric owners.

## What each opportunity means

| Id | Opportunity | Evidence | Typical effort |
|---|---|---|---|
| O1 | Metrics still arriving that nothing reads | No query, detector, config or wildcard use | Low |
| O2 | Read only by API clients | Queried only through the API | Medium |
| O2b | Rarely used | 10 or fewer interactive queries in the window | Low |
| O3 | Read only by detectors | No person or dashboard reads it | Medium |
| O4 | Histogram bucket series that are used | `_bucket` keys with use | Medium |
| O5 | Longer reporting interval | Measured interval on high-volume metrics | Low |
| O6 | High-cardinality labels | Label with 1,000+ distinct values | Medium |
| O7 | Duplicate signals | Same signal under dotted and underscore names or two sources | Medium |
| O8 | No cost center | Share of billed datapoints with no attribution | Low |
| O9 | Detector copies | Detectors identical except per-team values | Medium |

## Files

- `scripts/collect.py` collects raw data. `scripts/analyze.py` classifies and writes facts and digest.
- `scripts/build_assets.py` builds, tests and applies the notebook and dashboard.
- `scripts/generate_report.py` writes the `.md` and `.docx`. `scripts/rollup.py` compares tenants. `scripts/dtq.py` is the shared dtctl helper.
- `references/analysis-guide.md`, `otel-guidance.md`, `remediation-catalog.md`, `overrides.md`, `visualization-guide.md`.
