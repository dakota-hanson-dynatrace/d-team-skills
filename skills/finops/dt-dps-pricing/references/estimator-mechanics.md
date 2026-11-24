# Usage Estimator conversion mechanics, by category

All sheets below are in `Dynatrace DPS Usage Estimator.xlsm`. Every sheet's output is a DPS usage
quantity that rolls up into **Results Summary**'s "Equivalent qty in DPS rate card volumes" column,
which is what feeds "Model DPS based on usage" in the Pricing Tool.

Two global routing toggles live on Results Summary and are referenced by several sheets below:
`isUseMetricsPoweredByGrail` and `isUseTracesOnGrail`. Each is a single switch shared across every
sheet that produces that telemetry type — flip one and you re-route *all* of that type's usage
(Host traces, Serverless Functions, OpenTelemetry, Custom Metrics) between the Grail line items and
the Classic SKU line items at once. Check its state before reasoning about any one sheet in
isolation.

## Host Monitoring with AppSec

Per-host rows: Memory Avail (RAM GiB), Server Qty, Annual Uptime %, Monitoring Mode (Full Stack /
Infra / F&D), App Sec Mode, Security Posture Mgt toggle.

- **Hosts with < 4 GiB RAM are rounded up to 4 GiB** for Full-Stack, RVA, and RAP memory-GiB-hour
  calculations (not for Infrastructure Monitoring, which bills host-hours, not memory).
- RVA and RAP consume memory-GiB-hours on the same floored RAM figure as Full-Stack — they are not
  a separate per-host input.
- Trace retention has an optional extra-days add-on (`trace_rention_extra_days`, cell G8 on this
  sheet) — 10 days are included free, and using the extra-days add-on requires traces-on-Grail
  (`isUseTracesOnGrail` = true). This same named range/pool is shared with Serverless Functions and
  OpenTelemetry (see below) — size it once across all three trace sources, not per-sheet.

## Log Mgt Analytics

Four retention-day buckets per log source line. Fields per line: GiB/day, retention days, included
query days (free query allowance — effectively floors at 10 days even if entered lower), egress
yes/no, retention factor (default 0.9), enrichment factor (default 2x for typical K8s+OneAgent
enrichment; use 3x for heavy K8s+OneAgent enrichment, 1x for log ingest with no OneAgent).

A separate "logs to metrics" conversion on the same sheet estimates metric data points generated
from a user-set percentage of log messages that get converted to metrics.

## Kubernetes Monitoring — three non-overlapping paths

Do not combine these for the same pods:

1. **Host-deployed full-stack monitoring** — pod-hours are included free under Host Monitoring's
   Full-Stack memory-GiB-hours; there is no separate K8s line item for this path.
2. **Container Application Monitoring** — container-hours (separate SKU, $700/100,000).
3. **Kubernetes Platform Monitoring** — pod-hours (separate SKU, $200/100,000).

Recommended sizing input: average daily running pods × 1.5 buffer. Related inputs elsewhere in the
workbook ("% of full-stack usage that is K8S" and "% of host RAM used by containers in K8S", rows
47–48 on the Pricing Tool's "Model DPS based on usage" sheet) exist specifically to help a reviewer
untangle how much of the Full-Stack memory-GiB-hours figure is actually K8s workload, for sanity
checking against paths 2/3 above.

## Digital Experience

- Synthetic Browser Monitoring = `(# scripts × avg actions/script) × (executions/hour × 24 × 365) ×
  # locations`.
- Synthetic HTTP Monitoring = `(# monitors × executions/hour) × 24 × 365 × # locations`.

## Database Monitoring

- Base usage: `# db instances/day × avg lifetime hours/day × 365` → db-instance-hours/year.
- Free tier: 1,000 normalized queries per 15-minute interval per instance, included at no charge.
  **The query count field is per 15-minute interval, not per day** — a common misread.
- Overage: for instances exceeding the quota, `(avg normalized queries/instance − 1,000) ×
  # overage instances / 1,000 × lifetime hours/day × 365` adds *additional* db-instance-hours on top
  of the base figure. Base and overage both land on the single Database Monitoring DPS line — don't
  report only one of the two.

## Serverless Functions

- Custom metrics: `# distinct functions × 9 metrics/function × 60 × 24 × 365` data points/year (9
  metrics/function is a baked-in assumption).
- Routed by `isUseTracesOnGrail`:
  - OFF → `monthly requests × 12` annual invocations under **Serverless Functions Classic**.
  - ON → `(monthly requests × 12) × 1.6 KB/span × 5 spans/request / 1024 / 1024` → GiB trace
    ingest/year, under **Traces - Ingest & Process**.
- Trace retention extra-days usage draws on the same shared `trace_rention_extra_days` pool as Host
  Monitoring (10 days included free across Host + Serverless + OpenTelemetry combined).

## Code Monitoring

Trivial sheet: `avg containers/day × avg container lifetime hours/day × 365` → container-hours/year,
feeding the Code Monitoring DPS line directly. Same unit as Container Application Monitoring but a
distinct SKU ($500/100,000 vs $700/100,000) — don't conflate the two.

## Mainframe

Single input: total MSUs consumed across all LPARs for **one month** (from the IBM SCRT report).
`annual MSU-hours = monthly MSUs × 12`. The sheet's own worked example (99,000 MSUs/month × 12 =
1,188,000/year) exists specifically because entering a daily figure or an already-annualized figure
is a common mistake.

