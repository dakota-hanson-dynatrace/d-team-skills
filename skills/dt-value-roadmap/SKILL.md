---
name: dt-value-roadmap
description: >
  Produce a Dynatrace branded Value Roadmap PowerPoint for a customer or prospect tenant.
  Gathers live data via dtctl, scores it against the opportunity library, and generates
  a branded deck using the DT template. Leads with post-enablement coverage and anomaly
  findings for newly-connected cloud (AWS/Azure/GCP) and VMware integrations, then
  surfaces the broader account-health opportunities underneath. Use when asked to do an
  account review, gap analysis, health check, cloud/VMware coverage review, or value
  roadmap for a Dynatrace customer or tenant. Triggers: "value roadmap", "gap analysis",
  "account review", "health check", "observability assessment", "cloud coverage review",
  "deck for customer X", "roadmap deck".
---

# Dynatrace Value Roadmap Skill

Produces a customer-facing PowerPoint that shows what a Dynatrace tenant has already built
and presents prioritized next steps to unlock more platform value.

This skill is the readout for the SE cloud + VMware enablement effort: get the customer's
hyperscaler integrations (AWS/Azure/GCP) and the VMware extension enabled, wait a **minimum
of two weeks** so a real baseline exists, then run this skill. The deck leads with discovery
and coverage findings (OneAgent %, log enablement, log-to-trace correlation, cloud/VMware
depth) and data-driven anomaly findings from that newly-monitored estate, with
recommendations scoped to real operational value - not usage for usage's sake. The
pre-existing broad account-health opportunities (SLOs, workflows, alerting, etc.) still
fire and sort underneath.

---

## Prerequisites

- dtctl configured and authenticated against the target tenant context
- `/usr/local/bin/python3.11` with `python-pptx` installed
- `dynatrace-pptx-skill/assets/` present at `~/.claude/skills/dynatrace-pptx-skill/assets/`
- Cloud (AWS/Azure/GCP) and VMware integrations have been enabled for **at least two weeks**
  before running this skill - shorter windows don't give week-over-week/seasonal baselines
  enough signal, and findings should say so if the gate isn't met

---

## Workflow

### Step 0 - Enablement gate

Ask the SE when the cloud and VMware integrations were enabled (or infer it from the
earliest cloud entity/metric timestamp in the tenant). If it's been less than two weeks,
proceed but flag in the final review that anomaly baselines are provisional - call this out
to the SE rather than silently shipping thin findings as confident ones.

### Step 1 - Gather inputs

