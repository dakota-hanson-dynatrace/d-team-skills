# Value Roadmap - Data Collection Query Reference

All queries assume dtctl is authenticated against the target tenant context.
Use `dtctl query` (or alias `dtctl q`) for all DQL queries - `dtctl dql` does not exist.

The sections below are grouped **Coverage / Cloud / VMware / Anomaly** (primary findings
for the post-enablement review) followed by the pre-existing **Secondary** queries that
feed the broader account-health opportunities.

---

## COVERAGE

### OneAgent FullStack Coverage %

Monitoring mode is not a field on the HOST node - it lives on the `ONEAGENT` smartscape
node, joined back to the host via `references[monitors.host]`.

```bash
dtctl query '
  smartscapeNodes "HOST"
  | fieldsAdd host_id_str = toString(id)
  | lookup [
      smartscapeNodes "ONEAGENT"
      | fieldsAdd monitoringMode = coalesce(
            if(dt.smartscape_source.sender == "dynatrace_codemodule", "APP_ONLY"),
            if(isNotNull(dt.agent.monitoring_mode), dt.agent.monitoring_mode),
            "OTHER"),
          host_ref = toString(references[monitors.host][0])
    ], sourceField: host_id_str, lookupField: host_ref
  | fieldsAdd monitoringMode = lookup.monitoringMode
  | summarize total_hosts = count(),
      fullstack = countIf(monitoringMode == "FULL_STACK"),
      infra     = countIf(monitoringMode == "INFRA_ONLY")
  | fieldsAdd oneagent_fullstack_pct = round((toDouble(fullstack)/toDouble(total_hosts))*100, decimals:1)
'
```

Maps to `hosts_total`, `hosts_fullstack` (= fullstack), `hosts_infra` (= infra), `oneagent_fullstack_pct`.

**Gotcha**: access joined fields with dot notation (`lookup.monitoringMode`) - bracket
form silently returns null. A host with no OneAgent at all isn't a smartscape `HOST`
node and won't appear in this count - that's a true discovery gap, not a coverage %
problem; cross-check against the Discovery & Coverage app for the full picture.

### Logs Coverage by Process Group

```bash
dtctl query '
  fetch logs, from:now()-72h
  | summarize log_lines = count(), by: {dt.process_group.id}
  | summarize count()
' -M=minimal
dtctl query 'smartscapeNodes "PROCESS" | summarize count()'
```

`pg_with_logs_pct` = (distinct process groups from the first query / total process groups
from the second) * 100.

**Gotcha (cost)**: use a **72h window, not 14d**. A 14-day unfiltered `fetch logs` scan
hit dtctl's 500GB scan limit on a mid-sized tenant and returned a PARTIAL result even
with `samplingRatio:1000` applied (scanned ~238GB and still truncated) - this is the only
query pattern in this skill that blew the scan budget, because every other `fetch
logs`/`fetch events` query here stays at 24h or less. 72h is long enough to beat a single
quiet day without re-introducing that cost. Pass `-M=minimal` so the model can see
`sampled`/scan-limit warnings in the response and caveat `pg_with_logs_pct` as
approximate in the deck narrative when they appear, instead of presenting it as exact.

### Log-to-Trace Correlation %

```bash
dtctl query '
  fetch logs, from:now()-72h
  | summarize total = count(), with_trace = countIf(isNotNull(trace_id))
  | fieldsAdd log_to_trace_pct = round((toDouble(with_trace)/toDouble(total))*100, decimals:1)
' -M=minimal
```

**Gotcha**: `with_trace == 0` means log-trace correlation/enrichment is off, not that no
requests happened to log. `log_to_trace_pct < 50` is the `log_to_trace` opportunity
trigger. Same 72h/cost rationale as the process-group query above - don't widen this back
to 14d.

---

## CLOUD DEPTH (post-connection)

Cloud connection liveness is covered under Secondary (`hyperscaler-authentication` schema
checks below). These queries measure **depth** once a provider is already connected -
the thing this effort actually cares about, since discovery without OneAgent/logs doesn't
produce real value.

