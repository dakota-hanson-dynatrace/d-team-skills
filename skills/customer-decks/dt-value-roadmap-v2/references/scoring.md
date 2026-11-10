# Opportunity scoring and deliverable structure

Read this only when changing priorities, editing the opportunity library in `generate_pptx.py`, or
explaining why a finding did or didn't fire. Not needed for a normal run.

## Tiers and ordering

Findings sort **Coverage → Anomaly → Config Fix → Upgrade → Start Here → High Value → Phase 2**, then
`top_priorities` (SE pins) move to the front. Each finding carries `effort`, `gen` (Gen3 / Gen2 / Upgrade / Both), and a `value` line. There is no
cost field: effort and value are the only measures shown to the customer.

**Phase (lift x complexity)** comes from effort: up to 1 hour → Phase 1 Quick Wins
(weeks 1-2); up to 1 day → Phase 2 Core Improvements (weeks 3-6); longer → Phase 3
Strategic (this quarter). High-severity anomalies go to Phase 1. `effort_overrides` changes the phase.

## Library triggers

| Key | Trigger | Tier |
|-----|---------|------|
| `oneagent_coverage` | oneagent_fullstack_pct < 80 OR hosts_infra > 0 | Coverage |
| `log_enablement` | pg_with_logs_pct < 70 OR no logs; "pick one path" branch when log_external_pct >= 50 | Coverage |
| `log_to_trace` | log_to_trace_pct < 50 AND pg_with_logs_pct > 0 | Coverage |
| `log_attribution` | log_records_24h > 0 AND log_unattributed_pct >= 50 | Coverage |
| `cloud_coverage_gaps` | cloud_integration_live AND cloud hosts without OneAgent | Coverage |
| `vmware_coverage` / `vmware_data_gap` | VMware present / unexpectedly absent (mutually exclusive) | Coverage / Anomaly |
| *(one per `anomalies` entry, capped at 6)* | always | Anomaly |
| `alerting_profiles_broken` | any no-rules / test / orphaned profile | Config Fix |
| `mz_issues` | any MZ issue | Config Fix |
| *(one per Gen2/Both `platform_matrix` row)* | always | Upgrade |
| *(one per `custom_findings` entry)* | always | its `tier` |
| `alert_tuning` | problems_per_day (7-day average) > 200 | Start Here |
| `slos` | slo_count == 0 | High Value |
| `workflows` | workflow_count == 0 | High Value |
| `database_extensions` | db_service_pct > 40 AND no extensions present | High Value |
| `synthetic_absent` | synthetic_monitors == 0 | High Value |
| `rum_enablement` | rum_apps_classic > 0 AND NOT grail_rum_active | Phase 2 |
| `synthetic_cleanup` | synthetic_monitors > 5 AND rum_apps_classic == 0 | Phase 2 |
| `host_naming` | >= 50% of hosts named by IP | Phase 2 |
| `generic_service_names` | generic_services not empty | Phase 2 |
| `cpu_steady_high` | hosts_cpu_ge60 > 0 (ephemeral hosts excluded by collect.py) | Phase 2 |
| `retention_review` | log_retention_days <= 35 AND NOT retention_confirmed | Phase 2 |
| `tagging_strategy` | highlight_tagging == true (manual) | Phase 2 |

Set `retention_confirmed: true` when custom buckets show retention was already decided.

## Deliverable structure

**Report** (`generate_report.py`): Summary → Environment Snapshot → Platform Position (Gen2/Gen3
table) → Resolved Since the Last Review → Findings (effort, effort level, platform, phase,
what we found, recommendation, value, duplication check) → Phased Implementation Plan → Effort and Value Breakdown →
Scope and Data Notes.

**Deck** (`generate_pptx.py`): Cover → Executive Overview → Current State at a Glance → Platform
Position → Top Priorities → Where to Start (first finding in detail) → Effort and Phased Plan (one slide when the effort and phase groupings hold the same findings, otherwise Deliverables by Effort, then Phased
Plan) → Additional Monitoring Opportunities (only when there are 4 or more extension opportunities; the report always lists them) → Thank you. `--detail` appends one slide per finding. Findings group by effort (Low <=1 hr,
Medium <=1 day, High longer) and badges show effort. Neither deliverable mentions cost.

**Look and feel** follows the Observability Gap Analysis reference deck: dark artwork cover
(`assets/cover_art.png`), white content slides, navy 26pt title with grey subtitle, Arial, white cards
with blue / purple / magenta accent bars, magenta pill badges, and the grey finding panel (What we
found / Why it matters / Recommended action, footer with effort and phase).

## Improvement roadmap

Each run's merged data is saved to `benchmarks/<tenant-id>.json`. With 10+ saved, add peer
comparisons via a `--compare` flag, then a 0-100 maturity score per category. Re-runs can diff
against the saved file to fill `resolved` automatically.
