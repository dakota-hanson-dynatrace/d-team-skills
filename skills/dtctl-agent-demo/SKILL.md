---
name: dtctl-agent-demo
description: >
  Handles any dtctl/Dynatrace request against the demo-live context —
  investigating problems, checking error rates or latency, pulling logs,
  running DQL, building a dashboard, or anything else someone would
  normally ask the core dtctl skill to do. No need for the user to say
  "demo" anywhere: querying against demo-live is inherently a demo (it is
  never a real customer's tenant), so this skill silently checks the active
  dtctl context and, whenever it is demo-live, layers presentation-quality
  output on top of the normal answer: a chat-safe agent/human contrast that
  works inside Claude Code or VS Code as-is, plus (only when the presenter
  types the command directly instead of having the agent run it) dtctl's
  native colored live chart. Against any other context it adds nothing and
  defers entirely to plain dtctl behavior. Triggers: the same broad range of Dynatrace/dtctl questions the
  dtctl skill already covers — "show active problems", "error rate for
  <service>", "top hosts by CPU", "query demo-live", "in the demo tenant" —
  plus any explicit "demo dtctl" / "SKO demo" ask. Pairs with, does not
  replace, the core dtctl skill.
---

# dtctl agent demo

## Overview

The thesis: a coding agent talking to Dynatrace through `dtctl` isn't just
"an agent that can call an API" — the CLI itself already renders rich,
colored, live-refreshing terminal output with zero extra tooling, while the
exact same command also has a structured JSON envelope built for agents.
One query, two lenses. That contrast is the demo.

This skill only puts on that showcase framing against the `demo-live`
context. Against anything else it behaves like the plain `dtctl` skill:
confirm the context, respect its safety level, no invented narrative.

**There are two separate presentation tracks — do not conflate them.**
Verified directly, including inside Claude Code's own tool-call mechanism:
even when the underlying `dtctl` subprocess is given a real TTY (e.g. via
`script`), Claude Code's own rendering of that tool's output still shows the
raw escape sequences as literal bracket-text, not color. So this is not
"is a terminal on screen" — it's specifically whether the command was run
*through the agent's tool call* at all. If it was, no color, no matter what.
`FORCE_COLOR=1` fixes dtctl's own silent color-suppression when it isn't
attached to a TTY, but that's a different, narrower problem — it doesn't
change how Claude Code (or VS Code's agent panel) displays a tool result.

1. **Chat-native track** (the normal way this skill runs, inside Claude Code
   or VS Code, no setup): the agent/human contrast is structured JSON vs. a
   clean synthesized answer — table, prose, a rendered chart image. No color
   claim, and none needed; the contrast is real without it.
2. **Terminal-native track** (the actual colored, live-refreshing chart —
   the visual wow): only reachable by the *presenter personally typing the
   command into a real terminal*, bypassing the agent entirely for that one
   beat — even a Claude Code session running inside a real terminal window
   won't show color if Claude runs the command via its own tool call. Tell
   the presenter the exact command to type themselves; don't run it as a
   tool call and expect color. If there's no moment in the presentation
   where the presenter steps outside the agent to type a command directly,
   this track doesn't happen live — use the recorded fallback instead (see
   below).

**No magic words required.** This skill should fire for ordinary Dynatrace
asks ("what's the error rate for checkout", "show me active problems") just
as readily as for an explicit "give me a demo." The context check below is
also the demo-inference step: if the active context happens to be
`demo-live`, treat the request as a demo, full stop — nobody points dtctl at
`demo-live` for real work, so the context itself is the signal, not the
wording of the ask.

## Safety: check the active context first

Before doing anything else:

```bash
dtctl config current-context --plain
```

- If it prints `demo-live` → continue with the full workflow below.
- If it prints anything else → **stop the showcase framing**. Tell the user
  which context is active and ask whether they want to switch
  (`dtctl config use-context demo-live`) or continue against their real
  context. If they continue, drop back to normal `dtctl` skill behavior:
  plain output, respect `describe-context`'s `SafetyLevel`, no `--live`
  theatrics, no assumption that mutation is safe.

Never assume `demo-live` is active just because this skill triggered —
confirm every time.

## Workflow (against `demo-live`)

1. **Warm up.** `dtctl auth status --plain` — confirms token validity and
   shows expiry, which `auth whoami` doesn't. See gotchas below for why this
   is the preferred connectivity check.

2. **Pick a narrative** if the presenter hasn't already: incident
   investigation, an ad-hoc business question, or building an artifact
   (dashboard/notebook). Default to incident investigation if unspecified —
   it's the most universally legible story to a non-technical audience.

3. **The two-lens moment (chat-native track — always do this one).** Run the
   same DQL twice, back to back:

   ```bash
   dtctl --context demo-live query "<DQL>" -A              # what the agent parses: raw JSON envelope
   dtctl --context demo-live query "<DQL>" --no-agent       # what the audience watches: plain human table
   ```

   `--no-agent` on the second call is required, not decorative — see
   gotchas. Present the first verbatim (or close to it) and the second as
   a clean answer — same question, same answer, two audiences. Say this out
   loud, it's the point, not a side effect. Don't bother with `FORCE_COLOR`
   here: the chat surface won't render the color regardless, so the
   contrast has to come from the structure (JSON vs. answer), not from color.

4. **The live chart beat — the presenter types this themselves, the agent
   does not run it.** Tell the presenter to type this directly into a
   terminal, not as something Claude runs as a tool call:

   ```bash
   dtctl --context demo-live query "timeseries avg(dt.host.cpu.usage), by: {dt.entity.host}" \
     -o chart --live --fullscreen
   ```

   `-o chart` is a real `query` output mode; it renders braille multi-series
   charts with a legend, in real color — but only because a human typed it
   directly into a real terminal. `--live` refreshes on an interval
   (`--interval`, default `1m`). Filter or group first — see gotchas. If
   there's no moment where the presenter steps outside the agent to type a
   command directly, skip this step live and use the recorded fallback GIF
   instead.

5. **Optional advanced beat.** For "how much is this catching at a glance,"
   run the combined category+trend view: `python3 scripts/category_trend.py`.
   It batches two queries (current totals + a 14d trend per category) into
   one threshold-colored table with inline sparklines — the pattern for
   combining queries `-o chart` alone doesn't cover. Its ANSI color codes
   are hardcoded, not TTY-gated, so they survive being piped anywhere — but
   that only matters if something on the receiving end actually renders
   ANSI. Same rule as step 4: the presenter has to run
   `python3 scripts/category_trend.py` themselves, directly, for the color
   to show. If the agent runs it as a tool call, same numbers, no color, for
   the exact reason in the first gotcha below. Read it before running it
   live once; it's short.

6. **Close by revealing the query.** Show the exact DQL/command that
   produced whatever you just showed. Nothing was hidden — anyone in the
   audience could type the same thing.

## Gotchas that break a live demo

- **Running a command as the agent's own tool call never shows color, full
  stop — verified directly inside Claude Code, including with a real TTY
  forced onto the subprocess.** Claude Code's (and almost certainly VS
  Code's agent panel's) own rendering of a tool result shows raw ANSI escape
  sequences as literal bracket-text, not color, regardless of whether the
  underlying process had a TTY. This means the fix is not "open a terminal
  window" — it's "have the presenter type the command themselves," fully
  outside the agent turn. Two things are true and easy to conflate:
  - `dtctl` itself emits zero ANSI color when stdout isn't a real TTY
    (verified: `-o table` piped through a non-tty shell produces no ANSI
    codes at all), and `FORCE_COLOR=1` does fix *that specific* problem
    (`CLICOLOR_FORCE=1` does not — only `FORCE_COLOR` works).
  - But that's irrelevant to the agent-tool-call path: even forcing color
    and forcing a TTY on the subprocess (verified with `script`), Claude
    Code's own display of the tool result still didn't render it. Fixing
    dtctl's color emission does not fix how the host application displays a
    tool result.
  - Net effect: **the colored/live chart only appears if a human types the
    command directly**, never if Claude (or any agent) runs it as a tool
    call — even inside a Claude Code session that itself lives inside a
    real terminal window. Don't promise it will show up in the transcript.