```bash
# Entity census per provider (swap prefix for AWS_ / AZURE_ / GCP_)
dtctl query 'smartscapeNodes "AWS_*" | summarize count(), by: {type}'
dtctl query 'smartscapeNodes "AZURE_*" | summarize count(), by: {type}'
dtctl query 'smartscapeNodes "GCP_*" | summarize count(), by: {type}'

# Active AWS metric flow (confirms the integration is actually streaming, not just configured)
dtctl query 'fetch metric.series, from:-7d | filter dt.source == "AWS Metric Streams" | summarize count = countDistinctExact(metric.key)'
```

**Gotcha**: `builtin:cloud.azure` / `builtin:cloud.aws` / `builtin:cloud.gcp` schemas 404
on Gen3 tenants - use `builtin:hyperscaler-authentication.connections.*` (see Secondary).
Azure and GCP traversals need `"*"` wildcards; the typed relationship field isn't
populated.

`cloud_hosts_without_oneagent` and `cloud_services_without_logs` require cross-referencing
the cloud entity census against the OneAgent coverage query and the logs-by-PG query above
- there's no single query for this; the model builds it by joining the result sets.
`cloud_integration_live` = true once a provider's connection schema shows `enabled: true`
(check with `--jq 'map(.enabled)'` per the Cloud Integrations query under Secondary - don't
dump the full connection objects to read one field) AND the entity census returns > 0 for it.

---

## VMWARE PROBE

**Confirmed live** (previous guidance here was wrong and has been corrected): the VMware
extension reports under the `dt.cloud.vmware.hypervisor.*` metric namespace, with the
hypervisor exposed only as a **metric dimension** (`dt.entity.hypervisor`) - there is no
`HYPERVISOR` smartscapeNodes type and no `EXT_*` entity for it on a tenant where the
extension was confirmed actively reporting 193 distinct `vmware` metrics. Both the
`EXT_*` probe and the `hypervisor.type == "VMWARE"` host check returned **zero** on that
same tenant - a false negative that would incorrectly trigger the "VMware not found, is
this intentional?" operator prompt even with VMware data flowing. Treat the metric probe
as primary; don't let the fallback checks override it.

```bash
# PRIMARY probe - this is the signal that actually detects the extension
dtctl query 'fetch metric.series, from:-7d | filter contains(metric.key, "vmware") | summarize countDistinctExact(metric.key)'

# If the primary probe found metrics, count distinct hypervisors from the dimension
# (swap dt.cloud.vmware.hypervisor.cpu.usage for whichever vmware metric the probe found)
dtctl query 'timeseries val=avg(dt.cloud.vmware.hypervisor.cpu.usage), by:{dt.entity.hypervisor}, from:-7d | summarize count()'

# FALLBACK only - do not let a zero here override a non-zero primary probe result
dtctl query 'smartscapeNodes "HOST" | summarize countIf(hypervisor.type == "VMWARE")'
dtctl query 'smartscapeNodes "EXT_*" | summarize count(), by: {type}'
```

Only when the **primary** metric probe returns zero: set `vmware_hosts` from the
fallback host-level `hypervisor.type` count (it may still catch a differently-licensed
or differently-versioned VMware setup) and treat the extension as **not present**
(`vmware_ext_present: false`). Then ask the operator the intentional/not-intentional
question in `SKILL.md` Step 2 before writing `vmware_ext_intentional`. If the primary
probe finds metrics, set `vmware_ext_present: true` and `vmware_hosts` from the distinct
`dt.entity.hypervisor` count - skip the operator prompt entirely.

**`vmware_hosts_without_oneagent` (best-effort, feeds the Estate Coverage Overview
slide)**: the hypervisor count above is ESXi hosts, not guest VMs - it doesn't tell you
how many VMs lack OneAgent. A VM-level metric dimension analogous to
`dt.entity.hypervisor` likely exists (e.g. under a `dt.cloud.vmware.vm.*` namespace) but
hasn't been confirmed live. Probe for it the same way as the hypervisor check
(`fetch metric.series | filter contains(metric.key, "vmware.vm")`) before trusting it on
a new tenant; default `vmware_hosts_without_oneagent` to 0 rather than guessing if the
probe comes back empty.

---

## ANOMALY BASELINES (dtctl DQL, portable)

Portable across any customer context - no tenant-bound MCP analyzer required. Compare a
recent window against the prior window of equal length over the two-week-plus enablement
period. Run one per domain that has live data (cloud compute, cloud error/throughput,
VMware host/datastore if the extension is present); skip domains with no data rather than
forcing a finding.

