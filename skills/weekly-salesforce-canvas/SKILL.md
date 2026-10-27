---
name: weekly-salesforce-canvas
description: Runs the weekly principal report — refreshes a Slack canvas's Top 10 deal table against live Salesforce data and produces a delta report of what dropped out / got added and why. Trigger this whenever the user asks to "run the weekly principal report," "update the top 10 canvas," or "refresh the deal canvas from Salesforce," even if they don't name this skill directly.
---

# Weekly Salesforce Canvas Refresh

Refreshes a Slack canvas that tracks a "Top 10" opportunity list (e.g. "NEMA Top 10 H1 FY26")
against the live Salesforce pipeline, then reports what changed and why. Use the `sf`
Salesforce CLI for all Salesforce access — the user has an authenticated org alias already
set up, and `sf` keeps auth tokens inside the CLI instead of exposing them to you. Do not use
a browser or a Salesforce MCP connector for this; if `sf org list` shows no connected org,
tell the user to run `sf org login web` themselves rather than trying to log in for them.

## Inputs you need from the user (ask if missing)

- The Slack canvas URL or ID (canvas ID is the last path segment, e.g. `F0B1YHDDV6J`).
- The Salesforce report ID this canvas is meant to mirror (e.g. `00ORj0000073FxmMAE` from a
  Lightning report URL `.../Report/<ID>/view`).

## Step 1 — Read the current canvas

```
slack_read_canvas(canvas_id)
```

This returns `markdown_content` (the current table + Commit/Most Likely/Best Case groupings)
and `section_id_mapping` (fresh section IDs you'll need for the update in Step 6). Parse out
the old top-10 list: Opportunity name, Opportunity URL (contains the Opportunity Id), account,
director, territory, ACV, stage, forecast category, close date.

## Step 2 — Learn what the Salesforce report actually filters on

```bash
sf api request rest "/services/data/v61.0/analytics/reports/<REPORT_ID>" -o <org-alias> --json
```

`sf` prepends a version-check warning line to stdout — strip the first line before parsing
JSON (`tail -n +2`). The body is nested at `result.body` (it may arrive as a JSON string —
`json.loads` it if so). Read `reportMetadata`: `reportFilters`, `standardDateFilter`,
`groupingsDown`, and `sortBy` tell you the population (fiscal period, geography, territory
picklist values, opportunity type, excluded stages) and how it's ordered.

**Gotcha to check every time:** compare the report's own aggregate ACV column (often a custom
field like `Sales_ACV_Products__c`) against `Opportunity.Amount` for a handful of rows. These
can drift apart badly (seen one week: a custom ACV field sitting at 10-40% of `Amount` across
almost every deal — a data-quality bug, not a real pipeline collapse). The canvas's historical
ACV numbers are almost always `Amount` (TCV), not the report's internal ACV field. If they
diverge, rank by `Amount` and call out the divergence as a data-quality note in your final
report rather than silently trusting the report's own column.

## Step 2b — Verify the filter's population, not just its ACV field

The Step 2 gotcha above catches a bad *value* column. There's a second, separate failure
mode: a bad *population* filter — the report returns numbers for the wrong set of people.
This is easy to miss because the report still runs and still looks plausible.

If the report scopes to an org/team (e.g. "this VP's org") via a geography or territory
picklist rather than by direct ownership, don't trust it at face value. Picklists like this
are often shared across unrelated segments (government, strategic, other regions) and can be
blank or mis-set on individual reps regardless of who they actually report to. Spot-check by
pulling the real manager hierarchy and comparing:

```bash
sf data query -q "SELECT Id, Name FROM User WHERE Name IN ('<RD 1>','<RD 2>',...)" -o <org-alias> --json
sf data query -q "SELECT Id, Name, ManagerId FROM User WHERE ManagerId IN (<RD Ids>)" -o <org-alias> --json
```

Then check both directions: (a) does every open opportunity owned by someone in that
manager tree actually pass the report's filter (false negatives — usually a rep with an
off-list picklist value), and (b) does the filter pull in opportunities owned by people
*outside* that tree (false positives — the picklist is shared with other segments). In one
real case this found a filter that was simultaneously dropping a legitimate rep's entire
pipeline (nonstandard territory value) and leaking 67% unrelated noise from other VPs' orgs.
A subagent is a good way to run this check without burning main-thread context on 800+ rows.

