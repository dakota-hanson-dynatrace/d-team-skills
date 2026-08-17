# Dynatrace Gen2 → Gen3 Upgrade Readiness

Diagnose a tenant's readiness to migrate off Classic (Gen2) onto the latest
Dynatrace (Gen3), and tell the customer exactly what to change first for the
biggest impact.

This skill runs the upgrade-readiness checks **directly against the tenant via
`dtctl`** — each check's DQL and JS is bundled with the skill in
`references/readiness-checks.json` and executed against Grail, settings, and
platform APIs. No dashboard is fetched or required.

## 0. Prerequisites & one-time setup

Before assessing, make sure the tooling is in place. Run these checks; if all
pass, skip straight to step 1. If anything is missing, walk the customer through
setup — **detect their OS first** and use the matching commands. Run one step at
a time, show the command, and confirm before installing.

```bash
dtctl version        # is dtctl installed?
dtctl doctor         # config, connectivity, auth health
dtctl ctx            # is a context authenticated?
```

Detect OS: `uname -s` returns `Darwin`/`Linux`; on Windows the shell is
PowerShell (`$PSVersionTable`) or `ver` shows Windows. Then:

**A. Install dtctl** (if `dtctl version` fails):
- macOS / Linux: `brew install dynatrace-oss/tap/dtctl`
- Windows (PowerShell) — download, review, then run:
  `irm https://raw.githubusercontent.com/dynatrace-oss/dtctl/main/install.ps1 -OutFile dtctl-install.ps1` then `.\dtctl-install.ps1`