## Automation Engine

`# of workflows × avg hours/year each workflow exists` → workflow-hours, a direct 1:1 feed to the
Automation Workflow DPS line. **This is workflow *existence* time, not execution/run time** — a
workflow enabled all year counts 8,760 hours regardless of how often it actually fires.

## OpenTelemetry

- Custom metrics: `# distinct OTel metrics/minute × 60 × 24 × 365` data points/year.
- Spans/traces (same `isUseTracesOnGrail` toggle as Serverless Functions):
  - OFF → `OTel spans ingested/day × 365` spans/year, under **Custom Traces Classic (OpenTelemetry)**.
  - ON → `(spans/day × 1.6 KB/span × 365) / (1024 × 1024) + (GiB of OTel trace data ingested/day ×
    365)` → GiB/year under **Traces - Ingest & Process**. The sheet accepts spans/day and/or GiB/day
    directly as alternative ways to express the same ingest — don't double-enter both for the same
    traffic.
- Same shared `trace_rention_extra_days` 10-day-free pool as Host Monitoring and Serverless
  Functions — reason about trace retention across all three sources together, not sheet by sheet.

## Custom Metrics

Aggregates data points from three independent sources, all of which must be summed for a complete
figure (easy to transcribe only one and under-count):

1. Manual override — `# unique custom metrics/minute known × 60 × 24 × 365`.
2. Cloud services / Extensions sub-table — a simplified generic device list on this sheet itself
   (SNMP generic, Palo Alto, Fortinet, Checkpoint, Cisco Firepower, F5 BIG-IP, DB hosts, each with a
   hardcoded "typical metrics per device" constant), plus pointers out to the full AWS/Azure/GCP
   Cloud Services sheets and the detailed/quick Extensions sheets (see below).
3. NAM sub-table (synthetic network checks) — ICMP = 6 metrics/execution, TCP = 3, DNS = 3;
   `executions/hour × 8,760 hours/year × metrics/execution`. Note this sub-table annualizes with
   `8760` directly while the device sub-table above annualizes with `60 × 24 × 365` — same result,
   different formula shape, worth noting if auditing formulas cell-by-cell.

A single `isUseMetricsPoweredByGrail`-style toggle on this sheet routes the whole total to either
**Metrics - Ingest & Process** (Grail) or **Custom Metrics Classic**.

## Extensions (detailed estimator)

Per-technology custom-metric calculators: VMware, Citrix NetScaler/XenApp, F5 BIG-IP, IBM
DataPower/MQ/iSeries, Juniper, SAP ABAP/HANA, Windows Server, Apigee, Tibco EMS, Oracle, MSSQL, DB2
LUW, MySQL, OS Services, Disk Analytics (19 blocks total). Each block: user enters a device/instance
count; a hardcoded "metrics per instance" constant is multiplied in; annualized uniformly at
`× 60 × 24 × 365`.

**Gotcha:** several blocks use `IF(D<>"", D*constant1, constant2*constant1)` — i.e. if the
per-item count is left blank, the formula does **not** zero out, it silently substitutes a
different hardcoded default assumption. Blank ≠ excluded on this sheet.

Citrix XenApp and SAP ABAP blocks also produce a side-output of RUM sessions (`RUMfromExtensions`
named range) — these two are the only extensions that generate RUM; don't expect it from the
others.

## Extensions Quick Estimator

A coarser alternative to the detailed Extensions sheet, covering the *same* set of technologies.
Per technology, pick a method: `Skip` / `Number of devices` (small/medium/large counts × per-size
DDU constants) / `Typical amount – average` or `– large` (flat DDU constant, no device count
needed). DDU (Davis Data Unit) constants convert back to custom-metric-data-points at
`1,000 data points = 1 DDU`. Citrix XenApp and SAP ABAP again produce a RUM side-output.

**Double-count risk:** this sheet and the detailed Extensions sheet are two ways to estimate the
*same* technologies — confirm only one was filled in for any given technology, not both.

## AWS / Azure / GCP Cloud Services

Same pattern across all three clouds (different service catalogs): a "default" block of services
Dynatrace's native cloud integration always polls (instance count only, metrics/instance is fixed),
plus a long "optional services" list (instance count × metrics/instance, with a reference "avg
available" column). Output = `(metrics/instance × instance count) × (polling frequency × 24 × 365)`,
where polling frequency is a single shared constant per cloud sheet (60/hour, i.e. once per minute).

These three sheets are standalone — their output feeds the **Custom Metrics** category total, not
Host Monitoring. This is additive by design, not a duplicate: the same cloud instances legitimately
generate both Host Monitoring hours (if monitored via OneAgent/Full-Stack) *and* Custom Metrics data
points (if polled via the native cloud integration) — two different DPS categories for the same
instances is correct, but easy to mistake for double counting at first glance.

## Cloud Sizing Tool

Not a calculator — four lines of text pointing reps to an internal/external AWS/Azure/GCP sizing
tool (host units + DDUs for AWS/Azure, DDUs only for GCP). No formulas, no inputs; it exists
out-of-workbook.

## Cloud Servers Lookup

Pure reference table: Cloud Provider / Instance Name / RAM GB, ~888 rows (e.g. `a1.2xlarge` → 16
GB). A lookup source (almost certainly feeding Host Monitoring's "Memory Avail" column so a rep can
pick an instance type and auto-fill RAM) — no usage output of its own.