- **dtctl auto-detects agent mode when stdout isn't a TTY** — which is
  exactly the case when a coding agent runs it through its own shell tool.
  Without `--no-agent`, a query run "as if by a human" from inside an agent
  session silently comes back as the same structured JSON envelope as the
  `-A` call, defeating the two-lens contrast (verified: identical output
  with and without `-A` when run non-interactively; adding `--no-agent`
  restores the plain human table). Presenting from a real terminal instead
  of through the agent's own tool calls avoids this entirely; presenting by
  having the agent run the commands requires `--no-agent` on the human-lens
  call.
- **`-o chart` isn't in `--output`'s own `--help` line** (which lists only
  `json|yaml|csv|toon|table|wide`) but it works for `query`. Don't second-guess
  it on stage if `--help` doesn't mention it — it's a real, undocumented
  output mode, confirmed by running it.
- **Prefer `auth status` over `auth whoami` for a live connectivity check.**
  `whoami` needs a broader OAuth scope than plain reads require and can 403
  even when queries succeed, depending on the token's scopes — `auth status`
  reports token validity/expiry without that risk. (`whoami` did succeed
  when this was verified against `demo-live` on 2026-08-25 — the failure
  mode is scope-dependent, not universal. Treat it as a caveat, not a
  guarantee it will fail.)
- **Wide fan-out queries truncate the chart** ("Found N series, showing
  first 10"). Filter or `by:` down to a handful of series before going live,
  or the chart is visual noise instead of a clean story.
- **Conference wifi is not guaranteed.** Capture a `--plain` snapshot ahead
  of time as a fallback (see the `.ans` capture pattern in
  `scripts/category_trend.py`'s companion output) in case the live query
  fails on stage.
- **Do not claim `-o sparkline` or `-o barchart` exist.** They are not in
  `dtctl query --help` as of v0.38.0. If an older doc or skill mentions
  them, verify against the live `--help` before repeating it.

## Recording a GIF — how the colored chart reaches a chat-based presentation

This isn't just a wifi-outage fallback: it's the *only* way the colored,
live-refreshing chart ever appears inside a chat surface at all, since the
chat pane itself cannot render ANSI (see gotchas). A GIF is a video asset,
not live terminal text, so it displays fine anywhere images do. If SKO is
presented through a chat surface rather than a literal terminal on screen,
record the terminal-native beat ahead of time and drop the GIF in as media.

No reusable recording script exists upstream for this — `dynatui`'s README
demo GIF was recorded with [VHS](https://github.com/charmbracelet/vhs)
against the public demo tenant, but the `.tape` file was never committed
(checked both `Dynatrace-Internal/dynatui` and `dynatrace-oss/dtctl`, all
branches). To make your own recording:

```bash
brew install vhs
```

then write a short `.tape` file driving the same commands from the workflow
above (`vhs` docs: https://github.com/charmbracelet/vhs#vhs-command-reference),
and run `vhs demo.tape`.

## Related skills

- `dtctl` — core CLI reference (commands, resources, safety levels, DQL).
- `dynatrace-pptx-skill` — if the demo needs slides in addition to the
  terminal walkthrough.
