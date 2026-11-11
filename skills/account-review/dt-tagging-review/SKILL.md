---
name: dt-tagging-review
description: >
  Review how a Dynatrace tenant is tagged and produce a shareable executive one-page
  HTML overview with a gap analysis. Profiles the three tag layers (native host groups
  and K8s cluster names, legacy CMDB free-text tags, cloud auto-tags), finds the team
  that tags best (environment + region split, dedicated segments), and surfaces naming
  and coverage gaps (ungrouped hosts, no ownership/cost-center tag, inconsistent
  delimiters/case/spelling, fragmented non-prod values, duplicate key schemes). Read-only
  via dtctl. Triggers: "tagging review", "tagging overview", "tag gap analysis", "how is
  this tenant tagged", "tagging governance", "segment out team X", "which teams have good
  tagging", "tag hygiene", "host group coverage".
---

# Dynatrace Tenant Tagging Review

Profile how a tenant is tagged, name the gaps, and hand the account team a one-page
executive HTML overview they can share out.

**This skill is read-only.** It queries tags and topology; it never creates, edits, or
deletes a tag, host group, management zone, or segment. Load `dtctl` first (or alongside)
for auth/context setup and DQL conventions this skill assumes.

The output answers three questions an account team actually asks:
1. How is this tenant tagged today, across all sources?
2. Can we segment out (or focus on) a given team/product?
3. Which teams tag well, and where are the gaps?

## Prerequisites

```bash
dtctl config current-context                 # confirm you're on the right tenant
dtctl auth status --plain                    # context + token live
dtctl query 'smartscapeNodes "HOST" | limit 1' -o json --plain   # smoke test
dtctl inventory                              # entity census + existing Segments (used below)
```

If the user names a tenant, switch first: `dtctl config use-context <name>`.

## Why two different data sources

- **Live host group / cluster / namespace facts** come from `smartscapeNodes` — current
  Smartscape state, authoritative for counts. Use these for anything you report as a number.
- **Free-text tag values** come from `fetch dt.entity.host` — an event-lookback view. Good
  for discovering *what tag keys and values exist*, but its counts are inflated by host
  churn (containers counted as hosts). Never present a `fetch dt.entity.host` count as a
  host total; use it only to enumerate the tag taxonomy.

## Step 1 — Profile the three tag layers

Run these. They are tenant-agnostic.

**A. Tag taxonomy (what keys/values exist, top by volume):**
```
fetch dt.entity.host, from:now()-24h | fieldsAdd tag=tags | expand tag
| summarize count(), by:{tag} | sort `count()` desc | limit 40
```
Read the output into the three layers:
- **Native** — not in `tags` here; pulled in Step 2. The cleanest layer.
- **Legacy CMDB free-text** — `Environment:`, `SiteID:`, `Application:`, `Location:`,
  `assignment_group:`, `CMDBCI:`, `Host OS:`, `urgency:`, `impact:`, etc.
- **Cloud auto-tags** — `[Azure]aks-managed-*`, `[AWS]`, `[GCP]` prefixes. High volume,
  zero ownership meaning. Report as noise to ignore for governance.

**B. Application/team tag spread (candidate teams):**
```
fetch dt.entity.host, from:now()-24h | fieldsAdd tag=tags | expand tag
| filter contains(tag, "Application:")
| parse tag, "LD:\"Application:\" LD:app"
| summarize count(), by:{app} | sort `count()` desc | limit 30
```

## Step 2 — Native host groups (the authoritative layer)

```
smartscapeNodes "HOST" | summarize count(), by:{dt.host_group.id} | sort `count()` desc | limit 50
```

**Unassigned coverage gap** — the single most important number:
```
smartscapeNodes "HOST"
| fieldsAdd hg=if(isNull(dt.host_group.id), "<null>", else:dt.host_group.id)
| fieldsAdd bucket=if(in(hg, array("<null>","TBD","None","To Be Determined")), "UNASSIGNED", else:"assigned")
| summarize c=count(), by:{bucket}
```
Report `UNASSIGNED / (UNASSIGNED+assigned)` as a percentage. Anything above ~10% is a
HIGH-severity gap — those hosts are invisible to group-based scoping, alerting, and chargeback.
(Adjust the sentinel list if the tenant uses other placeholders like `default`, `unassigned`.)

