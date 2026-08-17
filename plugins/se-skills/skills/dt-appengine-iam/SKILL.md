---
name: dt-appengine-iam
description: Explains how permissions actually work for Dynatrace custom AppEngine apps (built with dt-app, deployed via app.config.json scopes) and how to diagnose the specific failure where a Grail query inside the app silently returns 0 records instead of an error. Load this whenever working on a Dynatrace custom app — dt-app dev/build/deploy, app.config.json, @dynatrace-sdk/client-query, @dynatrace-sdk/react-hooks (useDql) — and a query touches Grail (timeseries/metrics, logs, spans, events, entities, smartscape). Especially load it when a custom app shows no data / empty results for a query that works fine in a Notebook, via dtctl, or in another installed app — that exact symptom has a specific, non-obvious cause covered here. Also load it BEFORE reaching for IAM policies, "app service users," or per-app identity concepts to explain a custom-app permission gap — that mental model is wrong for this product and this skill explains the real one. Do not use for general DQL syntax or dtctl CLI usage outside a custom-app context — see the dtctl and dt-dql-essentials skills for that.
---

# Dynatrace AppEngine permissions

Findings below come from a real, fully-diagnosed debugging session, not from documentation-reading. They correct a wrong mental model that a general-purpose Dynatrace docs assistant confidently asserted — so trust this over generic Dynatrace IAM answers when the two disagree on how custom apps get their Grail access.

Scope of confirmation: this covers **browser/UI-driven Grail queries** — `useDql` and `queryExecutionClient` called from an app's frontend code. Server-side App Functions execute under a different mechanism that wasn't tested here.

## The mental model: who is actually querying Grail

A custom AppEngine app does **not** have its own separate identity for UI-driven Grail queries. There is no `app-<app-id>` service user to find or grant permissions to — checking the Identity & access management → Service users list for one will come up empty, no matter how plausible the name sounds.

Instead: **the app's Grail queries run as the logged-in viewing user, with access narrowed to the intersection of that user's IAM policies and the scopes the app declares in `app.config.json`.**

```
effective access = user's IAM policies ∩ app's declared scopes
```

This is why the same query can return real data in a Notebook (full user policies, no scope narrowing) and 0 records inside the app (narrowed to whatever scopes the app happened to declare) — even though it's the exact same person, in the exact same environment, at the exact same moment.

## Recognize this failure: the silent 0-records signature

The tell-tale pattern:
- A `timeseries`/metrics (or logs/spans/events) query returns **0 records** in the app.
- The query does **not** throw, fail, or show any error in the UI — it reports success.
- The *same* query works fine via dtctl, in a Notebook, or in a different installed app.
- Meanwhile, entity (`fetch dt.entity.host`) or Smartscape (`smartscapeNodes`/`smartscapeEdges`) queries in the *same* app work fine and return real data.

That last point is the key diagnostic signal. Entities and Smartscape are **not** bucket-partitioned Grail tables, so they only need their own read scope. Metrics, logs, spans, and events **are** bucket-partitioned — querying them requires resolving which bucket holds the data, which needs one more scope than people expect (next section). If topology/entity queries work but metric/log queries silently come back empty, suspect this before anything else.

## Root cause: bucket-partitioned tables need `storage:buckets:read` too

Metrics, logs, spans, and events live in named Grail buckets (e.g. `default_metrics`, `dt_system_metrics`). A custom app querying any of these tables needs **`storage:buckets:read`** in its declared scopes, *in addition to* the table-specific scope (`storage:metrics:read`, `storage:logs:read`, etc). Without it, the app can't resolve which buckets to read from — but Grail doesn't hard-fail the query over this. It returns:

- `state: "SUCCEEDED"`
- `records: []`
- `scannedBytes: 0`
- a `WARNING`-severity notification in the response metadata: `notificationType: "MISSING_BUCKET_PERMISSIONS"`, message like `"No bucket permissions for table metrics."`

Nothing throws. Nothing looks like a permission error unless you go looking in the metadata. This is exactly why it gets misdiagnosed as "no data in this timeframe" or a DQL syntax problem — the failure is silent by design, and the fix (one missing scope) is nowhere near where the symptom shows up (an empty chart).

## Catch it in code: read the Grail warning, don't just check for thrown errors

