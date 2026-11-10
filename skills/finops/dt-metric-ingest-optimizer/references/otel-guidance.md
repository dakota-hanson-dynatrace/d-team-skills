# OpenTelemetry metrics: managing volume and the sampling window

Use this when writing the OpenTelemetry section and when a probe shows a high-volume source. "Sampling window" here means
how often each series reports a value (the collection or export interval), because every datapoint is billed.

## The levers, in the order to try them

1. **Stop sending what nothing reads.** Filter in the collector so the data never leaves the cluster.
2. **Lengthen the reporting interval.** Datapoints scale with 1 divided by the interval. 10s to 60s is a sixfold cut,
   60s to 300s fivefold. Match the interval to the job of the metric (table below).
3. **Remove labels nobody splits by.** Series count is the product of label values. A pod ID or container ID on a metric
   nobody filters by multiplies volume for no insight. The probe lists the largest labels and their distinct counts.
4. **Send histograms natively.** A classic histogram sent as one series per bucket boundary (`_bucket` keys with an `le` label)
   multiplies datapoints by the number of boundaries (often 10 to 30). An OpenTelemetry Histogram or exponential histogram
   sends one datapoint per series. Keep `_sum` and `_count`. Where percentiles are not used, drop the buckets.
5. **Standardize names.** One name per signal removes duplicates and makes detectors and dashboards portable.

## Interval by kind of metric

| Kind | Interval | Why |
|---|---|---|
| Availability, error rate, latency used by alerts or SLOs | 30 to 60 seconds | Detectors need short windows. |
| Utilization and capacity (CPU, memory, disk, network) | 60 to 120 seconds | Trends matter. |
| Inventory, state, configuration (`*_info`, tolerations, limits, requests, labels) | 300 seconds or more | Values rarely change. |
| Collector and pipeline self-metrics (`otelcol_*`) | 60 to 300 seconds | Health only. |

Before lengthening an interval, check the detectors that read the metric. A detector with a sliding window of 5 samples at
60 seconds watches 5 minutes. At 300 seconds the same setting watches 25 minutes. Adjust the window or keep 60 seconds.

## Where the interval is set

- **Prometheus receiver**: `scrape_interval` per job.
- **SDKs**: `OTEL_METRIC_EXPORT_INTERVAL` in milliseconds.
- **Kubernetes Prometheus annotations or ServiceMonitor**: the scrape interval there.
- **Extensions and ActiveGate**: the polling interval in the extension configuration.

## Dynatrace specifics to state carefully

- Dynatrace ingests OpenTelemetry metrics over OTLP. Counters and histograms must use **delta temporality**. A collector that
  receives cumulative values needs the `cumulativetodelta` processor before export.
- Dynatrace stores each metric key as its own series. A `_bucket` key, the `_sum`/`_count` keys and the base key are
  independent. Nothing is derived from `_bucket` automatically, so removing `_bucket` does not break `_sum` or `_count`.
- The metric type in billing (`summary_stats`, `histogram`, `cardinality`) shows how each datapoint is stored. A large
  `summary_stats` volume on `_bucket` keys, with a small `histogram` volume, usually means histograms arrive as per-bucket
  series instead of native histograms. Confirm the path before recommending a change.
- Where the source cannot be changed, an OpenPipeline metrics pipeline can reduce what is kept. Prefer the source: dropping
  at the source also saves network and collector load.

## How to talk about it

Lead with what is measured (series, interval, labels), then the safe change, then the check. Use the probe numbers for the
tenant, never numbers from another tenant. For example: "The request-duration metric reports about every 60 seconds across
N series, and most of its volume is the bucket series. Moving to a native histogram, or dropping the labels nobody filters
by, removes most of it. Check the latency dashboards before and after."
