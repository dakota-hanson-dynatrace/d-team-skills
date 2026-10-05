---
name: kubectl-pod-debug
description: Live kubectl debugging against real clusters — resolve a pod by label in a namespace then tail/exec it, wait for rollout or an external-IP instead of hand-rolled sleep loops, and stop retyping -n on every command. For LIVE kubectl operations only, not Dynatrace K8s telemetry/DQL (that's dynatrace:dt-obs-kubernetes — do not use this skill for that). Triggers on "kubectl", "exec into a pod", "tail pod logs", "find the pod for app X", "wait for rollout", "wait for external IP", "crashlooping pod", "kubectl exec", "kubectl logs -n".
---

# kubectl pod debug helper

Encodes the idiom retyped dozens of times across demo-cluster debugging sessions
(`ai-observability`, `ai-observability-openinference`, `cross-cloud-demo`, `load-generator`,
`traffic-generator`, `otel-demo`, `argocd` namespaces; `d-team-demo-1` / `imf-poc-1` contexts):
**find the pod for an app by label, then log/exec/wait on it.** This is raw cluster
debugging, not Dynatrace observability data — for Grail/DQL questions about K8s (OOMKills,
restarts, resource usage) use `dynatrace:dt-obs-kubernetes` instead.

## Resolve pod by label, then act

The pattern seen over and over:

```bash
POD=$(kubectl get pod -n <ns> -l app=<app> -o jsonpath='{.items[0].metadata.name}')
kubectl logs -n <ns> "$POD" --tail=50
kubectl exec -n <ns> "$POD" -- <cmd>
```

**Known gap in that exact idiom:** `.items[0]` takes whatever the API returns first, which
can be a `Terminating`/`CrashLoopBackOff` pod from a previous rollout rather than the live
one. Every occurrence found used `.items[0]` with no `--field-selector` or `--sort-by`. Make
it robust with one extra flag:

```bash
POD=$(kubectl get pod -n <ns> -l app=<app> --field-selector=status.phase=Running \
  --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1:].metadata.name}')
```

**Simpler alternative, also seen in the transcripts:** if the deployment has one replica (or
you don't care which replica), skip pod resolution entirely — `kubectl logs`/`exec` accept a
workload reference directly:

```bash
kubectl logs -n <ns> deploy/<name> --tail=50
kubectl exec -n <ns> deploy/<name> -- <cmd>
```

## Wait for readiness, don't sleep-loop

`kubectl apply` followed by chained `rollout status` calls is already the right pattern and
shows up correctly:

```bash
kubectl apply -f manifest.yaml && \
  kubectl rollout status deployment/<name> -n <ns> --timeout=90s
```

But for things `rollout status` doesn't cover (e.g. waiting for a LoadBalancer external IP),
sessions fall back to a hand-rolled poll loop instead of a native kubectl feature:

```bash
# seen pattern — works, but reinvents what kubectl wait already does
for i in $(seq 1 24); do
  IP=$(kubectl -n <ns> get svc <name> -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null)
  [ -n "$IP" ] && { echo "EXTERNAL-IP: $IP"; break; }
  sleep 5
done
```

`kubectl wait` (1.23+) supports arbitrary jsonpath conditions natively — one line, built-in
timeout, no loop to retype:

```bash
kubectl wait -n <ns> svc/<name> --for=jsonpath='{.status.loadBalancer.ingress}' --timeout=120s
```

Same applies to waiting on a pod becoming ready instead of polling `get pod`:

```bash
kubectl wait -n <ns> pod -l app=<app> --for=condition=ready --timeout=60s
```

## Stop retyping -n on every command

`-n <namespace>` appears on nearly every command in these sessions, often against the same
namespace for a whole debugging block. If you're about to run more than a couple of commands
against one namespace, set it as the context default instead of repeating the flag:

```bash
kubectl config set-context --current --namespace=<ns>
```

(`kubectl config current-context` / `get-contexts` / `use-context` also show up often when
juggling `d-team-demo-1` vs `imf-poc-1` — same idea: check/switch once, not per command.)