If you're calling `queryExecutionClient` directly (or wrapping `useDql`), inspect `result.metadata.grail.notifications` whenever a query comes back empty:

```ts
const resp = await queryExecutionClient.queryExecute({
  body: { query, requestTimeoutMilliseconds: 30000 },
});
// ... poll to completion (see the requestToken gotcha below) ...

const records = resp.result?.records ?? [];
if (records.length === 0) {
  const warning = resp.result?.metadata?.grail?.notifications
    ?.find(n => n.severity === 'WARNING');
  if (warning) throw new Error(warning.message); // surfaces "No bucket permissions for table metrics."
}
```

Only check for the warning **when records are empty** — don't throw on any WARNING unconditionally. Grail attaches plenty of benign warnings (gap-filling notices, sampling notes) to queries that returned perfectly good data, and treating every warning as fatal will discard real results and produce a false permission error.

## Find the exact missing scope: diff against a working app

Don't reason about this abstractly or trust a generic answer about which scope is missing — check what's actually installed and working. If another custom app in the same environment successfully queries the same kind of Grail table, pull its installed manifest and diff scopes:

```bash
dtctl describe app <installed-app-id> -o json --plain
```

This returns the manifest actually running in the environment (`.manifest.scopes`), which is ground truth — more reliable than reasoning from docs, and faster than guessing scope names one at a time. A working app's scope list for a given table is the exact recipe you need.

## A lookalike bug: `QueryPollResponse` has no `requestToken`

If you're driving `queryExecutionClient` directly instead of using `useDql`, there's a separate bug that produces an *identical* symptom (query looks like it succeeded, returns 0/incomplete records) and is easy to mistake for the permissions issue above:

```ts
// WRONG — QueryPollResponse has no requestToken field.
// After the first reassignment, resp.requestToken is undefined,
// so the loop condition fails and polling stops after exactly one iteration —
// even if the query was still RUNNING.
let resp = await queryExecutionClient.queryExecute({ body: { query } });
while (resp.state === 'RUNNING' && resp.requestToken) {
  resp = await queryExecutionClient.queryPoll({ requestToken: resp.requestToken });
}
```

```ts
// RIGHT — capture the token once from the initial queryExecute response,
// and keep reusing that same token for every subsequent poll.
const start = await queryExecutionClient.queryExecute({ body: { query } });
let resp = start;
if (start.state === 'RUNNING' && start.requestToken) {
  const token = start.requestToken;
  do {
    resp = await queryExecutionClient.queryPoll({ requestToken: token });
  } while (resp.state === 'RUNNING');
}
```

Rule out this bug first if the code path uses `queryExecutionClient` directly — it's a pure code fix, not a permissions problem, and fixing scopes won't help if this is what's actually happening.

## Fix recipe

Once you've confirmed it's the bucket-permissions issue (via the metadata warning, or by comparing against a working app's manifest):

1. Add the missing scope to `app.config.json`:
   ```json
   { "name": "storage:buckets:read", "comment": "Resolve Grail metric/log/span/event buckets — required alongside the table-specific read scope for bucket-partitioned tables" }
   ```
2. Bump the app's `version` in `app.config.json` — redeploying the same version with different content fails on a checksum mismatch.
3. Redeploy: `dt-app deploy` (or `npm run deploy`).
4. Reload the deployed app. Dynatrace may prompt to re-approve the app's updated permission scopes on first load after a scope change — that's expected; approve it (as an admin) rather than treating it as an error to work around.

## What NOT to do

- Don't go looking for or try to create an `app-<app-id>` service user to bind an IAM policy to. It doesn't exist for UI-driven queries, and time spent searching for it (or asking a docs assistant, which may confidently invent one) is time not spent on the actual fix.
- Don't grant more IAM policy to the *viewing user* to fix this. If the user already has broad Grail read access (common for admins) and the app still returns 0 records, the user isn't the bottleneck — the app's declared scopes are.
- Don't fully trust a permissions symptom reproduced only against the local dev server (`dt-app dev`). The dev server authenticates through a separate, reduced-permission OAuth client (`dt0s08.dt-app-local`) with its own cached token, distinct from the actually-deployed app's runtime. Confirm any permission fix against the deployed app, not just dev.
