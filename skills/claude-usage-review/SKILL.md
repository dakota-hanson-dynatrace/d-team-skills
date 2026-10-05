---
name: claude-usage-review
description: Review Claude Code usage across all local sessions to find token-saving opportunities and recurring task patterns worth turning into a skill. Triggers on "review my claude usage", "claude usage review", "optimize my claude token usage", "what skills should I create", "where am I wasting tokens", or when invoked on a schedule as /claude-usage-review.
---

# Claude Code Usage Review

Analyzes all local session transcripts under `~/.claude/projects/` and produces a weekly-cadence
report with (1) concrete skill candidates mined from repeated tool/command patterns and (2) token-
reduction suggestions grounded in real numbers. Never reads raw transcripts directly — they run to
hundreds of MB, which would burn the very tokens this review is trying to save.

## Steps

1. **Run the digest script.** It is pure bash + jq, costs zero tokens, and does the heavy lifting:

   ```
   bash $HOME/.claude/skills/claude-usage-review/analyze.sh
   ```
   For unattended (launchd/cron) runs, add a `Bash(bash <your literal expanded $HOME>/.claude/skills/claude-usage-review/analyze.sh*)`
   rule to `permissions.allow` in your own `~/.claude/settings.json` — the allowlist matches a
   literal string, so it must be your actual expanded home directory, not `~` or `$HOME`.

   This writes `~/.claude/usage-reports/digest-<date>.json` and `.md`. **Read only the `.md` file**
   — it's a few KB, not the source transcripts.

2. **Optional color.** If useful, sample a handful (10-20) of recent `user`-role prompt strings
   (first ~200 chars each) via a bounded jq/grep pass — not a full read — to see *what* the repeated
   Bash commands / tool sequences in the digest were actually for. Skip this if the digest tables
   are already self-explanatory.

3. **Skill candidates.** Look at the digest's "Bash command frequency", "Tool usage frequency", and
   "biggest sessions" tables. For each recurring command cluster or multi-step tool sequence that
   isn't already covered by an existing skill, propose one: a name, 1-2 trigger phrases, and what it
   would encapsulate. Cross-check proposals against the currently installed skills (listed in the
   system reminder at session start) so you don't re-propose something that already exists (e.g.
   don't suggest a "dtctl helper" — that skill exists).

4. **Token-reduction suggestions.** Ground every suggestion in a specific digest number, e.g.:
   - A project/session with a low cache-hit % → context is being re-sent instead of reused; suggest
     fewer/shorter system-prompt-adjacent reloads, or checking what's busting the cache.
   - Sessions in "biggest sessions by output tokens" → candidates for compacting/starting fresh
     sooner, or for delegating sub-tasks to a subagent instead of doing them inline.
   - Heavy repeated `Read`/`cat`/`find` of the same paths → suggests batching or using
     offset/limit instead of re-reading whole files.
   - A skill in "output tokens by active skill" far outweighing its invocation count → that skill's
     body may be too verbose per-call.
   - Heavy Opus usage in `byModel` where Sonnet turns dominate the same project → candidate to
     default that work to Sonnet.
   Do not invent a dollar figure from token counts — four token types (input/output/cache
   read/cache creation) bill at different rates. Only cite cost if the digest's `totalCostUSD` line
   (sourced from `cost-state` records) has a non-zero value; otherwise talk in token counts.

5. **Write the report** to `~/ClaudeUsageReports/<date>-review.md` (outside `~/.claude/`, to keep
   the Write-tool permission rule for it separate from the Bash rule above) with two sections:
   "Skill candidates" and "Token-reduction suggestions", each a short bulleted list — concrete, not
   generic advice. You'll also need an `Edit(//<your literal expanded $HOME>/ClaudeUsageReports/**)`
   rule in `permissions.allow` for this to write unattended — **note the required double leading
   slash** on absolute paths in permission rules (`Edit(//Users/...)`, not `Edit(/Users/...)`); a
   single slash silently never matches. (The `.last-run` watermark is updated automatically by
   `analyze.sh` — nothing to do here.)

6. **Unattended runs.** If invoked non-interactively (scheduled via launchd, no human to prompt),
   skip any clarifying questions and just write the report — don't block waiting for input.
