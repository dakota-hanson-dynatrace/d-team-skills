# Remediation catalog by source and metric family

Use this to turn a finding into concrete steps. Pick the lever at the point where the data is produced, then confirm in
Dynatrace. Always list the check to run afterwards.

## By source (`grail.metric.source`)

| Source | Where to act | Typical steps |
|---|---|---|
| `opentelemetry` | Collector or SDK | Filter processor to drop unused names. Lengthen export or scrape interval. Transform processor to delete labels. Native histograms. `cumulativetodelta` before export. |
| (blank) | Scraper or exporter | Prometheus scrape config: `metric_relabel_configs` drop, `scrape_interval`, labeldrop. Micrometer: meter filters and publishing step. |
| `dynatrace_osagent` | OneAgent configuration | Disable custom metric collection nobody queries. |
| `dynatrace_codemodule` | Application metrics registry | Restrict exported meters, limit tags. |
| `k8s_monitoring` | Kubernetes monitoring settings | Narrow namespaces and workloads. |
| `openpipeline:*` | OpenPipeline | Delete unused metric extraction rules. Reduce dimensions in the rule. |
| `com.dynatrace.extension.*` | Extension configuration | Trim feature sets and metric selections. Lengthen the polling interval. |

## By family (prefix of the metric key)

| Family | Common cause | What to look at |
|---|---|---|
| `kube_*` | kube-state-metrics emits dozens of per-pod series | Drop state and info series nobody reads (tolerations, status reasons, timestamps). Keep readiness, restarts, phase if detectors use them. |
| `container_*` | cAdvisor per-container series | Keep CPU and memory working set. Drop spec and filesystem series nobody reads. Lengthen the interval. |
| `node_*` | node-exporter | Drop collectors you do not use (filesystem details, guest CPU, zswap). |
| `istio_*`, `envoy_*` | Sidecar metrics with many labels | Drop unused labels (destination details, security policy). Fewer histogram buckets. Aggregate per service. |
| `otelcol_*` | Collector self-metrics | Keep a handful for health. Lengthen the interval. Drop per-component series. |
| `argocd_*` | Argo CD controller metrics | Keep sync and health. Drop request and Git detail nobody reads. |
| `kafka_*` | Client metrics with many per-topic series | Filter to the topics and metrics alerts use. |
| `http_*`, `rpc_*`, `grpc_*` | Service request metrics | Keep RED metrics. Remove high-cardinality labels (URI with IDs). |

## Histograms (`_bucket`)

1. If nothing reads the percentile, drop the `_bucket` series and keep `_sum` and `_count`.
2. If percentiles are used, send a native histogram and fewer boundaries.
3. Remove labels the dashboards do not split by.

## Anomaly detectors

1. Group detectors by template (query with per-team values removed) and threshold tier.
2. Merge each group into one detector grouped by workload dimensions.
3. Put the dimensions in the event name and properties.
4. Route notifications from a workflow triggered by the event, using a lookup table from namespace or team to channel.
5. Pilot one family, run side by side for a week, compare alerts per team, then disable the copies.
6. Review detectors that never fire with their owners.

## Attribution

Add a cost-center and product attribute at the point of collection (collector resource attribute) or with an OpenPipeline
rule, so billed volume can be charged back. Report the unassigned share monthly.
