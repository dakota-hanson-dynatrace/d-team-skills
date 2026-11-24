# Common mistakes when reviewing someone's DPS estimate

Checklist to run before signing off on a usage estimate or a quoted annual cost.

1. **GiB vs. GiB-days.** Ingest (GiB) and Retain (GiB-days) are different rate-card rows with
   different denominators and prices — the most frequent unit mix-up in a reviewed number.
2. **Forgot the 4 GiB host RAM floor.** Any host under 4 GiB RAM must be floored to 4 GiB for
   Full-Stack, RVA, RAP, and SPM math. See worked-example.md for the size of the error this causes.
3. **Double-counted Kubernetes pod-hours.** Host full-stack (pods included free), Container
   Application Monitoring (container-hours), and Kubernetes Platform Monitoring (pod-hours) are
   three non-overlapping paths — the same pods should appear under only one.
4. **Wrong Grail vs. Classic toggle state.** `isUseMetricsPoweredByGrail` and `isUseTracesOnGrail`
   are shared across multiple sheets (Host traces, Serverless Functions, OpenTelemetry, Custom
   Metrics) — check the toggle before trusting which SKU line a number landed on, and remember
   flipping it re-routes *every* sheet that depends on it, not just the one you're looking at.
5. **DEM priced on the wrong Insights tier.** "With Insights" and "without Insights" DEM rates
   differ by about 33% — confirm which one the deal actually includes.
6. **Mainframe MSU input is monthly, not daily or annual.** `annual MSU-hours = monthly MSUs × 12`;
   a daily or already-annualized figure plugged into the monthly field over- or under-states usage
   by roughly 30x.
7. **Automation Workflow hours are existence time, not execution count.** A workflow active all
   year is 8,760 hours regardless of how often it runs.
8. **Database Monitoring query quota is per 15-minute interval**, not per day — misreading it as a
   daily quota drastically understates overage usage.
9. **Extensions (detailed sheet): a blank per-item input is not zero.** Several blocks substitute a
   different hardcoded default when a count is left blank — confirm every block was either
   deliberately filled in or deliberately skipped, not left blank by omission.
10. **Same technology estimated twice.** Extensions (detailed) and Extensions Quick Estimator cover
    the same technology list — check only one was used per technology, not both.
11. **Cloud Services (AWS/Azure/GCP) usage looks duplicative of Host Monitoring but isn't.** The
    same cloud instances legitimately generate both Host Monitoring hours (OneAgent) and Custom
    Metrics data points (native cloud polling) — additive by design, flag it only if the same metric
    source appears to be counted twice within Custom Metrics itself.
12. **Trace retention extra-days pool is shared.** Host Monitoring, Serverless Functions, and
    OpenTelemetry traces draw on one combined 10-day free allowance — sizing it per-sheet
    overstates the total free allowance available.
13. **Quick Price Estimate used to validate a detailed estimate.** It's a ratio-based ballpark tool
    for everything except Full-Stack/Infra and Log Ingest — never treat its numbers as a check on a
    category-by-category Usage Estimator output.
14. **Commit-discount tier mismatch.** `RateDiscount` is a manual input, never auto-applied — check
    the discount used against the commit-tier table (rate-card.md) for the deal's actual annual
    total, not just trust that it was looked up correctly.
15. **Non-US FX conversion mistaken for an error.** Every list rate is FX-converted and rounded up
    when `selected_country` isn't US — a non-US rate card showing different numbers from the US
    table above is expected, not a defect.
16. **Known tool bugs mistaken for input errors.** See pricing-engine.md's "DPS Model Audit" section
    — in particular, Container Application Monitoring's discount in "Model DPS using classic
    prices" pulls from the wrong named range, and that sheet's "Maximum Current Discount" headline
    excludes the Mainframe row. Don't chase these as data-entry mistakes.
