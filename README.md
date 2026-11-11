# d-team-skills

Claude Code SE skills — internal Dynatrace SE team plugin marketplace.

Skills in this repo are installed as a Claude Code plugin bundle. Once installed, Claude automatically activates the right skill based on what you're working on.

---

## Quick Install

```bash
claude plugin marketplace add dakota-hanson-dynatrace/d-team-skills
```

That's it. The plugin installs automatically when the marketplace is added. Restart Claude Code and the skills are active.

**To update after new skills are merged:**
```bash
claude plugin marketplace refresh d-team-skills
```

**Prerequisites:** Claude Code CLI and Git LFS (for the PowerPoint assets).

```bash
# Install git-lfs if you don't have it
brew install git-lfs   # macOS
# or: sudo apt install git-lfs  (Ubuntu/Debian)
```

---

## Skill Catalog

Skills are grouped under `skills/<category>/` by general application, so the directory layout itself gives an overview of what's here.

### `custom-apps/` — building Dynatrace AppEngine custom apps

| Skill | Triggers | What it does |
|-------|---------|--------------|
| **dt-app-ui-design** | "build a custom app", "AppEngine UI", "strato components" | Design patterns and component choices for Dynatrace AppEngine custom apps. Covers Strato UI library, layout primitives, DQL data-fetching conventions, and stat tile patterns. |
| **dt-appengine-iam** | "app returns no data", "AppEngine permissions", "Grail access" | Diagnoses the silent 0-records failure when a Grail query inside a custom app returns no data instead of an error. Corrects the wrong mental model about app-level service users and IAM scopes. |

### `dashboards/` — authoring Dynatrace dashboards

| Skill | Triggers | What it does |
|-------|---------|--------------|
| **dt-dashboard-design** | "tile has no color", "color a dashboard tile", "executive dashboard", "sparkline" | Dashboard tile coloring, formatting and visual design. Why `coloring` must nest inside `visualizationSettings`, theme and categorical color palettes, colored section banners, sparklines with trend deltas, `unitsOverrides`, and the DQL gotchas behind wrong-looking tiles. |
| **dt-dashboard-variables** | "dashboard variable", "multi-select filter", "DQL variable" | Dashboard variable authoring: multi-select query variables, GUID wildcard select-all sentinel, `in(field, array($Var))` filter syntax, cascading variables, and DQL gotchas specific to dashboard tile queries. |

### `finops/` — cost and licensing optimization

| Skill | Triggers | What it does |
|-------|---------|--------------|
| **dt-finops-hosts** | "FullStack candidates", "Infra-only downgrade", "FinOps host review" | Finds FullStack-monitored hosts with no deep-monitored workload (zero Smartscape processes) as Infra-only downgrade candidates, with RAM totals and aggregate RAM exposure. Read-only — never changes monitoring mode. |
| **dt-metric-ingest-optimizer** | "metric ingest", "unused metrics", "reduce metric volume", "OpenTelemetry sampling interval", "_bucket histogram", "anomaly detector copies" | Analyzes everything a tenant is billed for under Metrics - Ingest & Process plus the Metric - Query load. Produces a customer-facing Word and Markdown review (findings, remediation steps, phased plan), a findings notebook, and a dashboard comparing any selected window with the same-length window 7 days earlier. Finds unused, rarely used, API-only and detector-only metrics, histogram bucket and OpenTelemetry interval savings, duplicate signals, cost-center gaps and detector copies. Read-only unless the user agrees to create the notebook and dashboard. Runs against one or several tenants. |

### `mainframe/` — mainframe monitoring and positioning

| Skill | Triggers | What it does |
|-------|---------|--------------|
| **dt-mainframe-support** | "CICS", "ASRA", "S0C7 abend", "zDC", "mainframe log collection" | CICS/IMS architecture (zDC/zRemote stack, PLT/CSD region setup), MQ on z/OS, log ingest setup, and S0Cx abend diagnosis (S0C1/2/4/5/6/7). |
| **dt-mainframe-competitive** | "Dynatrace vs MainView", "OMEGAMON comparison", "STROBE alternative" | Positions Dynatrace OneAgent zDC (application observability) against BMC MainView, IBM OMEGAMON, CA SYSVIEW, and Compuware STROBE (system monitoring) for mainframe monitoring. |

