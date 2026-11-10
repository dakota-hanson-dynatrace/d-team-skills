# Value Roadmap - Config Hygiene and Gen2/Gen3 Query Reference

> **Manual fallback only.** `collect.py` runs these queries automatically. Use this file to debug a
> field that came back wrong or to extend the collector - not as part of a normal run.

## dtctl VERSION DIFFERENCES (read first)

`--limit 0 --jq ...` exists only on newer dtctl builds. dtctl 0.28.x has neither flag - every
`dtctl get` there fails with `unknown flag --limit`. On those builds `get` already pages through
everything (`--chunk-size` default 500), so the undercount risk does not apply. Portable form that
works on both:

```bash
dtctl get settings --schema=builtin:alerting.profile --context <ctx> --no-agent -o json > alerting.profile.json
```

Save each schema to a file and parse it (node, python, or jq if installed) rather than re-querying.
On Windows PowerShell 5.1, inline `dtctl query '... "string" ...'` loses the inner quotes; write the DQL
to a file and use `dtctl query -f q.dql` from Bash.

**Never run dtctl calls in parallel** (including `dt-upgrade-readiness/scripts/collect.py`, which
defaults to several workers - pass `--workers 1`). Concurrent OAuth refreshes have wiped a stored
token mid-run.

---

## CONFIG HYGIENE (feeds the Config Fix tier)

These catch configuration that exists but silently does not work. Pull the schemas once, then
derive every field from the saved JSON.

```bash
for s in builtin:alerting.profile builtin:problem.notifications builtin:management-zones \
         builtin:tags.auto-tagging builtin:anomaly-detection.metric-events builtin:davis.anomaly-detectors \
         builtin:monitoring.slo builtin:logmonitoring.log-storage-settings builtin:networkzones; do
  dtctl get settings --schema="$s" --context <ctx> --no-agent -o json > "${s#builtin:}.json"
done
dtctl get segments --context <ctx> --no-agent -o json > segments.json
dtctl get buckets  --context <ctx> --no-agent -o json > buckets.json
```

