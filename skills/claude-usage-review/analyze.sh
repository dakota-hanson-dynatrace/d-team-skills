#!/usr/bin/env bash
# claude-usage-review :: deterministic digest generator (pure bash + jq, zero model tokens).
# Crushes ~/.claude/projects/*.jsonl transcripts into a few-KB digest the review skill reads.
# Usage:
#   analyze.sh            # build digest-<date>.{json,md} in ~/.claude/usage-reports/
#   analyze.sh --selftest # run the jq aggregation against a fixture, assert, exit
set -euo pipefail

PROJECTS="${CLAUDE_PROJECTS_DIR:-$HOME/.claude/projects}"
OUT="${CLAUDE_USAGE_REPORTS_DIR:-$HOME/.claude/usage-reports}"
DATE="$(date +%F)"

# Per-session reducer. Run once per transcript; collapses one .jsonl to one small JSON object.
# Reused by --selftest so the fixture exercises the exact production paths.
read -r -d '' PERFILE_JQ <<'JQ' || true
def addmap(a;b): reduce (b|to_entries[]) as $e (a; .[$e.key]=((.[$e.key]//0)+$e.value));
reduce inputs as $r (
  {turns:0,input:0,output:0,cc:0,cr:0,think:0,byModel:{},bySkill:{},skillCalls:{},tools:{},bash:{}};
  if ($r.type=="assistant") then
    ($r.message.usage // {}) as $u |
    ($r.message.model // "unknown") as $m |
      .turns  += 1
    | .input  += ($u.input_tokens // 0)
    | .output += ($u.output_tokens // 0)
    | .cc     += ($u.cache_creation_input_tokens // 0)
    | .cr     += ($u.cache_read_input_tokens // 0)
    | .think  += ($u.output_tokens_details.thinking_tokens // 0)
    | .byModel[$m] = ( (.byModel[$m] // {turns:0,output:0,cr:0,cc:0,input:0,think:0})
        | .turns  += 1
        | .output += ($u.output_tokens // 0)
        | .cr     += ($u.cache_read_input_tokens // 0)
        | .cc     += ($u.cache_creation_input_tokens // 0)
        | .input  += ($u.input_tokens // 0)
        | .think  += ($u.output_tokens_details.thinking_tokens // 0) )
    | (if $r.attributionSkill
         then .bySkill[$r.attributionSkill] = ((.bySkill[$r.attributionSkill]//0) + ($u.output_tokens // 0))
         else . end)
    | reduce ($r.message.content[]? | select(.type=="tool_use")) as $t (.;
          .tools[$t.name] = ((.tools[$t.name]//0)+1)
        | (if $t.name=="Skill" and ($t.input.skill != null)
             then .skillCalls[$t.input.skill] = ((.skillCalls[$t.input.skill]//0)+1) else . end)
        # ponytail: naive first-token bash key (basename of argv[0]); fine for frequency ranking,
        # upgrade to strip leading `cd`/env-var prefixes if the table gets noisy.
        | (if $t.name=="Bash" and ($t.input.command != null)
             then ( ($t.input.command|ltrimstr(" ")|split(" ")[0]|split("/")|last) as $cmd
                    | .bash[$cmd] = ((.bash[$cmd]//0)+1) ) else . end) )
  else . end)
JQ

selftest() {
  local fixture out
  # One assistant record: 2 tool_use blocks (a Skill call + a Bash call), usage counters set.
  fixture='{"type":"assistant","attributionSkill":"dtctl","message":{"model":"claude-opus-5","usage":{"input_tokens":5,"output_tokens":100,"cache_creation_input_tokens":200,"cache_read_input_tokens":4000,"output_tokens_details":{"thinking_tokens":40}},"content":[{"type":"tool_use","name":"Skill","input":{"skill":"dtctl"}},{"type":"tool_use","name":"Bash","input":{"command":"/usr/bin/git status"}}]}}
{"type":"user","message":{"role":"user","content":"ignored"}}'
  out="$(printf '%s\n' "$fixture" | jq -n "$PERFILE_JQ")"
  check() { # $1=jq-path $2=expected
    local got; got="$(printf '%s' "$out" | jq -r "$1")"
    if [ "$got" != "$2" ]; then echo "SELFTEST FAIL: $1 = $got (expected $2)" >&2; exit 1; fi
  }
  check '.turns' 1
  check '.input' 5
  check '.output' 100
  check '.cc' 200
  check '.cr' 4000
  check '.think' 40
  check '.byModel["claude-opus-5"].output' 100
  check '.bySkill["dtctl"]' 100
  check '.skillCalls["dtctl"]' 1
  check '.tools["Bash"]' 1
  check '.bash["git"]' 1
  echo "SELFTEST OK"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit 0; fi

mkdir -p "$OUT"
command -v jq >/dev/null || { echo "jq not found on PATH" >&2; exit 1; }
[ -d "$PROJECTS" ] || { echo "no projects dir: $PROJECTS" >&2; exit 1; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
SESS="$TMP/sessions.ndjson"; : > "$SESS"

# One jq per transcript -> one compact session summary line. Streams NDJSON (never slurps a file).
while IFS= read -r f; do
  proj="$(basename "$(dirname "$f")")"
  sess="$(basename "$f" .jsonl)"
  if ! jq -n --arg session "$sess" --arg project "$proj" \
        "$PERFILE_JQ | . + {session:\$session, project:\$project}" < "$f" >> "$SESS" 2>/dev/null; then
    echo "warn: failed to parse $f" >&2
  fi
done < <(find "$PROJECTS" -type f -name '*.jsonl')

# Real-dollar cross-check from pre-aggregated cost-state records (last per session, summed).
COST="$(find "$PROJECTS" -type f -name '*.jsonl' -exec cat {} + 2>/dev/null \
  | jq -n 'reduce inputs as $r ({}; if $r.type=="cost-state" then .[$r.sessionId]=($r.totalCostUSD // 0) else . end) | ([.[]]|add) // 0' 2>/dev/null || echo 0)"

# Sessions touched since the last review (skill writes .last-run after it reports).
if [ -f "$OUT/.last-run" ]; then
  NEW_COUNT="$(find "$PROJECTS" -type f -name '*.jsonl' -newer "$OUT/.last-run" | wc -l | tr -d ' ')"
else
  NEW_COUNT="all (no prior run)"
fi

DIGEST_JSON="$OUT/digest-$DATE.json"
DIGEST_MD="$OUT/digest-$DATE.md"

# Final rollup over the ~160 small session objects (cheap).
jq -s --arg date "$DATE" --argjson cost "${COST:-0}" '
  def addmap(a;b): reduce (b|to_entries[]) as $e (a; .[$e.key]=((.[$e.key]//0)+$e.value));
  def addmodel(a;b): reduce (b|to_entries[]) as $e (a;
     .[$e.key] = ((.[$e.key]//{turns:0,output:0,cr:0,cc:0,input:0,think:0}) as $x
        | {turns:($x.turns+$e.value.turns),output:($x.output+$e.value.output),cr:($x.cr+$e.value.cr),
           cc:($x.cc+$e.value.cc),input:($x.input+$e.value.input),think:($x.think+$e.value.think)}));
  {
    generated: $date,
    totalCostUSD: $cost,
    totals: (reduce .[] as $x ({turns:0,input:0,output:0,cc:0,cr:0,think:0,sessions:0};
       .turns+=$x.turns|.input+=$x.input|.output+=$x.output|.cc+=$x.cc|.cr+=$x.cr|.think+=$x.think|.sessions+=1)),
    perProject: (group_by(.project) | map({project:.[0].project, sessions:length,
       turns:(map(.turns)|add), input:(map(.input)|add), output:(map(.output)|add),
       cc:(map(.cc)|add), cr:(map(.cr)|add), think:(map(.think)|add)}) | sort_by(-.output)),
    byModel: (reduce .[] as $x ({}; addmodel(.; $x.byModel))),
    bySkill: (reduce .[] as $x ({}; addmap(.; $x.bySkill))),
    skillCalls: (reduce .[] as $x ({}; addmap(.; $x.skillCalls))),
    tools: (reduce .[] as $x ({}; addmap(.; $x.tools))),
    bash: (reduce .[] as $x ({}; addmap(.; $x.bash))),
    biggestSessions: (sort_by(-.output) | .[0:15] | map({session,project,output,turns,cr,cc}))
  }' "$SESS" > "$DIGEST_JSON"

# Render the markdown digest (the human-readable export + what the skill reads).
jq -r --arg new "$NEW_COUNT" '
  def ratio(cr;cc;inp): (cr+cc+inp) as $d | (if $d>0 then (cr/$d*100|floor) else 0 end);
  def toptbl(m;n): (m|to_entries|sort_by(-.value)|.[0:n]);
  "# Claude Code Usage Digest - \(.generated)",
  "",
  "Sessions modified since last review: \($new)",
  (.totalCostUSD as $c | if $c>0 then "Cost (from cost-state records, partial coverage): $\($c|.*100|round/100)" else "Cost: no cost-state records found (token counts below are the basis)" end),
  "",
  "## Totals (all time)",
  "- sessions: \(.totals.sessions)  |  assistant turns: \(.totals.turns)",
  "- output tokens: \(.totals.output)  |  thinking: \(.totals.think)",
  "- cache_read: \(.totals.cr)  |  cache_creation: \(.totals.cc)  |  input: \(.totals.input)",
  "- cache hit ratio: \(ratio(.totals.cr;.totals.cc;.totals.input))% (cache_read / (read+creation+input))",
  "",
  "## By project (sorted by output tokens)",
  "| project | sessions | turns | output | cache_read | cache_creation | cache hit % |",
  "|---|--:|--:|--:|--:|--:|--:|",
  (.perProject[] | "| \(.project) | \(.sessions) | \(.turns) | \(.output) | \(.cr) | \(.cc) | \(ratio(.cr;.cc;.input))% |"),
  "",
  "## By model",
  "| model | turns | output | cache_read | cache_creation | input |",
  "|---|--:|--:|--:|--:|--:|",
  (.byModel|to_entries|sort_by(-.value.output)|.[] | "| \(.key) | \(.value.turns) | \(.value.output) | \(.value.cr) | \(.value.cc) | \(.value.input) |"),
  "",
  "## Output tokens by active skill (attributionSkill)",
  (if (.bySkill|length)>0 then (toptbl(.bySkill;20)[] | "- \(.key): \(.value)") else "- (none recorded)" end),
  "",
  "## Skill invocations (Skill tool calls)",
  (if (.skillCalls|length)>0 then (toptbl(.skillCalls;20)[] | "- \(.key): \(.value)") else "- (none recorded)" end),
  "",
  "## Tool usage frequency (top 20)",
  (toptbl(.tools;20)[] | "- \(.key): \(.value)"),
  "",
  "## Bash command frequency (top 25, by argv[0] basename)",
  (toptbl(.bash;25)[] | "- \(.key): \(.value)"),
  "",
  "## Biggest sessions by output tokens (compaction candidates)",
  "| session | project | output | turns |",
  "|---|---|--:|--:|",
  (.biggestSessions[] | "| \(.session[0:8]) | \(.project) | \(.output) | \(.turns) |")
' "$DIGEST_JSON" > "$DIGEST_MD"

echo "wrote $DIGEST_JSON"
echo "wrote $DIGEST_MD"

# Watermark for next run's "new since last review" count. Folded in here (rather than a separate
# bash call from the skill) so unattended runs only need one Bash permission rule, not two.
date -u +%FT%TZ > "$OUT/.last-run"