Ask the SE (if not already known):
1. Customer name (display name for the deck title)
2. dtctl context name for the tenant
3. Cloud posture: which providers (Azure, AWS, GCP) does the customer use for workloads? Are any already connected in Dynatrace?
4. Enablement date for the cloud/VMware integrations (see Step 0)
5. Whether the VMware extension is expected to be present on this tenant at all (some customers have no VMware footprint - that's a legitimate "intentional" answer in Step 2)

### Step 2 - Collect data (and verify permissions in the same pass)

Run every query in `references/queries.md` against the target context exactly once -
each query's result both confirms the permission needed to run it AND supplies the value
for `data.json`. There is no separate permissions pre-check: a 403/auth error on any query
IS the permission failure - report the specific scope/permission missing to the user and
stop. Any other result (including an empty array, `count()=0`, or a scan-limit warning) is
valid and should be used to populate the matching field below.

Replace `<ctx>` with the dtctl context name from Step 1, or omit `--context <ctx>` if using
the active context. Use `--limit 0 --jq ...` on every bare `dtctl get` call (slos,
workflows, settings) rather than the plain form - the agent-mode default caps `get` at 50
items, which both wastes tokens dumping full objects AND silently undercounts
`slo_count`/`workflow_count`/etc. on any tenant with more than 50. See
`references/queries.md` for the exact command per field.

Build a `data.json` with this schema:

```json
{
  "hosts":                   193,
  "hosts_total":             193,
  "hosts_fullstack":         150,
  "hosts_infra":             43,
  "oneagent_fullstack_pct":  78,
  "services":                1286,
  "traces_per_day":          "196M",
  "problems_per_week":       11352,
  "problems_per_day":        1622,
  "alerting_profiles":       32,
  "notifications_count":     32,
  "log_records_24h":         0,
  "pg_with_logs_pct":        55,
  "log_to_trace_pct":        35,
  "slo_count":               0,
  "workflow_count":          0,
  "rum_apps_classic":        6,
  "grail_rum_active":        false,
  "synthetic_monitors":      13,
  "db_services":             880,
  "db_service_pct":          68,
  "cloud_azure_connected":   true,
  "cloud_aws_connected":     false,
  "cloud_gcp_connected":     false,
  "cloud_k8s_clusters":      2,
  "cloud_workloads_exist":   true,
  "cloud_providers_in_use":  "Azure",
  "cloud_integration_live":  true,
  "cloud_hosts_without_oneagent":  12,
  "cloud_services_without_logs":   7,
  "enablement_date":         "2026-09-24",
  "vmware_hosts":            40,
  "vmware_hosts_without_oneagent": 3,
  "vmware_ext_present":      true,
  "vmware_ext_intentional":  null,
  "anomalies": [
    {
      "scope": "cloud",
      "entity": "vm-prod-17",
      "metric": "cpu.usage",
      "kind": "spike",
      "summary": "CPU usage on vm-prod-17 spiked to 3x its 2-week baseline on weekday mornings.",
      "recommendation": "Review autoscaling policy and check for a new batch job scheduled at that time.",
      "severity": "high"
    }
  ]
}
```

**VMware prompt logic**: the primary VMware probe is the metric-namespace check in
`references/queries.md` (`dt.cloud.vmware.hypervisor.*` via `metric.series`) - the
`EXT_*`/`hypervisor.type` checks are fallback only and must NOT independently zero out
`vmware_ext_present` (they produced a false negative on a tenant where VMware was
actively reporting; see queries.md for details). Only when the metric-namespace probe
itself finds nothing, ask the operator running the skill: *"No VMware extension data was
found - is that intentional (no VMware footprint, or extension deliberately not yet
deployed here), or unexpected?"*
- Intentional → set `vmware_ext_present: false`, `vmware_ext_intentional: true`. No VMware
  finding appears in the deck.
- Not intentional → set `vmware_ext_present: false`, `vmware_ext_intentional: false`. The
  deck adds a "VMware Extension Data Not Found" callout plus a roadmap step to fix it.

`anomalies` is built by the model: run the anomaly-baseline queries in
`references/queries.md`, interpret deviations, and write one object per real finding
(cap around 6 - the generator truncates past that). Don't manufacture findings to fill
the slot; an empty `anomalies` list is a legitimate, good result.

`vmware_hosts_without_oneagent` is best-effort: a query for VMware VM-level (not
hypervisor-level) OneAgent gaps isn't confirmed yet (see the VMWARE PROBE section in
`references/queries.md`) - default to 0 if it can't be computed on a given tenant rather
than guessing.

Two slides always render regardless of which opportunities fired, reading `data.json`
directly rather than being driven by opportunity triggers:
- **Executive Overview** (right after the stats slide) - a short bulleted lead-in
  summarizing full-estate OneAgent coverage %, log capture/log-to-trace %, how many
  opportunities fired broken down by tier, and the single top priority.
- **Estate Coverage Overview** (immediately after Executive Overview) - the detail view
  it introduces: stat cards for `hosts_fullstack + hosts_infra` (OneAgent-monitored)
  against `cloud_hosts_without_oneagent` and `vmware_hosts_without_oneagent` (discovered
  but not agented), giving the same full-estate coverage % with the breakdown behind it,
  plus `pg_with_logs_pct` and `log_to_trace_pct`.

`stat_cards` is optional. If omitted, four cards are auto-generated from the data above.
If the SE wants custom cards, add:
```json
  "stat_cards": [
    ["193",   "Hosts\nFully Instrumented"],
    ["1,286", "Services\nAuto-Discovered"],
    ["196M",  "Distributed Traces\nPer Day"],
    ["6",     "Classic RUM Apps\n(Not Yet on Grail)"]
  ]
```

### Step 3 - Generate the deck

```bash
/usr/local/bin/python3.11 ~/.claude/skills/dt-value-roadmap/generate_pptx.py \
  --customer "Acme Corp" \
  --tenant "abc123.apps.dynatrace.com" \
  --data /path/to/data.json \
  --output ~/Desktop/Acme_Value_Roadmap.pptx
```

