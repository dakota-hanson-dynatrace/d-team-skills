---
name: dt-finops-hosts
description: Find Dynatrace hosts monitored as FullStack that look like Infra-only downgrade candidates, to cut FinOps cost from unused deep monitoring. Read-only — identifies candidates via DQL, never changes monitoring mode. Triggers on "FullStack candidates", "Infra-only downgrade", "hosts without deep monitoring", "unused FullStack hosts", "FinOps host review", "downgrade FullStack hosts", "hosts paying for FullStack we don't need".
---

# FinOps: FullStack → Infra-Only Candidate Finder

Identifies hosts monitored as **FullStack** that have no real deep-monitored workload —
i.e. no processes justifying code-level (application) monitoring — making them candidates
to downgrade to **Infra-only** and cut licensing cost.

**This skill is read-only.** It reports candidates; it never changes a host's monitoring
mode. Load `dtctl` first (or alongside) for auth/context setup and DQL conventions this
skill assumes.

## Prerequisites

```bash
dtctl auth status --plain     # confirm context + token are live
dtctl query "fetch dt.entity.host | limit 1" -o json --plain   # smoke test
```

Any safety level works (`readonly` is enough — nothing here writes). Required scopes are
the standard `dtctl query` read scopes (`storage:entities:read`, `storage:smartscape:read`,
plus the rest of the standard set) — if the smoke test above returns a host, you have what
you need.

## Core query

`monitoringMode` (`FULL_STACK` / `INFRASTRUCTURE` / `DISCOVERY`) lives on `dt.entity.host`,
not on `smartscapeNodes "HOST"` — and `smartscapeNodes "PROCESS"` has no `dt.smartscape.host`
field to join on, only `host.name`. Cost center, host group, and memory live on
`smartscapeNodes "HOST"`. So the query joins across all three, using `toString(id)` on both
sides of the monitoringMode lookup (raw `id` types don't match across sources) and `host.name`
for the process join:

```dql
smartscapeNodes "HOST"
| fieldsAdd host_name = name, host_id_str = toString(id),
    memory_gib = round(toDouble(memory) / 1024 / 1024 / 1024, decimals: 1)
| lookup [
    fetch dt.entity.host
    | fieldsAdd monitoringMode, host_id_str = toString(id)
  ], sourceField: host_id_str, lookupField: host_id_str
| fieldsAdd monitoringMode = lookup.monitoringMode
| filter monitoringMode == "FULL_STACK"
| lookup [
    smartscapeNodes "PROCESS"
    | summarize process_count = count(), by: {host.name}
  ], sourceField: host_name, lookupField: host.name
| fieldsAdd process_count = coalesce(lookup.process_count, 0)
| filter process_count == 0
| fields host_name, dt.host_group.id, dt.cost.costcenter, process_count, memory_gib
| sort host_name
```

**RAM totals / savings variant:** swap the last two lines for a `summarize` to get the
aggregate RAM currently billed at FullStack rates that would move to Infra-only:

```dql
... (same pipeline through `| filter process_count == 0`) ...
| summarize candidate_hosts = count(), total_ram_gib = round(sum(memory_gib), decimals: 1)
```

RAM is a proxy for licensing impact, not a dollar figure — Dynatrace host-based consumption
scales with RAM and Infra-only is billed at a fraction of the FullStack rate, but the exact
ratio depends on the tenant's contract (classic Host Units vs. DPS/DDU). Report GiB moved,
not a cost estimate, unless the SE supplies the tenant's actual rate.

**Proxy signal, not exact:** no field on `smartscapeNodes "PROCESS"` or
`dt.entity.process_group_instance` exposes the classic UI's per-process "Deep Monitoring:
Enabled / Failed to Enable" status — it may not be in Grail at all. Treat
**process_count == 0 on a FullStack host** as a proxy for "no deep monitoring
justification," and spot-check a few results (`smartscapeNodes "PROCESS" | filter
host.name == "<name>"` over a wider window, e.g. `from:now()-7d`) against the classic
Hosts UI before treating the list as final.

## Output

Present as a table: host name, host group, cost center, process count (should be 0 for
every row), RAM (GiB). Follow with the aggregate candidate count and total RAM. Do not
suggest or perform the mode switch — hand the list back to the SE to action manually (UI
or a separate deliberate step).

## Known limitations

- Proxy signal, not a guaranteed match for the UI's "Deep Monitoring" column — spot-check
  a few results in the classic Hosts UI before treating the list as final.
- RAM totals show licensing *exposure*, not dollar savings — the FullStack→Infra-only rate
  ratio is contract-specific.
