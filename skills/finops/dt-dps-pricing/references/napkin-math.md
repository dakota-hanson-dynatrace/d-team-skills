# Napkin-math path: rough inputs to a napkin cost estimate, no workbook

For when you're on a call with only approximate numbers ("~2,500 servers, mostly Windows, 60%
Foundation & Discovery / 30% Infra / 10% Full-Stack, ~300-400 GB/day logs, targeting ~$500K/year")
and no time to open either `.xlsm`. This path reuses the same rate-card rows and discount mechanics
as the review workflow above, but runs forward (rough quantities → cost) instead of backward
(quoted cost → sanity check).

## 1. Map each rough input to a rate-card line and quantity

| What the customer said | Rate-card line | Quantity formula |
|---|---|---|
| N hosts in Full-Stack mode | Full-Stack Monitoring | `N × avg_RAM_GiB × 8,760` → memory-GiB-hours |
| N hosts in Infrastructure-only mode | Infrastructure Monitoring | `N × 8,760` → host-hours (RAM doesn't matter — this line bills host-hours, not memory) |
| N hosts in Foundation & Discovery mode | Foundation & Discovery | `N × 8,760` → host-hours (same reasoning — F&D isn't RAM-billed either, even though estimator-mechanics.md's Host Monitoring section only spells this out for Infra; it follows from the rate card's unit column) |
| X GB/day (or GiB/day) log ingest | Log Mgmt - Ingest & Process | `X × 365` → GiB/year |

**Defaults to apply when the customer didn't give specifics** (use these only as a last resort —
always prefer a number the customer actually states):

- **Avg RAM/host: 16 GiB.** This is the one host default this skill's own source material states
  (Quick Price Estimate's host input, pricing-engine.md) — reuse it rather than guessing.
- **Annual uptime: 100%.** Not stated as a default anywhere in the source workbooks' documentation;
  it's the napkin default here because DPS host-hours/memory-GiB-hours bill continuously for a host
  that exists all year, and "100% annual uptime" is what worked-example.md's own scenario uses
  without comment. Flag it explicitly as an assumption when you present the estimate — don't let it
  read as a sourced number.
- **GB vs GiB: treat as equivalent for napkin purposes.** The entire rate card and every formula in
  this skill are denominated in GiB; a customer's "GB/day" almost always means the same casual
  usage. Note it as a rounding simplification (1 GiB ≈ 1.07 GB) if precision matters later — don't
  silently convert, and don't treat it as a mix-up the way pitfalls.md's GiB-vs-GiB-days entry is.
- Apply the host-count split (e.g. 60/30/10) by multiplying total host count by each mode's
  percentage *before* running the quantity formulas above — each mode is priced on its own
  rate-card line, there's no blended rate.

## 2. Log Mgmt - Retain and Query: default to 35 days retention

**Default retention: 35 days** when the customer hasn't stated their own retention requirement.
Treat this as a documented napkin default, the same tier as retention factor (0.9) and enrichment
factor (2x) below — not a guess. Always prefer a number the customer actually states, and always
flag the default explicitly in the estimate's evidence trail (§4) as an assumed input, not a
customer-confirmed one, so it's easy to correct once the real figure is known.

Quantity formulas (reusing the fields and defaults estimator-mechanics.md's Log Mgt Analytics
section already documents):

- **Log Mgmt - Retain** (gibibyte-days/year): `GiB/day × retention_days × 365 × retention_factor ×
  enrichment_factor` — the steady-state stored volume (`GiB/day × retention_days`), annualized the
  same way Ingest is (`× 365`). Use `retention_days = 35` unless the customer gave their own number,
  `retention_factor = 0.9`, and `enrichment_factor = 2` (typical K8s+OneAgent enrichment; use 3 for
  heavy enrichment, 1 for log ingest with no OneAgent) unless stated otherwise. This napkin formula
  approximates the Log Mgt Analytics sheet's mechanics rather than reproducing it cell-for-cell —
  trace the source workbook if a precise figure is needed.
- **Log Mgmt - Query** (gibibytes-scanned): retention days don't drive Query usage — query volume
  depends on how much of the retained data actually gets scanned, not on how long it's kept, so
  there's no GiB/day-or-retention-days formula for it in this skill. Fall back to the one
  query-estimation formula this skill documents, Quick Price Estimate's ratio (pricing-engine.md):
  `Log query cost ≈ Log-Ingest cost × 0.86`, applied to the same Log-Ingest cost computed in §1
  (list or discounted, whichever the rest of the estimate uses consistently).

The same "don't guess" rule still applies to any other capability the customer didn't mention (K8s,
DEM, Database Monitoring, etc.) — leave them off the table entirely rather than defaulting them to
zero usage silently. Zero and "not discussed" aren't the same thing; say which one you mean.

## 3. Pick a discount tier going forward (not just checking one backward)

The review workflow's step 4 checks a *given* discount against the resulting total. Building an
estimate forward from a target commit needs the opposite direction:

1. Sum every line at **list** price first.
2. Pick a candidate discount tier from rate-card.md's table (start near the customer's stated
   target commit, e.g. ~$500K lands near Tier 5/6).
3. Apply that tier's discount to every line (`ROUNDUP(list_rate × (1 − discount), 2)`, same rounding
   order as the review workflow — round the discounted rate before multiplying by quantity).
4. Check self-consistency: does the resulting discounted total actually fall inside the tier band
   you picked? If the discounted total lands in a *different* tier than the one you chose, redo the
   math with that tier's discount instead and recheck — repeat until the tier you used and the tier
   implied by the result agree. (On the list total alone this usually resolves after one or two
   tries — there's no need to binary-search the whole 14-row table.)
5. Present that self-consistent discount explicitly as an assumption ("modeled at a Tier N / X%
   discount because the resulting total lands in that commit band") — it's exactly as much a
   guess as any other napkin input, just dressed up as a lookup.

## 4. Present the breakdown with its evidence trail

One row per capability, in the same shape the review workflow reasons about internally:

| Capability | Assumed quantity | Rate-card unit | List rate | Discounted rate | Annual cost |
|---|---|---|---|---|---|
| Full-Stack Monitoring | (hosts × RAM × 8,760) | memory-GiB-hours | $1,000/100,000 | (rate × (1−discount), rounded up) | qty/100,000 × discounted rate |
| Infrastructure Monitoring | (hosts × 8,760) | host-hours | $4,000/100,000 | … | … |
| Foundation & Discovery | (hosts × 8,760) | host-hours | $1,000/100,000 | … | … |
| Log Mgmt - Ingest & Process | (GB/day × 365) | gibibytes | $2,000/10,000 | … | … |
| Log Mgmt - Retain | (GB/day × 35 days\* × 365 × 0.9 × 2) | gibibyte-days | $700/1,000,000 | … | … |
| Log Mgmt - Query | (Log-Ingest cost × 0.86)\*\* | gibibytes-scanned | $3,500/1,000,000 | … | … |

\* 35 days is the napkin default from §2 — swap in the customer's stated retention if they gave one.
\*\* Query's figure comes from the documented cost ratio in §2, not a quantity × rate calculation —
the "Rate-card unit"/"List rate" columns are shown for reference only on this row.

Every cell in "Assumed quantity" should be traceable to either a number the customer gave or a
named default from §1 or §2 above — that's the audit trail. Add one closing line stating which
capabilities were left out and why (not discussed vs. no napkin path available), which defaults were
assumed (e.g., 35-day log retention), and which discount tier was used and why it's self-consistent
per §3.