### Step 4 - Review

Report the output path, the enablement-gate status from Step 0, which VMware branch fired
(present / intentionally absent / unintentionally absent), and the active opportunities
sorted by tier. Ask the SE if any priorities need to be adjusted before delivering.

---

## Opportunity Scoring

The script evaluates every opportunity in `OPPORTUNITIES` plus one entry per item in
`data['anomalies']`. Active ones appear as slides, sorted **Coverage → Anomaly → Start
Here → High Value → Phase 2**. Coverage and Anomaly are the primary findings for this
effort (post-enablement cloud/VMware discovery, depth, and anomalies); the rest are the
pre-existing broad account-health opportunities and still fire underneath.

| Key | Trigger | Tier |
|-----|---------|------|
| `oneagent_coverage` | oneagent_fullstack_pct < 80 OR hosts_infra > 0 | Coverage |
| `log_enablement` | pg_with_logs_pct < 70 OR (log_records_24h == 0 AND hosts > 0) | Coverage |
| `log_to_trace` | log_to_trace_pct < 50 | Coverage |
| `cloud_coverage_gaps` | cloud_integration_live AND (cloud hosts without OneAgent OR cloud services without logs) | Coverage |
| `vmware_coverage` | vmware_ext_present AND vmware_hosts > 0 | Coverage |
| `vmware_data_gap` | NOT vmware_ext_present AND vmware_ext_intentional == false | Anomaly |
| *(one per `data['anomalies']` entry, capped at 6, sorted by severity)* | always, if present | Anomaly |
| `alert_tuning` | problems_per_day > 200 | Start Here |
| `slos` | slo_count == 0 | High Value |
| `workflows` | workflow_count == 0 | High Value |
| `database_extensions` | db_service_pct > 40% | High Value |
| `rum_enablement` | rum_apps_classic > 0 AND grail_rum_active == false | Phase 2 |
| `synthetic_cleanup` | synthetic_monitors > 5 AND rum_apps_classic == 0 | Phase 2 |
| `tagging_strategy` | highlight_tagging == true (manual flag, not auto-triggered) | Phase 2 |

Note: `synthetic_cleanup` only fires when `rum_apps_classic == 0` because `rum_enablement` already mentions synthetic cleanup in its fix text. `vmware_coverage` and `vmware_data_gap` are mutually exclusive by construction - if VMware is intentionally absent (`vmware_ext_intentional == true`), neither fires.

SE can override priority by editing `generate_pptx.py` OPPORTUNITIES list entries before running.

---

## Quick DQL Reference

See `references/queries.md` for full queries with gotchas. Quick commands:

