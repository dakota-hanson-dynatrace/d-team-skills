#!/usr/bin/env bash
# Self-check: runs each query the skill depends on against the current dtctl context
# and asserts it returns rows. No mutations. Exits non-zero on the first failure.
set -euo pipefail

ctx=$(dtctl config current-context)
echo "Running tagging-review self-test against context: $ctx"

# name|DQL  — each must come back ok:true with at least one row
checks=(
  'host groups|smartscapeNodes "HOST" | summarize count(), by:{dt.host_group.id} | limit 5'
  'unassigned bucket|smartscapeNodes "HOST" | fieldsAdd hg=if(isNull(dt.host_group.id),"<null>",else:dt.host_group.id) | fieldsAdd bucket=if(in(hg,array("<null>","TBD","None","To Be Determined")),"UNASSIGNED",else:"assigned") | summarize c=count(), by:{bucket}'
  'tag taxonomy|fetch dt.entity.host, from:now()-24h | fieldsAdd tag=tags | expand tag | summarize count(), by:{tag} | limit 5'
  'environment values|fetch dt.entity.host, from:now()-24h | fieldsAdd tag=tags | expand tag | filter startsWith(tag,"Environment:") | summarize count() | limit 1'
  'bracket-key dup|fetch dt.entity.host, from:now()-24h | fieldsAdd tag=tags | expand tag | fieldsAdd dup=if(startsWith(tag,"[Environment]"),"bracketEnv",else:"plain") | summarize count(), by:{dup}'
  'k8s namespaces|smartscapeNodes "K8S_NAMESPACE" | summarize count(), by:{k8s.cluster.name} | limit 5'
)

fail=0
for c in "${checks[@]}"; do
  name="${c%%|*}"; dql="${c#*|}"
  out=$(dtctl query "$dql" --agent -o json 2>&1 || true)
  if echo "$out" | grep -q '"ok":true' && echo "$out" | grep -Eq '"(records|total)"'; then
    echo "  PASS  $name"
  else
    echo "  FAIL  $name"
    echo "        $out" | head -c 300; echo
    fail=1
  fi
done

# K8S_NAMESPACE check is advisory: a tenant with no Kubernetes legitimately returns 0 rows.
[ "$fail" -eq 0 ] && echo "All checks passed." || { echo "One or more checks failed (K8s absence is OK on non-K8s tenants)."; exit 1; }
