# Value Roadmap - Data Collection Query Reference

All queries assume dtctl is authenticated against the target tenant context.

---

## Hosts

```bash
dtctl dql 'fetch dt.entity.host | summarize count()'
```

Returns total instrumented host count. Maps to `hosts`.

**Gotcha**: This counts OneAgent-instrumented hosts only. Hosts monitored via extension or cloud integration only won't appear here.

---

## Services

```bash
# Total services
dtctl dql 'fetch dt.entity.service | summarize count()'

# Database services only
dtctl dql 'fetch dt.entity.service | filter serviceType == "DATABASE_SERVICE" | summarize count()'
```

`services` = total count. `db_services` = database count. `db_service_pct` = (db / total) * 100, rounded.

**Gotcha**: serviceType values include `WEB_REQUEST_SERVICE`, `DATABASE_SERVICE`, `MESSAGING_SERVICE`, `CUSTOM_SERVICE`, etc. DATABASE_SERVICE is the right filter for the database extensions opportunity.

---

## Traces / Request Volume

```bash
# Total requests in last 24h (as a count for display)
dtctl dql 'timeseries sum(dt.service.request.count), from:now()-24h | summarize sum(sum(dt.service.request.count))'
```

This returns a raw number. Convert to display string for `traces_per_day` (e.g., 196,000,000 → "196M").

**Gotcha**: `dt.service.request.count` is a delta metric (rate × interval), so summing across the 24h window gives total request count.

---

## Problems

```bash
# Last 7 days
dtctl dql 'fetch events, from:now()-7d | filter event.category == "PROBLEM" | filter event.kind == "DAVIS_PROBLEM" | summarize count()'

# Last 24h (for problems_per_day)
dtctl dql 'fetch events, from:now()-24h | filter event.category == "PROBLEM" | filter event.kind == "DAVIS_PROBLEM" | summarize count()'
```

Maps to `problems_per_week` and `problems_per_day`.

**Alternative**: `dtctl get problems --from=now-7d` returns the problems list; use `.length` of the result array. DQL is more reliable for large volumes since the REST API paginates.

**Gotcha**: Filter `event.kind == "DAVIS_PROBLEM"` to avoid counting CUSTOM_ANNOTATION or INFO events as problems.

---

## Alerting Profiles

```bash
dtctl get alerting-profiles
```

Returns a JSON array. `alerting_profiles` = count of items. `notifications_count` = same count (classic integrations are 1:1 with profiles in most configs, but verify).

**Gotcha**: The API only returns classic alerting profiles. AutomationEngine notification integrations (Settings 2.0) are separate - check `workflow_count` via workflows endpoint.

---

## Log Monitoring

```bash
dtctl dql 'fetch logs, from:now()-24h | limit 1 | summarize count()'
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

**Gotcha**: This endpoint requires the AutomationEngine API scope. If it returns 403, the tenant may not have AutomationEngine enabled or the token lacks the scope. In that case, set `workflow_count` to 0 (the opportunity is relevant regardless) and note the scope gap.

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
dtctl dql 'fetch user.events, from:now()-24h | limit 1 | summarize count()'
```

Returns 1 if the new Grail RUM experience is active and receiving data, 0 if not.

`grail_rum_active` = true if count > 0.

**Gotcha**: `user.events` and `user.sessions` are the new Grail RUM tables. Classic RUM data does NOT appear here - it lives in a separate data store. Zero records means the new experience is not enabled, even if classic RUM is fully configured.

**Secondary check**:
```bash
dtctl dql 'fetch user.sessions, from:now()-24h | limit 1 | summarize count()'
```

Both should return 0 if RUM is not active on the new platform.

---

## Synthetic Monitors

```bash
dtctl get synthetic-monitors
```

Returns array of synthetic monitor definitions. `synthetic_monitors` = length.

**Gotcha**: This returns all monitors regardless of enabled/disabled status. Filter to `enabled: true` if you want only active monitors.

---

## Cloud Integrations

```bash
# Azure
dtctl get settings --schema=builtin:cloud.azure

# AWS
dtctl get settings --schema=builtin:cloud.aws

# GCP
dtctl get settings --schema=builtin:cloud.gcp

# Kubernetes (entity-based)
dtctl dql 'fetch dt.entity.kubernetes_cluster | summarize count()'
```

`cloud_azure_connected` = true if builtin:cloud.azure returns one or more configured credentials with enabled=true. Same for AWS and GCP.

`cloud_k8s_clusters` = count from the entity query.

**Gotcha**: `dtctl get settings --schema=builtin:cloud.azure` returns all credentials, including disabled ones. Check the `enabled` field on each item before setting `_connected` to true.

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
dtctl dql '
  fetch events, from:now()-7d
  | filter event.category == "PROBLEM" and event.kind == "DAVIS_PROBLEM"
  | summarize count(), by: {event.status}
'
```

For breakdown by problem type (slowdown / error / availability / contention):

```bash
dtctl dql '
  fetch events, from:now()-7d
  | filter event.category == "PROBLEM" and event.kind == "DAVIS_PROBLEM"
  | summarize count(), by: {dt.davis.impact_level}
'
```

---

## Traces Per Day - Display Formatting

Raw number → display string:

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
- [ ] alerting_profiles (int)
- [ ] notifications_count (int)
- [ ] log_records_24h (int, usually 0 or 1)
- [ ] slo_count (int)
- [ ] workflow_count (int)
- [ ] rum_apps_classic (int)
- [ ] grail_rum_active (bool)
- [ ] synthetic_monitors (int)
- [ ] cloud_azure_connected (bool)
- [ ] cloud_aws_connected (bool)
- [ ] cloud_gcp_connected (bool)
- [ ] cloud_k8s_clusters (int)
- [ ] cloud_workloads_exist (bool, ask SE)
- [ ] cloud_providers_in_use (string, ask SE)