| Field | How to derive |
|---|---|
| `alerting_profiles_no_rules` | profiles with `value.severityRules` empty. Include the attached notification in the label (match `problem.notifications[].value.alertingProfile` to the profile `objectId`) - "no rules + a live channel" is the case that matters |
| `alerting_profiles_test` | profile names containing TEST/test that have a notification attached |
| `alerting_profiles_orphaned` | profiles no notification references |
| `mz_issues` | one plain sentence per broken zone: rules keyed on `entityId`/`PROCESS_GROUP_ID` (fragile), tag values with typos (compare against real tag values below), zones with 0 members |
| `mz_count` | length of management-zones.json |
| `custom_segment_count` | segments whose owner is not "Dynatrace" (the 10 built-in segments don't count) |
| `classic_slo_count` | length of monitoring.slo.json (classic). Gen3 SLOs come from `dtctl get slos` |
| `log_retention_days` | `retentionDays` of the `default_logs` bucket |

Membership and tag checks:

```bash
dtctl query 'fetch dt.entity.host | expand mz=managementZones | summarize count(), by:{mz}'
dtctl query 'fetch dt.entity.service | expand mz=managementZones | summarize count(), by:{mz}'
dtctl query 'fetch dt.entity.host | expand t=tags | summarize count(), by:{t} | sort `count()` desc | limit 20'
dtctl query 'fetch dt.entity.service | fieldsAdd n=arraySize(tags) | summarize svcs=count(), tagged=countIf(n>0)'
```

**Gotcha**: don't assume "no tags" from the auto-tagging rule count - check entity tags directly.
A prior review reported zero tags on a tenant where every host carried one.

Naming, capacity, Infra-only names:

```bash
dtctl query 'fetch dt.entity.host | summarize total=count(), ipnamed=countIf(startsWith(entity.name, "ip-"))'
dtctl query 'fetch dt.entity.host | summarize n=count(), by:{hostGroupName}'
dtctl query 'fetch dt.entity.host | filter monitoringMode == "INFRASTRUCTURE" | fields entity.name, tags'
dtctl query 'fetch dt.entity.service | filter entity.name == "/" or startsWith(entity.name, "localhost") or contains(entity.name, "Tomcat/localhost") or startsWith(entity.name, "Requests on 127.0.0.1") | fields entity.name'
dtctl query 'timeseries cpu=avg(dt.host.cpu.usage), by:{dt.entity.host}, from:now()-7d | fieldsAdd a=arrayAvg(cpu), p95=arrayPercentile(cpu, 95) | summarize hosts_ge60=countIf(a >= 60), max_avg=max(a), max_p95=max(p95)'
```

`hosts_infra_names`: summarize the Infra-only list by role (e.g. "6 Module Server SSH hosts"), not raw
IP names. `generic_services` excludes "Requests executed in background threads of ..." - that is a
normal OneAgent pattern. Run the CPU query for the prior week too; `cpu_steady_high` is for
steady load, a jump between weeks belongs in `anomalies`.

Classic cloud metric event activity:

Classic `builtin:cloud.*` / `ext:cloud.*` metrics live in classic metric storage and never appear in
Grail `metric.series` (Grail only has the Gen3-style `cloud.azure.microsoft_*` / `cloud.aws.*` keys), so
a metric.series count for them is always 0 and proves nothing. Check Davis events instead, matching the
event template titles of the enabled cloud metric events:

```bash
dtctl query 'fetch dt.davis.events, from:now()-30d | filter in(event.name, array("<title 1>", "<title 2>")) | summarize n=count(), by:{event.name}'
```

An event in 30 days proves the metric reports. No event means the condition was quiet or the data
stopped, and the two can't be told apart from Grail: report those as unverified, never as dead. To
confirm a quiet one, open its selector in the classic Metrics browser. When the classic cloud
integration was replaced by a Gen3 connection, compare each event
against the Gen3 default alerts in `top_problem_sources` before recommending migration: if Gen3
against the Gen3 AWS default alerts in `top_problem_sources` before recommending migration: if Gen3
already alerts on it, the step is retire, not recreate.

Log attribution and sources:

```bash
dtctl query 'fetch logs, from:now()-24h | summarize total=count(), no_host=countIf(isNull(dt.entity.host)), no_svc=countIf(isNull(dt.entity.service)), with_trace=countIf(isNotNull(trace_id))'
dtctl query 'fetch logs, from:now()-24h | summarize n=count(), by:{dt.openpipeline.source, dt.system.bucket} | sort n desc'
```

`log_unattributed_pct` = no_svc / total. `log_external_pct` = share from a cloud forwarder source
(`/api/v2/logs/ingest/aws_firehose`, Azure Event Hub, etc.); set `log_external_source` to its plain
name. **Duplication rule**: when `log_external_pct` >= 50, the deck never recommends "enable OneAgent
logs" for those workloads - that would store every line twice. Extension sources
(`extension:com.dynatrace.extension.*`) are database-monitoring logs, not application logs.

Cloud instances without OneAgent (AWS shown):

```bash
dtctl query 'smartscapeNodes "AWS_EC2_INSTANCE" | summarize n=count(), by:{aws.state}'
dtctl query 'smartscapeNodes "AWS_EC2_INSTANCE" | filter aws.state == "running" | lookup [smartscapeNodes "HOST" | fields aws.resource.id, hid=id], sourceField:aws.resource.id, lookupField:aws.resource.id | summarize running=count(), without=countIf(isNull(lookup.hid)), names=collectDistinct(if(isNull(lookup.hid), name), maxLength:10)'
```

Maps to `cloud_hosts_running`, `cloud_hosts_without_oneagent`, `cloud_hosts_without_oneagent_names`.
Also check the top services by volume - a large "Requests to unmonitored hosts" service is direct
evidence of the gap (`unmonitored_requests_week`).

---

## GEN2 / GEN3 LENS (feeds platform_matrix and the Upgrade tier)

Run the upgrade-readiness collector once and read its sections:

```bash
PYTHONUTF8=1 uv run --python 3.11 python -X utf8 ~/.claude/skills/dt-upgrade-readiness/scripts/collect.py \
  --context "<ctx>" --workers 1 > readiness.json
```

`PYTHONUTF8=1` is required on Windows (the checks contain emoji; cp1252 crashes the collector).
Build one `platform_matrix` row per capability area. Areas and where the evidence comes from:

| Area | Gen2 evidence | Gen3 evidence |
|---|---|---|
| Cloud monitoring | readiness "Classic cloud integrations" (credentials, API calls) | `cloud.aws.*`/Azure/GCP metrics in `metric.series`; Gen3 alert names in problems |
| Log storage | readiness "Log Classic" tenant state | Logs on Grail % |
| Log processing | readiness "OpenPipeline adoption" (classic pipeline records) | OpenPipeline record share |
| Metric events | `anomaly-detection.metric-events` (enabled count, selector type) | `davis.anomaly-detectors` |
| Problem notifications | `problem.notifications` + alerting profiles | `dtctl get workflows` |
| Management zones | `management-zones` | custom segments + IAM policies |
| SLOs | `monitoring.slo` | `dtctl get slos` |
| Real User Monitoring | readiness "Frontends to migrate" | frontends on Grail, `user.events` count |
| Dashboards | readiness "Deprecated classic dashboards" | `dtctl get dashboards` |
| Access control | readiness "Classic RBAC roles" | IAM policies |
| OneAgent / service detection | readiness SDv1 rules, OneAgent host readiness | - |
| Synthetic monitoring | readiness "Synthetic monitoring" | HTTP/browser monitor entities |

Row status: `Gen3` (only Gen3 in use - shown on the platform slide, improvements come from other
findings), `Gen2` (only classic - gets an Upgrade slide), `Both` (both running - gets a
**Consolidate** slide). Set `duplicate: true` when part of the classic config is already covered by a
Gen3 equivalent. Every Gen2/Both row must carry `duplication_check`: the sentence that explains why
the step will not leave two copies running (disable the classic channel when the workflow goes live,
delete the classic SLO once Gen3 matches, retire alerts Gen3 already covers, and so on). If you
cannot write that sentence, the row should not recommend an upgrade.

---

## Data Collection Checklist

### Coverage / Cloud / VMware / Anomaly (primary)
- [ ] hosts_total, hosts_fullstack, hosts_infra (int) - via the OneAgent coverage join
- [ ] oneagent_fullstack_pct (int, 0-100)
- [ ] pg_with_logs_pct (int, 0-100) - via logs-by-PG vs total PROCESS nodes
- [ ] log_to_trace_pct (int, 0-100)
- [ ] cloud_integration_live (bool), cloud_hosts_without_oneagent (int), cloud_services_without_logs (int)
- [ ] enablement_date (string, ask SE) - gates how much to trust seasonal-style anomalies
- [ ] vmware_hosts (int) - from the distinct dt.entity.hypervisor count (metric probe)
- [ ] vmware_ext_present (bool) - from the EXT_*/metric probe
- [ ] vmware_ext_intentional (bool or null) - **only set when vmware_ext_present is false**; ask the operator
- [ ] anomalies (list, can be empty) - one entry per real deviation found, capped ~6

### Config hygiene
- [ ] alerting_profiles_no_rules / alerting_profiles_test / alerting_profiles_orphaned (lists of labels)
- [ ] mz_issues (list of sentences), mz_count, custom_segment_count, classic_slo_count
- [ ] hosts_ip_named, host_groups, hosts_infra_names, generic_services, hosts_cpu_ge60 / cpu_max_avg / cpu_max_p95
- [ ] log_unattributed_pct, log_external_pct, log_external_source, log_sources, log_retention_days
- [ ] cloud_hosts_running, cloud_hosts_without_oneagent_names, unmonitored_requests_week
- [ ] db_extensions_present (list) - suppresses database_extensions
- [ ] top_problem_sources (list of [name, count])

### Gen2 / Gen3
- [ ] platform_matrix (list of rows, see GEN2 / GEN3 LENS)

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
