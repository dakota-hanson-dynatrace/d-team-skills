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

| Skill | Triggers | What it does |
|-------|---------|--------------|
| **dt-app-ui-design** | "build a custom app", "AppEngine UI", "strato components" | Design patterns and component choices for Dynatrace AppEngine custom apps. Covers Strato UI library, layout primitives, DQL data-fetching conventions, and stat tile patterns. |
| **dt-appengine-iam** | "app returns no data", "AppEngine permissions", "Grail access" | Diagnoses the silent 0-records failure when a Grail query inside a custom app returns no data instead of an error. Corrects the wrong mental model about app-level service users and IAM scopes. |
| **dt-dashboard-variables** | "dashboard variable", "multi-select filter", "DQL variable" | Dashboard variable authoring: multi-select query variables, GUID wildcard select-all sentinel, `in(field, array($Var))` filter syntax, cascading variables, and DQL gotchas specific to dashboard tile queries. |
| **dt-upgrade-readiness** | "upgrade readiness", "Gen3 migration", "classic to Grail" | Assesses a tenant's readiness to migrate from Dynatrace Gen2 (Classic) to Gen3. Runs readiness checks via dtctl, produces a self-contained HTML report. |
| **dt-value-roadmap** | "value roadmap", "gap analysis", "account review", "health check" | Generates a branded customer-facing PowerPoint. Collects live data from a tenant via dtctl/DQL, scores it against an opportunity library, and builds a prioritized roadmap deck. |
| **dynatrace-pptx-skill** | "create a presentation", "build a deck", "DT slides" | Builds PowerPoint decks using the official Dynatrace 2026 brand template. Provides color constants, font specs, layout patterns, and python-pptx gotchas. Required by `dt-value-roadmap`. |

---

## Contributing

### Add a new skill

1. Clone the repo and create a branch.

```bash
git clone https://github.com/dynatrace/d-team-skills.git
cd d-team-skills
git checkout -b skill/my-new-skill
```

2. Create your skill directory:

```bash
mkdir -p skills/my-skill-name
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
└── my-skill-name/
    ├── SKILL.md
    ├── references/      <- reference docs, query libraries, API notes
    └── scripts/         <- helper scripts Claude can invoke
```

5. Test it locally before opening a PR:

```bash
# Symlink your WIP skill into ~/.claude/skills/ for live testing
ln -s $(pwd)/skills/my-skill-name ~/.claude/skills/my-skill-name

# Open Claude Code and trigger your skill
# Remove the symlink when done
rm ~/.claude/skills/my-skill-name
```

6. Open a PR. Once merged, teammates get the skill on their next `claude plugin update`.

### Binary assets (images, templates)

If your skill needs binary files (images, Office templates, etc.), you must track them with Git LFS. Add a line to `.gitattributes`:

```
plugins/se-skills/skills/my-skill-name/assets/*.png filter=lfs diff=lfs merge=lfs -text
```

Run `git lfs track` before staging the files. Do not commit binaries without LFS - it bloats the repo for everyone.

### Update an existing skill

Same flow: branch, edit the `SKILL.md` or supporting files, PR. Bump the version in `plugins/se-skills/.claude-plugin/plugin.json` when the change meaningfully affects behavior.

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
│   └── plugin.json            <- plugin metadata and version
├── skills/
│   └── <skill-name>/
│       └── SKILL.md           <- required per skill
├── .gitattributes             <- Git LFS rules for binary assets
└── README.md
```