```bash
# Week-over-week delta example - swap the timeseries metric per domain
dtctl query '
  timeseries val=avg(dt.host.cpu.usage), by:{dt.entity.host}, from:now()-7d
  | fieldsAdd recent = arrayAvg(val)
'
dtctl query '
  timeseries val=avg(dt.host.cpu.usage), by:{dt.entity.host}, from:now()-14d, to:now()-7d
  | fieldsAdd prior = arrayAvg(val)
'
```

Flag a deviation when the recent window differs from the prior window by a wide enough
margin to be operationally meaningful (not noise) - e.g. a multi-x spike or a steady
directional trend across both windows, not a single-sample blip. For each real deviation
found, write one `anomalies` entry: `{scope, entity, metric, kind, summary,
recommendation, severity}`. `kind` is a short label (`spike`, `trend`, `drop`); `severity`
is `high`/`medium`/`low` and controls sort order and the 6-finding cap in the generator.

**Gotcha**: seasonal patterns need at least two full weekly cycles to separate real
anomalies from normal day-of-week variation - this is exactly why the skill gates on two
weeks of enablement (SKILL.md Step 0). Don't report a seasonal-style finding off less data
than that; a plain week-over-week delta is the safer comparison on a borderline-short
window.

---

## SECONDARY (broad account-health queries)

These still feed the `alert_tuning` / `slos` / `workflows` / `database_extensions` /
`rum_enablement` / `synthetic_cleanup` / `tagging_strategy` opportunities, which sort
below Coverage and Anomaly findings but still fire when triggered.

## Hosts

```bash
dtctl query 'fetch dt.entity.host | summarize count()'
```

Returns total instrumented host count. Maps to `hosts`.

**Gotcha**: This counts OneAgent-instrumented hosts only. Hosts monitored via extension or cloud integration only won't appear here.

---

## Services

```bash
# Total services
dtctl query 'fetch dt.entity.service | summarize count()'

# Database services only
dtctl query 'fetch dt.entity.service | filter serviceType == "DATABASE_SERVICE" | summarize count()'
```

`services` = total count. `db_services` = database count. `db_service_pct` = (db / total) * 100, rounded.

**Gotcha**: serviceType values include `WEB_REQUEST_SERVICE`, `DATABASE_SERVICE`, `MESSAGING_SERVICE`, `CUSTOM_SERVICE`, etc. DATABASE_SERVICE is the right filter for the database extensions opportunity.

---

## Traces / Request Volume

```bash
dtctl query 'timeseries val=sum(dt.service.request.count), from:now()-24h | fields totalRequests=arraySum(val)'
```

Returns a single `totalRequests` number. Convert to display string for `traces_per_day` (e.g., 178549877 -> "178M").

**Gotcha**: Nested aggregation `summarize sum(sum(...))` over timeseries output is invalid DQL and will fail with NO_NESTED_AGGREGATIONS. Use the `timeseries ... | fields arraySum(val)` pattern instead.

---

## Problems

```bash
# Last 7 days
dtctl query 'fetch events, from:now()-7d | filter event.category == "PROBLEM" | filter event.kind == "DAVIS_PROBLEM" | summarize count()'

# Last 24h (for problems_per_day)
dtctl query 'fetch events, from:now()-24h | filter event.category == "PROBLEM" | filter event.kind == "DAVIS_PROBLEM" | summarize count()'
```

Maps to `problems_per_week` and `problems_per_day`.

**Gotcha**: Filter `event.kind == "DAVIS_PROBLEM"` to avoid counting CUSTOM_ANNOTATION or INFO events as problems. `dtctl get problems` is not a valid resource type - DQL is the only working approach.

---

## Alerting Profiles

```bash
dtctl get settings --schema=builtin:alerting.profile --limit 0 --jq 'length' -o json
```

`alerting_profiles` = the returned count. `--limit 0 --jq 'length'` is required, not just
a token optimization: the agent-mode default caps `get` at 50 items, so the bare command
would silently undercount on any tenant with more than 50 profiles.

**Gotcha**: `dtctl get alerting-profiles` is not a valid resource name and will fail. The correct approach is Settings 2.0 via `builtin:alerting.profile`.

---

## Notifications Count

```bash
dtctl get settings --schema=builtin:problem.notifications --limit 0 --jq 'length' -o json
```

`notifications_count` = the returned count. Same `--limit 0` correctness requirement as above.

