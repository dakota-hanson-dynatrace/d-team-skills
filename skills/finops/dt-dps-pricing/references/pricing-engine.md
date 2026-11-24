# Pricing Tool: engine layout, supporting sheets, and known tool bugs

All sheets below are in `DPS Pricing Tool.xlsm`.

## "Model DPS based on usage" — the core engine

Columns (one row per capability):

| Col | Meaning |
|---|---|
| H / I | Category / capability name |
| K | Unit of measure |
| J | Existing annual usage (input) |
| Q | New/additional annual usage (input) |
| W | Rate-card volume denominator |
| U | `(J+Q)/W` = equivalent qty in rate-card volumes |
| Y | USD list price per that volume (hardcoded input) |
| Z | `ROUNDUP(Y * exchange_rate, 0)` — FX-adjusted list price |
| AK | `=RateDiscount` — flat discount %, identical on every row |
| AL | `ROUNDUP(Z * (1 - AK), 2)` — discounted rate |
| AO | Annual cost of all usage |
| AP / AQ | Cost split: new usage vs. existing usage |

Named ranges: `deployment` (B5, SaaS/Managed — several rows zero out when Managed, confirmed for
Kubernetes/Container/Code/Database/Telemetry/DEM/Automation/Egress/Classic categories),
`RateDiscount` (AK5, manual input — see rate-card.md for the tier table it's informed by, never
auto-looked-up here), `usage_commit` (AO5), `exchange_rate` (`'Weighting Tables'!O2`),
`selected_country` (`Start!G2`).

Rows 47–48 ("Additional observations") are optional inputs — "% of full-stack usage that is K8S"
and "% of host RAM used by containers in K8S" — for untangling how much Full-Stack memory-GiB-hours
is really Kubernetes workload, useful when sanity-checking against the Kubernetes Monitoring sheet's
own pod-hour/container-hour lines.

## Quick Price Estimate

A simplified 2-input ballpark tool, explicitly documented as estimating "based on average cost
ratios derived from the usage of real customers" — **not** a usage-derived model. Inputs: host
count, GB/day log ingest, flat discount %, avg RAM/host (default 16 GiB), % of hosts needing
full-stack (rest assumed infra-only).

Only Full-Stack and Infrastructure Monitoring are computed directly (hosts × RAM × 8,760 hours,
live rates pulled from "Model DPS based on usage"). Every other category is a **fixed empirical
ratio** off that Full-Stack or Log-Ingest cost, not an independent estimate:

- App Sec (RVA+RAP) = Full-Stack cost / 9.3
- RUM/DEM total = Full-Stack cost / 5.35
- Metrics ingest = Full-Stack cost / 11
- Log retain = Log-Ingest cost / 3.7
- Log query = Log-Ingest cost × 0.86
- Everything else (Mainframe, K8s, DB Mon, trace/event telemetry, Automation, Egress, AI Units,
  Classic SKUs) = hardcoded 0.

**Never use Quick Price Estimate to validate a detailed Usage Estimator figure** — its App
Sec/DEM/Metrics numbers are ratios of Full-Stack/Log spend, not usage-derived; compare a detailed
estimate against "Model DPS based on usage" instead.

Guard rails (warn, don't block): above 5,000 hosts or 5,000 GB/day log; above 20% discount ("Deal
desk is required"). "Expert services to get started" = `MAX(QuickStart_Cost, MIN($300k × FX, 25%
of total))`, where `QuickStart_Cost = $16,500 × FX`. Carries its own copy of the 14-tier
commit-discount table — confirmed identical to the one in rate-card.md.

## Show the Discount

A reverse calculator: enter a customer's quoted/current per-unit rate for each of ~39 capability
rows (mirrored from "Model DPS based on usage"), and it computes `discount = 1 −
entered_rate/list_rate`, plus an uplift-% preview. No independent discount-tier logic — a pure
algebraic inverse of list price. This is the sheet that revealed the DEM with/without-Insights
split documented in rate-card.md (toggle `Discont_helper_DEM_Insights`, D50).

## Model DPS using classic prices

Converts an existing **classic (SKU-based)** contract into DPS terms — a different workflow from
the usage-first engine above, in four steps:

1. **Current classic contract** — SE enters current unit price, quantity, utilization for Host
   Units, Host Unit Hours, Application Security Units, DEM Units (and w/ Insights), Davis Data
   Units, Cloud Automation Units, Mainframe MSUs. Realized unit cost = Total Cost /
   (Qty × Utilization).
2. **Implied discount** — compares each classic price to a hardcoded FX-adjusted "Adjusted Basis"
   reference price (e.g. Host Units $1,401.60, DEM Units $9,000 / w-Insights $12,000, Davis Data
   Units $2,000, Mainframe $765) to back into an implied "Current Contract Discount" per line,
   flags "High Discount?" above a cap (20%), and rolls up max/average/weighted-average implied
   discount.
3. **New DPS terms** — SE picks an annual commit; the commit-tier discount auto-looks-up from the
   **same 14-tier table** (confirmed identical); adds a negotiated discount, deployment type
   (SaaS/Managed), a "Use DEM with Insights?" toggle, and ESS inclusion %. `act_level_discount` =
   commit-tier discount + negotiated discount, the default discount most Step-4 rows use.
4. **Resulting DPS rate card** — re-derived from the live "Model DPS based on usage" list prices.
   Most rows apply `act_level_discount`; five get a per-category override instead:
   `classic_discount_host_monitoring` (Full-Stack/Infra), `classic_discount_app_sec` (RVA/RAP), and
   `classic_discount_DDU` (the four legacy/Classic rows) — **plus Container Application Monitoring,
   which incorrectly pulls from `classic_discount_mainframe` instead of its own override: see Known
   Tool Bugs below.** DEM rows use dedicated per-capability × Insights-on/off named ranges. Managed
   deployment zeroes out the same set of categories noted above.

## Weighting Tables

See rate-card.md for the FX table. The rest of this sheet (legacy Host Unit / DEM Unit / Davis Data
Unit / Application Security Unit weighting tables) is classic-SKU conversion scaffolding used only
by "Model DPS using classic prices," not by the usage-based engine.

## DPS Model Audit

A static, dated findings report (dated 17 Nov 2026 in the copy reviewed) auditing both pricing
models' internal formula wiring — **tool defects, not commercial-policy issues.** Confirmed findings
most relevant to reviewing someone's numbers (full list has 11 items; these are the ones worth
flagging as "known tool quirk, not your input error"):

1. **High** — In "Model DPS using classic prices," Container Application Monitoring's discount cell
   wrongly reads `MAX(classic_discount_mainframe, act_level_discount)` instead of its own override;
   Mainframe's own row doesn't use the Mainframe discount at all.
2. **High** — A pie-chart formula in the usage model references the wrong cell (`A11` instead of
   `AO11`), so Container Application Monitoring cost silently falls into "Other" instead of "K8S
   Monitoring" in that rollup chart.
3. **Medium** — Container Application Monitoring is likewise omitted from the application
   observability breakdown totals.
8. **High** — Trace total includes converted classic/legacy span usage, but the new/existing cost
   split only uses the plain new/existing usage cells — so total cost can appear to exceed the sum
   of its new+existing split when legacy trace-conversion inputs are used.
11. **Medium** — The "Maximum Current Discount" headline uses `MAX()` over the implied-discount
    column but excludes the Mainframe row, which can understate the true maximum classic discount.

If a number looks inconsistent in exactly one of these specific ways, it's very likely the workbook,
not the rep's input — don't spend review time chasing it as a data-entry error.
