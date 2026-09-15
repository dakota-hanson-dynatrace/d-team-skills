# Value Roadmap - Data Collection Query Reference

All queries assume dtctl is authenticated against the target tenant context.
Use `dtctl query` (or alias `dtctl q`) for all DQL queries - `dtctl dql` does not exist.

---

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
dtctl get settings --schema=builtin:alerting.profile
```

Returns array of alerting profile objects. `alerting_profiles` = count of items.

**Gotcha**: `dtctl get alerting-profiles` is not a valid resource name and will fail. The correct approach is Settings 2.0 via `builtin:alerting.profile`.

---

## Notifications Count

```bash
dtctl get settings --schema=builtin:problem.notifications
```

Returns array of classic problem notification channel objects. `notifications_count` = count of items.

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
dtctl get slos
```

Returns array of SLO definitions. `slo_count` = length. 0 triggers the SLO opportunity.

---

## Workflows (AutomationEngine)

```bash
dtctl get workflows
```

Returns array of workflow definitions. `workflow_count` = length. 0 triggers the workflows opportunity.

**Gotcha**: If this returns 403, the tenant may not have AutomationEngine enabled or the token lacks the `automation:workflows:read` scope. Set `workflow_count` to 0 and note the gap.

---

## Classic RUM Apps

```bash
dtctl get settings --schema=builtin:rum.web.app-detection
```

Returns configured web application detection rules. `rum_apps_classic` = count of items.

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
# Azure
dtctl get settings --schema=builtin:hyperscaler-authentication.connections.azure

# AWS
dtctl get settings --schema=builtin:hyperscaler-authentication.connections.aws

# GCP
dtctl get settings --schema=builtin:hyperscaler-authentication.connections.gcp

# Kubernetes (entity-based)
dtctl query 'fetch dt.entity.kubernetes_cluster | summarize count()'
```

`cloud_azure_connected` = true if `builtin:hyperscaler-authentication.connections.azure` returns one or more items with `enabled: true`. Same for AWS and GCP.

`cloud_k8s_clusters` = count from the entity query.

**Gotcha**: `builtin:cloud.azure`, `builtin:cloud.aws`, and `builtin:cloud.gcp` do not exist on Gen3 tenants (404). The correct Gen3 schema prefix is `builtin:hyperscaler-authentication.connections.*`. Check the `enabled` field on each returned item before setting `_connected` to true.

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
