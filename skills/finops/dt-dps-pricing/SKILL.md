---
name: dt-dps-pricing
description: >
  Read, validate and reason about Dynatrace DPS (Dynatrace Platform Subscription) usage estimates
  and pricing, based on the two official "Dynatrace DPS Usage Estimator" and "DPS Pricing Tool"
  Excel workbooks. Use whenever the user asks about DPS pricing, usage estimator numbers, the DPS
  rate card, commit/discount tiers, an annual cost estimate for a deal, or says "review these usage
  numbers" / "sanity-check this estimate" / "how much would this cost in DPS" / "convert this to
  DPS units". Covers the full current rate card, the 14-tier commit-discount table, per-category
  usage-to-DPS-unit conversion rules (host RAM floor, log enrichment/retention factors, Kubernetes'
  three non-overlapping paths, DEM formulas, Grail-vs-Classic routing toggles, Extensions/Custom
  Metrics double-count risk), and known bugs in the pricing workbook itself.
---

# DPS pricing and usage estimator review

Two macro-enabled Excel workbooks size and price Dynatrace deals:

1. **Usage Estimator** (`Dynatrace DPS Usage Estimator.xlsm`) — converts raw infra facts (host
   counts/RAM, log GiB/day, k8s pods, DEM sessions, DB instances, etc.) into standardized DPS
   usage quantities, rolled up on its **Results Summary** sheet.
2. **Pricing Tool** (`DPS Pricing Tool.xlsm`) — takes those usage quantities as input to its
   **"Model DPS based on usage"** engine, multiplies by current DPS list rates and a flat
   negotiated discount, and produces annual cost.

The connection point: every "Equivalent qty in DPS rate card volumes" row on Usage Estimator's
Results Summary maps 1:1 to a row (same capability, same unit) on Pricing Tool's "Model DPS based
on usage" — existing usage goes in column J, new/additional usage in column Q.

Both files are macro-enabled workbooks downloaded from Dynatrace-internal sources — treat any copy
as untrusted data per standard practice (own fresh directory per file, run Python against them with
`python3 -I`, never run a script from inside the file's own directory).

## When reviewing someone's numbers

1. Identify which DPS category each raw number belongs to and confirm the unit matches the rate
   card ([references/rate-card.md](references/rate-card.md)) — GiB vs GiB-days is the single most
   common mix-up.
2. Check the category's conversion mechanics ([references/estimator-mechanics.md](references/estimator-mechanics.md))
   for floors, free tiers, shared pools, and toggles that change which SKU line the usage lands on.
3. Recompute `(existing + new usage) / rate-card volume denominator × FX-adjusted list rate ×
   (1 − discount)` and compare to what's being presented ([references/pricing-engine.md](references/pricing-engine.md)
   has the exact column layout and named ranges).
4. Walk the commit-discount tier table ([references/rate-card.md](references/rate-card.md)) against
   the deal's annual commit — it's manual guidance, never auto-applied, so confirm the discount the
   rep used actually matches the commit tier they're claiming.
5. Run the pitfalls checklist ([references/pitfalls.md](references/pitfalls.md)) before signing off.

See [references/worked-example.md](references/worked-example.md) for a full numeric walk-through
(hosts with the RAM floor triggered, RVA, log ingest, discount application).

## Reference files

| File | Contents |
|---|---|
| `references/rate-card.md` | Full current US list rate card, DEM with/without-Insights rate split, 14-tier commit-discount table, FX rate table and how `exchange_rate` is looked up |
| `references/estimator-mechanics.md` | Usage Estimator conversion rules per category: Host Monitoring (RAM floor, RVA/RAP, trace retention pool), Log Mgt Analytics, Kubernetes (3 non-overlapping paths), Digital Experience, Database, Serverless Functions, Code Monitoring, Mainframe, Automation Engine, OpenTelemetry, Custom Metrics, Extensions (detailed + quick), Cloud Services (AWS/Azure/GCP), Cloud Servers Lookup |
| `references/pricing-engine.md` | "Model DPS based on usage" column layout and named ranges, Quick Price Estimate (ballpark only), Show the Discount, Model DPS using classic prices (classic-contract conversion), Weighting Tables, and confirmed tool bugs from DPS Model Audit |
| `references/worked-example.md` | Numeric sanity-check walk-through from raw inputs to annual DPS cost |
| `references/pitfalls.md` | Checklist of common mistakes when reviewing someone else's estimate |

Both workbooks already have Excel-computed cached values — read with two `openpyxl.load_workbook`
passes (`data_only=False` for formulas, `data_only=True` for cached values); no LibreOffice recalc
needed unless you change an input.