- Other methods (Linux without Homebrew, binaries): the [dtctl install guide](https://github.com/dynatrace-oss/dtctl#installation).

**B. Install the Dynatrace AI skills** (dynatrace-for-ai — DQL/dtctl helpers this
skill pairs with). Cross-platform, needs Node/npm:
```bash
npx skills add dynatrace/dynatrace-for-ai
```
Alternative (Claude Code plugin): `claude plugin marketplace add dynatrace/dynatrace-for-ai` then `claude plugin install dynatrace@dynatrace-for-ai`.

**C. Authenticate a context** (if `dtctl ctx` shows none, or `dtctl doctor`
reports auth issues). Ask the customer for their environment URL, then:
```bash
dtctl auth login --context <name> --environment "https://<env>.apps.dynatrace.com"
dtctl doctor        # confirm green
```
On headless boxes, WSL, or containers (no OS keyring), export
`DTCTL_TOKEN_STORAGE=file` before logging in, or use API-token auth
(`dtctl config set-credentials`).

**D. Confirm the tenant is reachable:**
```bash
dtctl query "fetch dt.entity.host | limit 1" -o json --plain | head -c 200
```
Non-empty JSON (or an empty result set) → the tenant is queryable and you're
ready. An auth/permission error → revisit step C.

Everything green → proceed. See also the repo `README.md` for the fresh-machine
bootstrap one-liner.

## 1. Pick the target tenant — honor the context the user gave you

**If the user named a context/tenant, that is the target. You MUST pass it as
`--context <name>` to `collect.py` and to every `dtctl` command. Never fall back
to, or silently use, the active context when the user specified one** — running
against the wrong tenant is a serious error.

First verify the named context exists:

```bash
dtctl ctx            # list all contexts
```

- **Name is in the list** → use `--context <name>` everywhere from here on.
- **Name is NOT in the list** → stop and tell the user; show the available
  contexts and ask which to use (or how to create it with `dtctl ctx set`).
  Do **not** proceed against the active context as a guess.
- **User named no context** → only then use the active one, and **state which
  tenant you're assessing** (`dtctl ctx current`) and get confirmation before
  running.

If they haven't set up a context yet, point them to `dtctl ctx set <name>
--environment https://<env>.apps.dynatrace.com` (the `dtctl` skill covers auth).

## 2. Run the readiness checks against the tenant

```bash
python3 scripts/collect.py --context <name>   # ALWAYS pass the context the user named
```

Omit `--context` only when the user named none (step 1). The collector echoes
the context it's running against on the first line of its output — check it
matches the intended tenant.

(Path is relative to this skill directory.) It loads the bundled check
definitions (`references/readiness-checks.json`) and runs every check against
the tenant — DQL checks via `dtctl query`, code checks via `dtctl exec function`
— then prints one consolidated JSON to stdout. Takes ~1 minute. Redirect it to a
file and read that file:

```bash
python3 scripts/collect.py --context <name> > /tmp/readiness.json
```

Output shape:

```json
{
  "context": "...", "generated": "...", "check_count": 90,
  "upgrade_guide": "https://docs.dynatrace.com/docs/shortlink/upgrade-latest-dynatrace",
  "scope_gaps": ["fleet-management:activegates:read", ...],
  "sections": [
    { "section": "### Log Classic",
      "doc_links": ["https://docs.dynatrace.com/..."],
      "checks": [
        { "id": "227", "title": "Tenant state", "type": "code|data",
          "description": "<🟢/🟡/🔴 rules for THIS check>",
          "result": <query result>,          // present on success
          "status": "🟢|🟡|🔴|⚪",             // present only if the check self-reports it
          "result_total_rows": 5000,          // present if the result list was capped at 25
          "error": "...", "scopes_needed": [...],  // present on failure
          "skipped": "..." } ] } ]
}
```

## 3. Determine each check's status

For every check, decide 🟢 ready / 🟡 in progress / 🔴 action required / ⚪ n/a:

- If the check has a `status` field, use it.
- Otherwise read its `description` — **each check's description states its own
  🟢/🟡/🔴 rules** — and apply those rules to its `result`. Examples:
  - `description` says "🔴 Log Classic active … 🟢 Upgraded to Logs on Grail" and
    result is `🟢 Upgraded to Logs on Grail` → 🟢.
  - A count that "should trend toward 0" with `count: 15` → 🔴 (15 remain).
  - A detail table with rows (hosts/services/dashboards to migrate) → 🔴, and
    `result_total_rows` (if present) is the true count, not the capped 25.
  - Empty result / count 0 → 🟢.
- `error` + `scopes_needed`: the check couldn't run — see step 4. Treat as
  **unknown**, never as ready.
- `skipped`: a detail check that relies on a template variable and isn't run in
  standalone mode; the summary checks in that area still run, so don't treat it
  as a blocker.

## 4. Report token scope gaps

`scope_gaps` lists scopes the current token lacks, so some checks couldn't run
(commonly ActiveGate / network-zone / extension-config checks). This is
expected for many customers. Surface it plainly near the top:

> ⚠️ N checks couldn't run — the token is missing: `<scopes>`. Grant these to
> the token/OAuth client and re-run for full coverage. Until then, treat those
> areas as unverified.

Never report an area as ready if its checks failed on scopes.

## 5. Prioritize by impact

The point is not to list 90 checks — it's to tell the customer **what to fix
first**. Rank the 🔴 blockers, then 🟡:

1. **Blockers first (🔴).** These stop or degrade the upgrade.
2. Within blockers, rank by **breadth × effort**:
   - *Breadth*: how much it touches — host/service/dashboard/group counts
     (use `result_total_rows`), tenant-wide settings, security exposure.
   - *Effort*: a tenant-wide toggle (enable new monitoring rules, switch a
     pipeline) is high-impact/low-effort → do first. Rewriting 48 dashboards'
     entity-model DQL is high-effort → schedule, don't block on it.
   - Prefer changes that clear a whole domain at once over per-item slogs.
3. **Then 🟡 (in progress)** — finish what's started (e.g. parallel log ingest,
   partial OpenPipeline migration).
4. 🟢 / ⚪ — mention only as a one-line "already done" reassurance.

Group findings by the check sections (Log Classic, OpenPipeline,
Classic entity model, IAM/RBAC, Service detection & SDv2, Cloud integrations,
Infrastructure/OneAgent/Operator, ActiveGate & network, Synthetic, DEM,
App Security, REST APIs, Classic apps, …).

## 6. Deliver the report

Lead with a verdict and the shortlist, then detail. Suggested shape:

- **Verdict** — one line: ready / nearly ready / significant work, and the
  single biggest lever.
- **Top actions (most impact first)** — a short ranked list. Each: what to
  change, why it blocks the upgrade, scale (counts), effort, and the concrete
  next step (which app/setting, or a Classic link from the check result if one
  is present). Keep it to the handful that matter.