## Step 3 — Kubernetes clusters & namespaces

```
smartscapeNodes "K8S_NAMESPACE" | summarize count(), by:{k8s.cluster.name} | sort `count()` desc
```
Cluster names usually encode the real ownership and discipline (env + region), e.g.
`aks-<product>-<role>-<env>-<region>-NN`. Group clusters by product prefix to find who owns
the biggest K8s footprint and who splits by environment/region.

## Step 4 — Detect the gaps (naming & pattern analysis)

Score each of these; they map 1:1 to the report's gap rows.

1. **Ungrouped hosts** (Step 2) — HIGH if >10%.
2. **No ownership / cost-center tag** — scan the taxonomy (Step 1A) for a *consistent* key
   like `owner`, `cost-center`, `team`, `business-unit`. `assignment_group`/`CMDBCI` present
   on only some hosts does **not** count. Absence = HIGH.
3. **No naming standard** — inspect host-group names (Step 2) for mixed delimiters
   (`_` vs `-`), mixed case (`_Prod` vs `_Qa` vs `_PROD`), and spelling variants
   (`Datacenter` vs `Datacentre`). Two or more divergences = MED.
4. **Fragmented non-prod values** — count distinct non-production `Environment:` values:
   ```
   fetch dt.entity.host, from:now()-24h | fieldsAdd tag=tags | expand tag
   | filter startsWith(tag, "Environment:")
   | parse tag, "LD:\"Environment:\" LD:e"
   | summarize count(), by:{e} | sort `count()` desc
   ```
   More than one of {QA, DEV, Non-Prod, SIT, Staging, Test} in use = MED.
5. **Duplicate key schemes** — a parallel bracket-prefixed management-zone tag set that
   duplicates plain keys:
   ```
   fetch dt.entity.host, from:now()-24h | fieldsAdd tag=tags | expand tag
   | fieldsAdd dup=if(startsWith(tag, "[Environment]"), "bracketEnv", else:"plain")
   | summarize count(), by:{dup}
   ```
   Any non-trivial `bracketEnv` count = MED (two tags for one concept). Generalize the
   `[Environment]` prefix to whatever bracket prefix the tenant uses.

## Step 5 — Find the model team

The team to hold up as the standard is the one that:
- splits host groups and/or clusters by **both environment and region**, and
- already has **dedicated Segments** built for it.

List segments from `dtctl inventory` (the `segments` array) — purpose-built team segments
(not the generic `aws.account.id` / `k8s.namespace.name` ready-made ones) reveal who has
invested in tagging. Cross-reference against the host-group and cluster prefixes. Name the
runners-up too: teams with the same cluster-naming discipline but no segments yet — they're
the natural next candidates.

To show a team is isolatable, confirm a clean filter exists, e.g.
`in(dt.host_group.id, array("BLC_PROD", ...))` or
`startsWith(k8s.cluster.name, "aks-<product>")`.

## Step 6 — Generate the report

Fill [`assets/report-template.html`](assets/report-template.html) — a self-contained,
theme-aware (light/dark) HTML one-pager; the only external dependency is Google Fonts, with
system fallbacks. Replace every `{{...}}` placeholder and follow the `<!-- REPEAT -->`
comments to add/remove tile, gap, and layer rows to match what you found. Keep it to one
page; lead with the one-sentence verdict and the four headline tiles.

Write the finished file to the user's working directory (not the skill folder), named
`<tenant>-tagging-overview.html`, and give them the path. Tell them it's a standalone file
they can open, email, or host anywhere.

Do **not** embed the tenant URL, token, or any host/IP detail in the report — it's meant to
be shared outside the team.

## Quick check

`assets/selftest.sh` runs the six queries against the current context and asserts each
returns rows (non-empty, `ok:true`). Run it after changing any DQL in this skill:
```bash
bash assets/selftest.sh
```
