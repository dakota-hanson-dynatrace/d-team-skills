# overrides.json - what the model writes

`collect.py` writes `facts.json` with every countable field. The model writes only
`overrides.json`: the judgment calls. Both generators merge them (`--data facts.json overrides.json`,
later file wins), so any fact can also be corrected here.

Keep overrides small. Write text only where the digest shows something tenant-specific; the opportunity
library already has data-driven text for the standard findings (see `scoring.md`).

## Fields

| Key | Required | What it is |
|---|---|---|
| `summary` | yes | One paragraph, SE voice: overall position, then the two or three themes |
| `summary_points` | yes | 3-5 short bullets with real numbers |
| `top_priorities` | yes | Finding keys to lead with, in order (5) |
| `platform_matrix` | yes | One row per capability area (below) |
| `anomalies` | if any | Real deviations only, judged from the digest's "Anomaly candidates" |
| `custom_findings` | if any | Tenant-specific findings the library can't trigger on |
| `caveats` | yes | Scope gaps, approximations, inferences (for example "assumed VMware intentionally absent") |
| `resolved` | if a prior review exists | What changed since then, stated as current facts |
| `label_overrides` / `effort_overrides` | optional | `{finding_key: text}` when a default label is generic or effort understates coordination |
| `exec_coverage_bullet` | optional | Replaces the deck's first Executive Overview bullet (default: OneAgent coverage %, which counts uncovered cloud instances and can mislead when they are EKS nodes) |
| `stat_cards` | optional | `[["338", "Hosts\nMonitored by OneAgent"], ...]` (4 cards) |
| `hosts_infra_names`, `slo_candidates`, `log_external_note`, `vmware_problem_note` | optional | Short phrases that enrich library text |
| Corrections | as needed | Any facts.json field the digest shows is wrong (e.g. `retention_confirmed: true`, `vmware_ext_intentional: true`) |

## platform_matrix rows

One row per area. Areas and their evidence are listed in `queries-config.md` (GEN2 / GEN3 LENS);
the digest's readiness section supplies most of it.

| Key | Meaning |
|---|---|
| `area`, `status` | `Gen3` = platform slide only; `Gen2` = Upgrade finding; `Both` = Consolidate finding |
| `gen2_today`, `gen3_today`, `matrix_next` | Short cells for the report's platform table |
| `gen2`, `gen3`, `title`, `label` | Names for finding titles and slide labels (label under ~45 chars) |
| `headline`, `detail`, `next_step`, `action`, `value` | Finding text; `detail` lines starting with `▸` become bullets |
| `duplication_check` | **Required** for Gen2/Both: why the step won't leave two copies running |
| `duplicate` | true when part of the classic config is already covered by Gen3 |
| `effort` | Effort to complete ("2 hr", "3 days"). Drives the Low / Medium / High Effort grouping and the phase. Any `cost` or `line_item` key is ignored |

Gen3-only rows need only `area`, `status`, `gen2_today`, `gen3_today`, `matrix_next`.

A Gen2/Both row supersedes the matching library finding (`workflows`, `slos`, `rum_enablement`,
`tagging_strategy`) so one migration never appears twice.

## anomalies

```json
{"scope": "service", "entity": "CustomerAlarmController", "metric": "failure rate", "kind": "trend",
 "severity": "high", "title": "Optional finding title", "label": "Short slide label",
 "summary": "One sentence with the numbers.", "detail": "Optional second paragraph.",
 "recommendation": "What to do.", "effort": "2 hr", "value": "Roadmap value text"}
```

`severity: high` puts it in Phase 1. Key is `anomaly_<entity>_<metric>` (use it in `top_priorities`).
Chronic 90-100% failure rates usually mean failure detection counts expected responses; say so.
Batch workers (Databricks, EMR) running hot are not anomalies; persistent hosts are.

## custom_findings

Same keys as a platform_matrix row plus `key`, `tier` (Coverage / Anomaly / Config Fix / Upgrade /
Start Here / High Value / Phase 2), optional `gen` and `phase`. Use for things like an oversized log source,
a duplicated workflow, OneAgents below the Gen3 minimum, or a large production VM gap (with
Infra-only vs FullStack split by role). State the value, not the price: what the team can see or do
afterwards.

## The no-duplication rule

No recommendation may leave two copies of the same thing running. The library enforces the known
cases (forwarder logs vs OneAgent logs, DB extensions already present, classic SLO vs Gen3 SLO,
classic notification vs workflow). For everything the model writes: if you can't write the
`duplication_check` sentence, don't recommend the upgrade. If the Gen3 side couldn't be read (403),
say the check is still needed.

## Writing voice

The deliverables go out under the SE's name and must read like an SE wrote them:
- Plain, specific sentences with the tenant's numbers and entity names.
- No marketing filler ("unlock", "supercharge", "single highest-leverage"), no rhetorical questions.
- Never use the word "cost" (or price, billing, DPS) in any field. The customer reads effort and value only: what it takes to do, and what it unlocks. Say "takes an hour" or "adds trace data for 40 hosts".
- No em dashes; use a plain hyphen or rewrite. No emoji, no decorative arrows.
- State what was found, then what to do. Say what wasn't verified; don't claim what the data doesn't show.

## tech_exclude (optional)
List of technology names (as they appear in the digest's "Technology and extension opportunities" section) to drop from
the Additional Monitoring Opportunities slide and report section, e.g. `["Apache Tomcat (JMX)"]`. Use for noise only.