**Gotcha**: `dtctl get notifications` queries AutomationEngine notification integrations, not classic problem channels - it will return 0 even when classic channels exist. For classic notification channels, use `builtin:problem.notifications`. Note that `notifications_count` and `alerting_profiles` will differ in most tenants; they are separate counts.

---

## Log Monitoring

```bash
dtctl query 'fetch logs, from:now()-24h | limit 1 | summarize count()'
```

Returns 1 if any logs exist in the last 24h, 0 if log monitoring is not enabled.

`log_records_24h` = 0 triggers the log monitoring opportunity.

**Gotcha**: A count of 0 can also mean log monitoring is enabled but no logs matched. To distinguish: if OneAgent is deployed on hosts (hosts > 0) and log_records_24h is 0, it is almost certainly not enabled rather than a filtering issue - the default log sources generate noise immediately.

---

## SLOs

```bash
dtctl get slos --limit 0 --jq 'length' -o json
```

`slo_count` = the returned count. 0 triggers the SLO opportunity.

**Gotcha (correctness, not just tokens)**: `--limit 0` is required. The agent-mode
default caps `get` at 50 items - a bare `dtctl get slos` on a tenant with more than 50
SLOs returns exactly 50 and silently misreports `slo_count` as non-zero-but-wrong instead
of the true count (confirmed live: a tenant with 52 actual SLOs returned 50 from the bare
command).

---

## Workflows (AutomationEngine)

```bash
dtctl get workflows --limit 0 --jq 'length' -o json
```

`workflow_count` = the returned count. 0 triggers the workflows opportunity.

**Gotcha**: If this returns 403, the tenant may not have AutomationEngine enabled or the token lacks the `automation:workflows:read` scope. Set `workflow_count` to 0 and note the gap. Same `--limit 0` correctness requirement as SLOs above (confirmed live: a tenant with 142 actual workflows returned 50 from the bare command).

---

## Classic RUM Apps

```bash
dtctl get settings --schema=builtin:rum.web.app-detection --limit 0 --jq 'length' -o json
```

Returns the count of configured web application detection rules. `rum_apps_classic` = that count.

**Gotcha**: This counts configured apps, not necessarily apps with active JS beacons. An app configured in classic RUM but with no beacon traffic will still appear here.

---

## Grail RUM Active

```bash
dtctl query 'fetch user.events, from:now()-24h | limit 1 | summarize count()'
```

Returns 1 if the new Grail RUM experience is active and receiving data, 0 if not.

`grail_rum_active` = true if count > 0.

**Gotcha**: `user.events` and `user.sessions` are the new Grail RUM tables. Classic RUM data does NOT appear here - it lives in a separate data store. Zero records means the new experience is not enabled, even if classic RUM is fully configured.

**Secondary check**:
```bash
dtctl query 'fetch user.sessions, from:now()-24h | limit 1 | summarize count()'
```

Both should return 0 if RUM is not active on the new platform.

---

## Synthetic Monitors

```bash
# Browser and clickpath monitors
dtctl query 'fetch dt.entity.synthetic_test | summarize count()'

# HTTP monitors
dtctl query 'fetch dt.entity.http_check | summarize count()'
```

`synthetic_monitors` = sum of both counts.

**Gotcha**: `dtctl get synthetic-monitors` is not a valid resource name and will fail. Use the two entity DQL queries above and add the results. `dt.entity.synthetic_test` covers browser/clickpath monitors; `dt.entity.http_check` covers HTTP monitors. `dt.entity.multiprotocol_monitor` covers the newer Gen3 synthetic type - include it if the tenant uses Gen3 synthetics.

---

## Cloud Integrations

```bash
# Azure - just the enabled flags per connection, not the full objects
dtctl get settings --schema=builtin:hyperscaler-authentication.connections.azure --limit 0 --jq 'map(.enabled)' -o json

# AWS
dtctl get settings --schema=builtin:hyperscaler-authentication.connections.aws --limit 0 --jq 'map(.enabled)' -o json

# GCP
dtctl get settings --schema=builtin:hyperscaler-authentication.connections.gcp --limit 0 --jq 'map(.enabled)' -o json

# Kubernetes (entity-based)
dtctl query 'fetch dt.entity.kubernetes_cluster | summarize count()'
```

`cloud_azure_connected` = true if the Azure array contains any `true`. Same for AWS and GCP.