```bash
# Hosts
dtctl query 'fetch dt.entity.host | summarize count()'

# Services (total)
dtctl query 'fetch dt.entity.service | summarize count()'

# DB services (run after service count to calculate db_service_pct)
dtctl query 'fetch dt.entity.service | filter serviceType == "DATABASE_SERVICE" | summarize count()'

# Traces/requests last 24h
dtctl query 'timeseries val=sum(dt.service.request.count), from:now()-24h | fields totalRequests=arraySum(val)'

# Problems last 7 days
dtctl query 'fetch events, from:now()-7d | filter event.category == "PROBLEM" | filter event.kind == "DAVIS_PROBLEM" | summarize count()'

# Alerting profiles (count only - avoid dumping full profile objects)
dtctl get settings --schema=builtin:alerting.profile --limit 0 --jq 'length' -o json

# Classic notification channels (count only)
dtctl get settings --schema=builtin:problem.notifications --limit 0 --jq 'length' -o json

# Log records in last 24h (0 = log monitoring not enabled)
dtctl query 'fetch logs, from:now()-24h | limit 1 | summarize count()'

# SLOs (--limit 0 is required for correctness, not just tokens - the agent-mode
# default caps `get` at 50 items, which silently undercounts slo_count past that)
dtctl get slos --limit 0 --jq 'length' -o json

# Workflows (same --limit 0 requirement)
dtctl get workflows --limit 0 --jq 'length' -o json

# Classic RUM apps (count only)
dtctl get settings --schema=builtin:rum.web.app-detection --limit 0 --jq 'length' -o json

# Grail RUM active? (returns 0 if not active)
dtctl query 'fetch user.events, from:now()-24h | limit 1 | summarize count()'

# Synthetic monitors (sum both results)
dtctl query 'fetch dt.entity.synthetic_test | summarize count()'   # browser/clickpath
dtctl query 'fetch dt.entity.http_check | summarize count()'       # HTTP monitors

# Kubernetes clusters
dtctl query 'fetch dt.entity.kubernetes_cluster | summarize count()'

# Cloud integrations (enabled field per connection - get only what's used, not full objects)
dtctl get settings --schema=builtin:hyperscaler-authentication.connections.azure --limit 0 --jq 'map(.enabled)' -o json
dtctl get settings --schema=builtin:hyperscaler-authentication.connections.aws --limit 0 --jq 'map(.enabled)' -o json
dtctl get settings --schema=builtin:hyperscaler-authentication.connections.gcp --limit 0 --jq 'map(.enabled)' -o json

# OneAgent FullStack coverage % (see references/queries.md for the full join)
dtctl query 'smartscapeNodes "HOST" | lookup [smartscapeNodes "ONEAGENT" | fieldsAdd monitoringMode = coalesce(if(dt.smartscape_source.sender == "dynatrace_codemodule", "APP_ONLY"), if(isNotNull(dt.agent.monitoring_mode), dt.agent.monitoring_mode), "OTHER"), host_ref = toString(references[monitors.host][0])], sourceField: toString(id), lookupField: host_ref | summarize total = count(), fullstack = countIf(lookup.monitoringMode == "FULL_STACK")'

# Log-to-trace correlation % (72h, not 14d - a 14d unbounded log scan hits dtctl's
# 500GB scan limit on any tenant with real log volume; -M=minimal surfaces sampled/
# scan-limit warnings so the SE can caveat the result as approximate)
dtctl query 'fetch logs, from:now()-72h | summarize total = count(), with_trace = countIf(isNotNull(trace_id))' -M=minimal

# Cloud entity census (AWS/Azure/GCP)
dtctl query 'smartscapeNodes "AWS_*" | summarize count(), by: {type}'
dtctl query 'smartscapeNodes "AZURE_*" | summarize count(), by: {type}'
dtctl query 'smartscapeNodes "GCP_*" | summarize count(), by: {type}'

# VMware probe - metric namespace is PRIMARY (EXT_*/hypervisor.type gave false
# negatives on a tenant where VMware was actively reporting - see queries.md)
dtctl query 'fetch metric.series, from:-7d | filter contains(metric.key, "vmware") | summarize countDistinctExact(metric.key)'
```

---

## Deck Structure

Output is always: Cover → Foundation divider → Stats slide → Executive Overview → Estate Coverage Overview → Next Steps divider → N opportunity slides (Coverage → Anomaly → Start Here → High Value → Phase 2) → Roadmap table → How to Get There (phased sequencing of the same roadmap) → Thank you. Total: N + 9 slides.

---

## Improvement Roadmap

### Phase 1 - Run it more (right now)
After each engagement, save `data.json` to `~/.claude/skills/dt-value-roadmap/benchmarks/<tenant-id>.json`. Note which opportunities fired and which the customer already had addressed. After 5 tenants you'll see patterns.

### Phase 2 - Benchmarking (5-10 tenants)
With 10+ saved benchmarks, add peer comparison callouts to slides:
- "Customers with 100-500 hosts typically have X SLOs defined"
- "Alert volume of 1,622/day is 3x the median for this tier"

Add a `--compare` flag to `generate_pptx.py` that reads the benchmarks directory and adds these lines automatically.

### Phase 3 - Automated scoring (15+ tenants)
Add `opportunity_score.py`: maturity score 0-100 per category and overall. Add a score to the cover slide and a radar chart to the current state section.

### Phase 4 - Multi-tenant pipeline
Replace manual dtctl steps with a batch runner:
```bash
for tenant in $(cat tenants.txt); do
  dtctl context use $tenant
  python3 collect.py --output benchmarks/$tenant.json
done
```

Run quarterly against a book of business. Auto-generate updated decks and flag customers who have made progress since last quarter.

### What to do to get to Phase 2
1. Run this skill against 5-10 more tenants (SE demo tenants, sandbox tenants, or willing customers)
2. Save each `data.json` to the benchmarks directory after each run
3. Add `industry` and `company_size` fields to each benchmark file for peer grouping
