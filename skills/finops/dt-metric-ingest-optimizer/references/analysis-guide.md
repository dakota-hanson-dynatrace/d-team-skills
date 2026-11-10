# Analysis guide: reading the digest and judging what it says

The scripts do the counting. Your job is the judgment the numbers leave open. Read `digest.md` first. Open `facts.json`
only for a line that is ambiguous, and then only the key you need.

## What the numbers mean

**Billed versus ingested.** Billed volume comes from billing usage records (`Metrics - Ingest & Process`). Per-metric volume
comes from `dt.sfm.metrics.ingest.datapoints`. Outside `dt.*` platform metrics the two agree within a few percent. Platform
metrics (`dt.*`) are not billed under metric ingest, so every opportunity excludes them. If the two differ by more than about
10 percent, say so in the caveats.

**Billing records are late.** They describe usage that ended a few hours earlier, so complete days are used for billed
comparisons. The ingest measure is also late for some keys (hours), which is why the interval probe uses a window that ended
3 hours ago.

**Usage classes** (each key gets exactly one, strongest evidence first):
1. Used interactively: queried from a dashboard, notebook or Dynatrace app more than 10 times in the window.
2. Rarely used: 10 or fewer interactive queries and no detector or config reference. Usually exploration.
3. Used by API clients only: only queried through the API (Grafana, scripts, pollers).
4. Used by detectors only: only anomaly detectors or classic metric events read it.
5. Referenced in saved config only: named in a dashboard, notebook, workflow or SLO that has not run in the window.
6. Possible wildcard use: matches a wildcard pattern found in queries or config.
7. No usage found: none of the above. These are the drop candidates when they still arrive.

**Detector runs are not use.** Anomaly detectors run once a minute, so a metric read by one shows tens of millions of
queries. Query pool `ALERTING` is the detector class. The skill separates it, otherwise every detector metric looks busy.

**Bulk enumeration queries are ignored.** Some Dynatrace apps issue one query naming hundreds of metric keys when a page
opens. Queries with more than 60 distinct tokens are excluded from usage so those keys are not counted as used.

## Judgment to apply

- **API-only metrics**: ask who the client is (`query_api_users`). A Grafana board someone looks at weekly is real use. A script
  polling every minute that nobody reads is not.
- **Rarely used**: look at the last-queried date. A key last queried 80 days ago by one person is a drop candidate. A key
  queried 4 times last week is a small dashboard and should stay.
- **Detector-only**: check whether the detector ever fired. If it did, the metric is doing its job.
- **Bucket series**: do not recommend dropping a `_bucket` family that dashboards use for percentiles. Recommend native
  histograms or fewer buckets and labels instead. Dropping `_bucket` never affects the `_sum` and `_count` series.
- **Interval estimates**: the probe is an estimate. It is accurate to roughly 10 to 15 percent and is snapped to a standard
  interval. If a probe shows a value outside 5 to 3600 seconds it is discarded. Confirm in the collector or SDK before
  promising a saving.
- **Savings are volume first.** Dollar figures use the rate you pass in (default 0.15 per million datapoints, an assumed
  list rate). Always state that it is indicative and ask for the contracted rate.
- **Never fired is not useless.** Availability alerts that never fire may be healthy. Recommend review with the owner,
  not deletion.

## Limits to state in the report

- Usage comes from 90 days of query history (the log keeps 90). Quarterly or yearly jobs are missed.
- Wildcard queries are only matched in metric contexts (`metric.key` filters, selectors, `metrics` commands).
- The OpenPipeline pipeline behind "unused" routing entries may not be readable. Judge it from ingest volume.
- Series counts for probed metrics exclude `dt.*` dimensions, which are derived from other dimensions.
- Metrics from AWS, Azure or other cloud polling may not appear in the ingest measure used here.

## DQL lessons that bit this analysis

- `sumIf` does not exist: use `sum(if(cond, value, else: 0))`.
- `timeseries ... scalar:true` is cheaper than building an array, and `by:` dimensions that are null group together.
- Notebooks cannot read `$dt_timeframe_*`. Only dashboards can.
- `count()` in `timeseries` does not return datapoints per series. Use ingested datapoints divided by series count.
- `metrics from:now()-2h | filter metric.key == "x" | limit 50` returns the dimensions of a metric. Without `from:` it may be empty.
- Pass DQL through a file. PowerShell 5.1 strips quotes from inline queries.
- Run dtctl calls one at a time. Concurrent token refreshes wiped the saved token.