If the filter is broken this way, you have two options: keep re-deriving correct SOQL ad hoc
every run (cheap, no write risk), or fix the saved Salesforce Report itself so future runs
don't need the workaround (more useful long-term, but touches a shared org artifact — confirm
with the user before creating/editing a Report, and see the gotchas below before doing so).
A reliable ownership-based filter uses the report's `OWNER_MANAGER` (Opportunity Owner's
Manager) and `FULL_NAME` (Opportunity Owner) columns, OR'd together via `reportBooleanFilter`
so it also catches deals the RDs own directly — e.g.
`reportFilters: [...,{"column":"OWNER_MANAGER","operator":"equals","value":"RD1,RD2,RD3"},{"column":"FULL_NAME","operator":"equals","value":"RD1,RD2,RD3"}], reportBooleanFilter: "1 AND 2 AND 3 AND (4 OR 5)"`.
Don't reach for Salesforce's native role-hierarchy scope (`scope: "team"` +
`userOrHierarchyFilterId`) expecting it to "just work" — it's the theoretically correct,
zero-maintenance mechanism (auto-includes new hires), but it silently returned 0 rows in a
real org even for a known-good manager, both as an ad-hoc override and as a saved report.
If you try it, verify actual row counts before trusting it; don't assume it's wired up
correctly in every org.

## Step 3 — Re-run the report's filter logic as SOQL, ranked by Amount

Translate `reportFilters` + `standardDateFilter` into a direct query, e.g.:

```bash
sf data query -q "SELECT Id, Name, Account.Name, Owner.Name, Owner.ManagerId, Owner.Manager.Name, <territory field>, Amount, StageName, ForecastCategoryName, CloseDate, IsClosed, IsWon FROM Opportunity WHERE Geography__c = 'NORAM' AND <territory field> IN (...) AND Type IN (...) AND CloseDate = THIS_FISCAL_QUARTER AND Probability > 0 AND StageName NOT IN ('6 - Closed Lost', ...) ORDER BY Amount DESC NULLS LAST LIMIT 15" -o <org-alias> --json
```

SOQL note: it's `StageName NOT IN (...)`, not `NOT StageName IN (...)` — the latter is a
parse error. Pull ~15 rows, not just 10, so you can see who's waiting just outside the cutoff.

Take the top 10 by `Amount` as the new list.

## Step 4 — Diff old vs. new by Opportunity Id

- **Dropped out**: in the old canvas list but not in the new top 10.
- **Added**: in the new top 10 but not in the old canvas list.
- **Reordered**: present in both, just at a different rank — worth one line in the summary,
  not a full writeup.

For every dropped/added opportunity, pull the fields you'll need to explain it. A quick
per-Id lookup covers most cases:

```bash
sf data query -q "SELECT Id, Name, <territory field>, Type, Probability, StageName, CloseDate, Amount FROM Opportunity WHERE Id IN ('<id1>','<id2>',...)" -o <org-alias> --json
```

Common reasons you'll find: a picklist field (like the territory field) got blanked, which
silently drops a record out of the filter even though nothing "changed" from a deal-health
standpoint; a stage regressed or advanced; `CloseDate` slipped to a later quarter; the deal
closed won or moved to a closed/booked stage.

## Step 5 — Pull the "why" for changed deals

```bash
sf data query -q "SELECT OpportunityId, Field, OldValue, NewValue, CreatedDate FROM OpportunityFieldHistory WHERE OpportunityId IN (...) AND Field IN ('Amount','StageName','CloseDate','<custom ACV field>') ORDER BY CreatedDate DESC LIMIT 200" -o <org-alias> --json

sf data query -q "SELECT WhatId, Subject, Description, CreatedDate FROM Task WHERE WhatId IN (...) ORDER BY CreatedDate DESC LIMIT 60" -o <org-alias> --json
```

Field history explains *what* changed and *when*. Tasks tell you whether the deal is being
actively worked (recent emails/calls) or has gone quiet — a deal with its last logged activity
a year old is a different story than one that closed last week. Write one to two sentences of
"why" per changed deal from this evidence; don't guess.