`cloud_k8s_clusters` = count from the entity query.

**Gotcha**: `builtin:cloud.azure`, `builtin:cloud.aws`, and `builtin:cloud.gcp` do not exist on Gen3 tenants (404). The correct Gen3 schema prefix is `builtin:hyperscaler-authentication.connections.*`. Use `--jq 'map(.enabled)'` instead of dumping the full connection objects (which include ARNs and other config you don't need) - and apply `--limit 0` here too, since this schema is subject to the same 50-item agent-mode default as `get slos`/`get workflows`.

**cloud_providers_in_use**: Ask the SE. This is the display string used in slide text (e.g., "Azure", "AWS", "Azure and AWS"). It is NOT derived from the API - it reflects what the customer is actually using for workloads, not what is currently connected to Dynatrace.

**cloud_workloads_exist**: Ask the SE. True if the customer has cloud workloads that are not yet connected to Dynatrace. The cloud_extension opportunity only fires when this is true AND no provider is connected.

---

## Dashboards (optional, not scored)

```bash
dtctl get dashboards
```

Returns dashboard list. Useful context for the SE but not used in opportunity scoring.

---

## Problem Type Breakdown (optional)

For enriching the alert_tuning slide body text:

```bash
dtctl query '
  fetch events, from:now()-7d
  | filter event.category == "PROBLEM" and event.kind == "DAVIS_PROBLEM"
  | summarize count(), by: {event.status}
'
```

For breakdown by problem type (slowdown / error / availability / contention):

```bash
dtctl query '
  fetch events, from:now()-7d
  | filter event.category == "PROBLEM" and event.kind == "DAVIS_PROBLEM"
  | summarize count(), by: {dt.davis.impact_level}
'
```

---

## Traces Per Day - Display Formatting

Raw number -> display string:

| Raw | Display |
|-----|---------|
| 1,234,567 | "1.2M" |
| 196,000,000 | "196M" |
| 1,500,000,000 | "1.5B" |
| 45,000 | "45K" |

Use the display string for `traces_per_day` in data.json since it appears verbatim on slides.

---

## Data Collection Checklist

### Coverage / Cloud / VMware / Anomaly (primary)
- [ ] hosts_total, hosts_fullstack, hosts_infra (int) - via the OneAgent coverage join
- [ ] oneagent_fullstack_pct (int, 0-100)
- [ ] pg_with_logs_pct (int, 0-100) - via logs-by-PG vs total PROCESS nodes
- [ ] log_to_trace_pct (int, 0-100)
- [ ] cloud_integration_live (bool), cloud_hosts_without_oneagent (int), cloud_services_without_logs (int)
- [ ] enablement_date (string, ask SE) - gates how much to trust seasonal-style anomalies
- [ ] vmware_hosts (int) - from hypervisor.type=="VMWARE" host count
- [ ] vmware_ext_present (bool) - from the EXT_*/metric probe
- [ ] vmware_ext_intentional (bool or null) - **only set when vmware_ext_present is false**; ask the operator
- [ ] anomalies (list, can be empty) - one entry per real deviation found, capped ~6

### Secondary (broad account-health)
- [ ] hosts (int)
- [ ] services (int)
- [ ] db_services (int) and db_service_pct (int, 0-100)
- [ ] traces_per_day (string, human-readable)
- [ ] problems_per_week (int)
- [ ] problems_per_day (int)
- [ ] alerting_profiles (int) - via `builtin:alerting.profile`
- [ ] notifications_count (int) - via `builtin:problem.notifications`
- [ ] log_records_24h (int, usually 0 or 1)
- [ ] slo_count (int)
- [ ] workflow_count (int)
- [ ] rum_apps_classic (int)
- [ ] grail_rum_active (bool)
- [ ] synthetic_monitors (int) - sum of synthetic_test + http_check entity counts
- [ ] cloud_azure_connected (bool) - via `builtin:hyperscaler-authentication.connections.azure`
- [ ] cloud_aws_connected (bool) - via `builtin:hyperscaler-authentication.connections.aws`
- [ ] cloud_gcp_connected (bool) - via `builtin:hyperscaler-authentication.connections.gcp`
- [ ] cloud_k8s_clusters (int)
- [ ] cloud_workloads_exist (bool, ask SE)
- [ ] cloud_providers_in_use (string, ask SE)