### `migration/` — Gen2 → Gen3 upgrade assessment

| Skill | Triggers | What it does |
|-------|---------|--------------|
| **dt-upgrade-readiness** | "upgrade readiness", "Gen3 migration", "classic to Grail" | Assesses a tenant's readiness to migrate from Dynatrace Gen2 (Classic) to Gen3. Runs readiness checks via dtctl, produces a self-contained HTML report. |

### `account-review/` — tenant assessment deliverables

| Skill | Triggers | What it does |
|-------|----------|--------------|
| **dt-tagging-review** | "tagging review", "tag gap analysis", "how is this tenant tagged", "segment out team X", "which teams tag well" | Profiles a tenant's tagging across all three layers (native host groups/clusters, legacy CMDB free-text tags, cloud auto-tags), finds the team that tags best, and scores naming/coverage gaps (ungrouped hosts, missing ownership tag, inconsistent delimiters/case/spelling, fragmented non-prod values, duplicate key schemes). Produces a self-contained, shareable executive one-page HTML overview. Read-only via dtctl. |

### `customer-decks/` — customer-facing PowerPoint deliverables

| Skill | Triggers | What it does |
|-------|---------|--------------|
| **dt-value-roadmap-v2** | "value roadmap", "gap analysis", "account review", "health check" | Generates a Value Roadmap (Markdown report, Word report, and a short PowerPoint) for a customer or prospect tenant. Collects live data from a tenant via dtctl/DQL, then builds the report and deck in the Observability Gap Analysis look, using effort/value wording only (no cost/price/billing language). Replaces `dt-value-roadmap` (v1). Optionally shells out to `dt-upgrade-readiness` for a readiness digest — see note below. |
| **dynatrace-pptx-skill** | "create a presentation", "build a deck", "DT slides" | Builds PowerPoint decks using the official Dynatrace 2026 brand template. Provides color constants, font specs, layout patterns, and python-pptx gotchas. Fallback only - `dt-value-roadmap-v2` ships its own template. |

> `dt-value-roadmap-v2/collect.py`'s `--readiness` flag shells out to `../../migration/dt-upgrade-readiness/scripts/collect.py` by a path that names the `migration/` category directly, not a sibling-relative path — if `dt-upgrade-readiness` is ever renamed or moved to a different category, update that path too.

### `dev-tools/` — general engineering workflow

| Skill | Triggers | What it does |
|-------|---------|--------------|
| **kubectl-pod-debug** | "kubectl", "exec into a pod", "tail pod logs", "wait for rollout" | Live kubectl debugging idioms: resolve a pod by label then log/exec it (with the readiness/sort-order gotcha fixed), `kubectl wait` instead of hand-rolled sleep-poll loops, and setting a default namespace context. Not for Dynatrace K8s telemetry — see `dt-finops-hosts`-style DQL skills for that. |
| **gh-pr-workflow** | "open a PR", "merge this PR", "self-merge", "gh pr create" | The create → check → merge → confirm `gh` CLI cycle for opening and self-merging a PR end to end, including the mergeable/mergeStateStatus check before merging and the post-merge confirmation habit. |

### `productivity/` — working better with Claude Code itself

| Skill | Triggers | What it does |
|-------|---------|--------------|
| **claude-usage-review** | "review my claude usage", "optimize my claude token usage", "where am I wasting tokens" | Digests your local Claude Code session transcripts (bash+jq, zero model tokens) into skill-candidate and token-reduction suggestions. Designed to run on a weekly schedule via launchd/cron. |

### `sales-ops/` — recurring sales reporting