## Step 6 — Update the canvas

Re-read `section_id_mapping` if any time has passed since Step 1 (section IDs go stale after
any edit — never reuse an old mapping). Then, in one `slack_update_canvas` call with multiple
`sections` operations:

1. `replace` the main table section with the new top 10, same column structure as the
   original (Opportunity | Account | Director | Territory | ACV | Stage | Forecast | Close
   Date). Build Opportunity/Account/Director links as
   `https://<lightning-domain>/lightning/r/<Id>/view`. **Escape any literal `|` in an
   Opportunity/Account name as `\|` before inserting it into the table** — Salesforce
   Opportunity names sometimes contain a raw pipe (e.g. `"Cardworks, Inc. | Managed to SaaS
   Upgrade"`), and an unescaped one is read as a column delimiter, silently merging cells and
   dropping the rest of that row (the Close Date column disappears with no error).
2. For each of the Commit / Most Likely / Best Case groupings: `replace` enough existing
   account-link sections to cover the new membership, `delete` any leftover sections if the
   new group has fewer members, and note that if you're asked to add a short summary under
   each account link, put it in the same `replace` call as the link — two lines separated by
   a blank line, link first: `[Account Name](url)\n\n<1-2 sentence summary: ACV, stage, close
   date, one line of why-it's-here-or-changed>`.
3. Leave the title section alone unless the user asks you to change it.

Always share the returned `canvas_url` with the user.

## Step 7 — Report the delta in chat

Give the user a compact report, not the raw query dumps:

- **Data-quality note** (only if Step 2 found one): which field diverged and by how much.
- **Dropped out**: opportunity, old rank/value, what happened (closed won, slipped quarter,
  field blanked, gone stale), sourced from Steps 4-5.
- **Added**: opportunity, value, stage, why it's here now.
- **Reordered / unchanged**: one line, e.g. "MAPFRE, Sentara, Cintas held their spots, just
  reshuffled by ACV."
- A one-line net read on the quarter (e.g. pipeline shrank because two deals closed won while
  smaller early-stage deals backfilled the list).

## Appendix — gotchas when creating/editing the Salesforce Report itself

Only relevant if you go the "fix the saved Report" route from Step 2b. The Analytics REST API
(`/services/data/vNN.0/analytics/reports`) is pickier than the UI and fails with unhelpful
generic errors:

- **`description` has a hard length limit (~255 chars).** Going over it fails report
  creation/update with a generic `{"errorCode":"UNKNOWN_EXCEPTION","message":"invalid
  parameter value"}` — no field name, no length in the error. If create/update fails with that
  exact message and your filters/columns look fine, suspect `description` first (or bisect by
  reverting fields one at a time from a known-working minimal payload).
- **`groupingsDown` overrides `sortBy` for display order.** A `SUMMARY`-format report grouped
  by e.g. `ACCOUNT_NAME` sorts the *groups* by that grouping's own `sortOrder` (alphabetical by
  default), not by the `sortBy` aggregate — `sortBy` only orders rows *within* a group. A flat
  "Top N by Amount" report needs `reportFormat: "TABULAR"` with `groupingsDown: []`.
- **TABULAR format doesn't auto-include the old grouping dimension as a column.** If you drop
  `groupingsDown`, add `ACCOUNT_NAME` / `OPPORTUNITY_NAME` to `detailColumns` explicitly, or
  the report becomes unreadable (owner name with no way to tell which deal is which).
- **`sf api request rest ... --method DELETE` needs a body even though DELETE has no body.**
  `--body ""` fails with `No 'mode' found in 'body' entry`. Use
  `--body @file` where the file contains `{"mode":"raw","raw":""}`.
- **Data can move mid-session.** An actively-worked deal's Amount can change while you're
  mid-refresh (seen: $960K → $1.62M same day, confirmed via `LastModifiedDate`). Re-pull the
  final numbers immediately before writing the canvas rather than reusing an earlier snapshot
  from the same session.
- **A big account with many opportunities can legitimately miss the cutoff.** Don't assume a
  missing well-known account is a filter bug — check whether its open deals in the window are
  just too small (or `Amount = 0`, which sorts last) before concluding something's wrong.
