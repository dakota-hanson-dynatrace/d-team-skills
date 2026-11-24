# Worked example: sanity-checking a raw usage set against expected DPS cost

Scenario handed to you for review: "100 hosts, mixed sizes, Full-Stack with RVA; 40 GiB/day of log
ingest; US pricing; 10% negotiated discount." Walk it from raw inputs to an annual number the same
way the two workbooks would, so you can tell whether a quoted total is plausible.

## 1. Host Monitoring (Full-Stack + RVA) — apply the RAM floor first

Raw inputs:
- 80 hosts @ 16 GiB RAM, Full-Stack, 100% annual uptime
- 20 hosts @ 2 GiB RAM, Full-Stack, 100% annual uptime

**The 20 small hosts are below the 4 GiB floor** — for Full-Stack/RVA/RAP math they count as 4 GiB
each, not 2 GiB. This is the single step people most often skip.

```
memory-GiB-hours/yr = (80 × 16 + 20 × 4) × 8,760
                     = (1,280 + 80) × 8,760
                     = 1,360 × 8,760
                     = 11,913,600 GiB-hours
```

Full-Stack list cost: `11,913,600 / 100,000 × $1,000 = $119,136`
RVA list cost (same floored GiB-hours, different rate): `11,913,600 / 100,000 × $225 = $26,805.60`

Apply the 10% discount (`AL = ROUNDUP(Z × (1 − AK), 2)`, AK = 0.10):
- Full-Stack discounted rate: `ROUNDUP(1000 × 0.9, 2) = $900` → `11,913,600/100,000 × 900 = $107,222.40`
- RVA discounted rate: `ROUNDUP(225 × 0.9, 2) = $202.50` → `11,913,600/100,000 × 202.50 = $24,125.04`

If you'd forgotten the floor (used raw 2 GiB for the 20 small hosts instead of 4 GiB), you'd get
`(1,280+40)×8,760 = 11,566,800 GiB-hours` — about 3% lower than the correct figure. Small on its
own, but it compounds across Full-Stack, RVA, RAP and SPM for every undersized host in a large
fleet, so check it whenever a host list includes anything under 4 GiB.

## 2. Log Mgt Analytics — Ingest & Process

Raw input: 40 GiB/day ingest.

```
GiB/yr = 40 × 365 = 14,600 GiB
list cost = 14,600 / 10,000 × $2,000 = $2,920
discounted (10%) = 14,600 / 10,000 × $1,800 = $2,628
```

(Retain and Query usage depend on retention days, the included-query-day allowance, and the
retention/enrichment factors on the Log Mgt Analytics sheet — trace those from the source workbook
for the specific retention policy quoted rather than assuming a single formula; the factors
documented in estimator-mechanics.md tell you which inputs to expect and their defaults.)

## 3. Roll it up

```
Full-Stack (discounted):  $107,222.40
RVA (discounted):          $24,125.04
Log Ingest (discounted):    $2,628.00
                          -----------
Subtotal shown above:     $133,975.44
```

This is a partial total (Full-Stack + RVA + Log Ingest only) for illustration — a real estimate
would also include Infrastructure/F&D for any non-Full-Stack hosts, Log Retain/Query, any K8s,
DEM, Database, or other categories in play, each from its own row on "Model DPS based on usage."

## 4. Check the discount against the commit tier

`$133,975.44` × however many categories remain unlisted will determine the true annual commit. If
the rep is quoting a 10% discount, cross-check against rate-card.md's tier table: 10% corresponds
to Tier 4 ($200,000–$299,999.99 annual commit). If the full rolled-up total comes in well under
$200,000, a 10% discount is inconsistent with standard tier guidance (not impossible — reps can
negotiate off-tier — but worth a question) and if it comes in well over $300,000, 10% is leaving
tier-appropriate discount on the table.

## Method to generalize

1. Compute each category's native quantity from its raw inputs (apply any floor/free-tier/factor
   from estimator-mechanics.md).
2. Divide by the rate-card volume denominator (rate-card.md), multiply by the FX-adjusted list rate.
3. Apply `(1 − discount)`, rounding the discounted rate with `ROUNDUP(..., 2)` before multiplying
   by quantity (not the other way around — rounding order matters at scale).
4. Sum every category's discounted cost for the annual total.
5. Check the discount used against the commit-tier table for the resulting total.