| Skill | Triggers | What it does |
|-------|---------|--------------|
| **weekly-salesforce-canvas** | "run the weekly principal report", "update the top 10 canvas", "refresh the deal canvas from Salesforce" | Refreshes a Slack canvas's Top 10 deal table against live Salesforce data and produces a delta report of what changed and why. |

---

## Contributing

### Add a new skill

1. Clone the repo and create a branch.

```bash
git clone https://github.com/dynatrace/d-team-skills.git
cd d-team-skills
git checkout -b skill/my-new-skill
```

2. Create your skill directory under the category it belongs to (see the Skill Catalog above for the current categories — add a new category folder only if none of the existing ones fit):

```bash
mkdir -p skills/<category>/my-skill-name
```

3. Write your `SKILL.md`:

```yaml
---
name: my-skill-name
description: >
  One or two sentences describing when Claude should activate this skill.
  Include the natural-language triggers people will use ("when asked to...",
  "use when the user mentions...", etc.).
---

# Skill Title

## Overview
What this skill does and when to use it.

## Workflow
Step-by-step instructions for Claude to follow.
```

4. Add any supporting files alongside `SKILL.md`:

```
skills/
└── <category>/
    └── my-skill-name/
        ├── SKILL.md
        ├── references/      <- reference docs, query libraries, API notes
        └── scripts/         <- helper scripts Claude can invoke
```

If your skill is in a brand-new category, also add that category's path to the `skills` array in `.claude-plugin/plugin.json` — that array is how the plugin loader finds skills nested under a category folder; without an entry there the skill won't be discovered.

5. Test it locally before opening a PR:

```bash
# Symlink your WIP skill into ~/.claude/skills/ for live testing
ln -s $(pwd)/skills/<category>/my-skill-name ~/.claude/skills/<category>/my-skill-name

# Open Claude Code and trigger your skill
# Remove the symlink when done
rm ~/.claude/skills/<category>/my-skill-name
```

6. Open a PR. Once merged, teammates get the skill on their next `claude plugin update`.

### Binary assets (images, templates)

If your skill needs binary files (images, Office templates, etc.), you must track them with Git LFS. Add a line to `.gitattributes`:

```
skills/<category>/my-skill-name/assets/*.png filter=lfs diff=lfs merge=lfs -text
```

Run `git lfs track` before staging the files. Do not commit binaries without LFS - it bloats the repo for everyone.

### Update an existing skill

Same flow: branch, edit the `SKILL.md` or supporting files, PR. Bump the version in `.claude-plugin/plugin.json` when the change meaningfully affects behavior.

---

## Skill Format Reference

### Frontmatter fields

| Field | Required | Description |
|-------|---------|-------------|
| `name` | yes | Kebab-case slug matching the directory name |
| `description` | yes | When Claude activates this skill. Be specific about trigger phrases. |
| `version` | no | Semver string |
| `argument-hint` | no | For user-invoked skills (`/skill-name <arg>`) |
| `allowed-tools` | no | Restrict which tools the skill can use |
| `model` | no | Override the model for this skill |

### Types of skills

**Context-activated** (Claude reads the conversation and decides when to apply it):
The `description` field drives activation. Write it as a trigger statement: "Use this skill when the user asks to create a presentation, mentions DT slides, or says 'build a deck'."

**User-invoked** (slash command `/skill-name`):
Add `argument-hint` to the frontmatter. User types `/skill-name <their input>`; available as `$ARGUMENTS` in the skill body.

---

## Repo Structure

```
d-team-skills/
├── .claude-plugin/
│   ├── marketplace.json       <- Claude marketplace registration
│   └── plugin.json            <- plugin metadata, version, and the `skills` array
│                                  listing each category folder below
├── skills/
│   └── <category>/             <- general application, e.g. dashboards/, finops/, mainframe/
│       └── <skill-name>/
│           └── SKILL.md       <- required per skill
├── .gitattributes             <- Git LFS rules for binary assets
└── README.md
```

Skills are discovered one level under each category folder, not directly under `skills/` — that's why `plugin.json`'s `skills` array must list every category path.