- **By area** — per section: status emoji + one line. Expand only 🔴/🟡 with the
  specifics (which hosts, services, dashboards, groups — pull from the check
  results; note the true total when capped).
- **Couldn't verify** — the scope gaps and skipped checks.

Be concrete and cite the tenant's real numbers. Link to the upgrade guide:
https://docs.dynatrace.com/docs/shortlink/upgrade-latest-dynatrace .

### Classic dashboards → recreate them (selective, built-in)

When the "Classic App usage" section shows Classic dashboards still in use
(checks ~#127/#128, "Deprecated classic dashboards"), include a **"Dashboards to
migrate"** subsection. Do **not** try to convert dashboards yourself — dtctl
can't read Classic dashboards (they're the old config-v1 model, not Gen3
documents), and Dynatrace already ships a converter. Instead:

1. **Rank the still-used ones** from the check result by `Views` (and `Users`) if
   present, else by the sum of the usage-trend array; sort desc. Only
   regularly-used dashboards are worth migrating (~10–15% see real use) — list
   the top ~10–20, not all.
2. For each, surface its **deep link** (the check result already includes a
   full tenant-qualified `https://<env>/ui/apps/dynatrace.classic.dashboards/#dashboard;id=...`
   link — the collector absolutizes it; `environment_url` is also in the output) so the
   customer can open it directly.
3. Give the **recreation steps** (Dynatrace's built-in one-click converter,
   which recreates the dashboard in the new Dashboards app and keeps the
   original):
   - Open the dashboard in Dashboards Classic → `>` menu → **Upgrade** (or `>` →
     Upgrade from the open dashboard's top-right).
   - The converter handles Data Explorer, Health, Markdown, Header, Logs &
     Events, Custom charts, and Synthetic tiles. **Unsupported tiles** (USQL,
     Service, Database, World Map) become explanatory markdown and need manual
     rebuild — flag this so they aren't surprised.
   - Enhance the upgraded dashboard with variables/segments afterward.
4. Cite the section's doc link (`upgrade-guide-dashboards` in that section's
   `doc_links`).

This gives them a prioritized recreate-these-first plan without a fragile
custom transpiler. (If a customer explicitly wants generated Gen3 dashboards
rather than the built-in upgrade, Davis CoPilot via `dtctl exec copilot` can
draft one per dashboard — but treat that output as an approximate starting
point that needs review, not a faithful migration.)

## 7. Always generate and present the HTML report

**Every run ends with a self-contained HTML report — this is mandatory, not
optional, and the customer does not have to ask for it.** HTML only (no PDF). It
opens in any browser on any OS.

1. Copy `references/report-template.html` and fill it in with the step-6 content
   (verdict, ranked top actions, per-area remediation cards, "already done").
   Use the template's CSS/classes; keep it self-contained (no external assets).
2. For each 🔴/🟡 area, write the "How to resolve" steps and cite the official
   doc:
   - Use the section's `doc_links` from the collector output — Dynatrace's own
     links. **Do not invent doc URLs.** If a section has no `doc_links`, cite the
     top-level `upgrade_guide`.
   - Ground the steps in the actual doc: **`WebFetch` the doc URL** (for the
     active blockers) and summarize the real procedure. If offline / WebFetch
     unavailable, use the check's own `description` text as the fix and still
     link the doc. Never fabricate steps that aren't in the docs.
3. Save it to a discoverable file in the current working directory, e.g.
   `readiness-report-<tenant>-<YYYY-MM-DD>.html`.
4. **Present it to the customer**: give the file path, and also show the verdict
   + ranked top actions inline in chat so they see the headline immediately
   without opening the file.

Keep the report focused: only 🔴/🟡 areas get full remediation cards; 🟢/⚪ get
the one-line "already done" list. Cite real tenant numbers, not placeholders.

## Notes

- Read-only: the collector only reads. It never changes tenant config.
- Detail lists are capped at 25 rows in the JSON (`result_total_rows` gives the
  real count); for a full list, run that check's DQL directly with `dtctl query`.
- To re-check one area after the customer fixes something, re-run a single
  check's DQL/JS with `dtctl query` / `dtctl exec function` rather than the whole
  collector.
- The check definitions live in `references/readiness-checks.json` (bundled).
  Refresh them there if Dynatrace updates the readiness checks.
