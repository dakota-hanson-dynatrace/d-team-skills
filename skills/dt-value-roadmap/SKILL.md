---
name: dt-value-roadmap
description: >
  Produce a Dynatrace branded Value Roadmap PowerPoint for a customer or prospect tenant.
  Gathers live data via dtctl, scores it against the opportunity library, and generates
  a branded deck using the DT template. Use when asked to do an account review,
  gap analysis, health check, or value roadmap for a Dynatrace customer or tenant.
  Triggers: "value roadmap", "gap analysis", "account review", "health check",
  "observability assessment", "deck for customer X", "roadmap deck".
---

# Dynatrace Value Roadmap Skill

Produces a customer-facing PowerPoint that shows what a Dynatrace tenant has already built
and presents 3-8 prioritized next steps to unlock more platform value.

---

## Prerequisites

- dtctl configured and authenticated against the target tenant context
- `/usr/local/bin/python3.11` with `python-pptx` installed
- `dynatrace-pptx-skill/assets/` present at `~/.claude/skills/dynatrace-pptx-skill/assets/`

---

## Workflow

### Step 1 - Gather inputs

Ask the SE (if not already known):
1. Customer name (display name for the deck title)
2. dtctl context name for the tenant
3. Cloud posture: which providers (Azure, AWS, GCP) does the customer use for workloads? Are any already connected in Dynatrace?

### Step 2 - Collect data

Run the queries from `references/queries.md` against the tenant. Build a `data.json` with this schema:

```json
{
  "hosts":                   193,
  "services":                1286,
  "traces_per_day":          "196M",
  "problems_per_week":       11352,
  "problems_per_day":        1622,
  "alerting_profiles":       32,
  "notifications_count":     32,
  "log_records_24h":         0,
  "slo_count":               0,
  "workflow_count":          0,
  "rum_apps_classic":        6,
  "grail_rum_active":        false,
  "synthetic_monitors":      13,
  "db_services":             880,
  "db_service_pct":          68,
  "cloud_azure_connected":   false,
  "cloud_aws_connected":     false,
  "cloud_gcp_connected":     false,
  "cloud_k8s_clusters":      0,
  "cloud_workloads_exist":   true,
  "cloud_providers_in_use":  "Azure"
}
```

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

Report the output path and the active opportunities that fired. Ask the SE if any priorities need to be adjusted before delivering.

---

## Opportunity Scoring

The script evaluates these 8 opportunities in order. Active ones appear as slides, sorted Start Here → High Value → Phase 2.

| Key | Trigger | Default Priority |
|-----|---------|-----------------|
| `alert_tuning` | problems_per_day > 200 | Start Here |
| `log_monitoring` | log_records_24h == 0 AND hosts > 0 | Start Here |
| `cloud_extension` | no provider connected AND cloud_workloads_exist == true | Start Here |
| `slos` | slo_count == 0 | High Value |
| `workflows` | workflow_count == 0 | High Value |
| `database_extensions` | db_service_pct > 40% | High Value |
| `rum_enablement` | rum_apps_classic > 0 AND grail_rum_active == false | Phase 2 |
| `synthetic_cleanup` | synthetic_monitors > 5 AND rum_apps_classic == 0 | Phase 2 |

Note: `synthetic_cleanup` only fires when `rum_apps_classic == 0` because `rum_enablement` already mentions synthetic cleanup in its fix text.

SE can override priority by editing `generate_pptx.py` OPPORTUNITIES list entries before running.

---

## Quick DQL Reference

See `references/queries.md` for full queries with gotchas. Quick commands:

```bash
# Hosts
dtctl dql 'fetch dt.entity.host | summarize count()'

# Services
dtctl dql 'fetch dt.entity.service | summarize count()'

# DB services (run after service count to calculate db_service_pct)
dtctl dql 'fetch dt.entity.service | filter serviceType == "DATABASE_SERVICE" | summarize count()'

# Problems last 7 days
dtctl dql 'fetch events | filter event.category == "PROBLEM" | filter timestamp >= now() - 7d | summarize count()'

# Alerting profiles
dtctl get alerting-profiles

# Log records in last 24h (0 = log monitoring not enabled)
dtctl dql 'fetch logs, from: now() - 24h | limit 1 | summarize count()'

# SLOs
dtctl get slos

# Workflows
dtctl get workflows

# Classic RUM apps
dtctl get settings --schema=builtin:rum.web.app-detection

# Grail RUM active? (returns 0 if not active)
dtctl dql 'fetch user.events, from: now() - 24h | limit 1 | summarize count()'

# Synthetic monitors
dtctl get synthetic-monitors

# Cloud integrations
dtctl get settings --schema=builtin:cloud.azure
dtctl get settings --schema=builtin:cloud.aws
dtctl get settings --schema=builtin:cloud.gcp
```

---

## Deck Structure

Output is always: Cover → Foundation divider → Stats slide → Next Steps divider → N opportunity slides → Roadmap table → Thank you. Total: N + 5 slides.

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
