---
name: dt-dashboard-design
description: Dynatrace dashboard tile coloring, formatting and visual design - why coloring must nest inside visualizationSettings (the silent failure that renders every tile colorless), colorThresholdTarget and labelMode on singleValue, theme color variables and the categorical palette, colored section banners via "data record()" since markdown cannot be colored, sparklines with increase/decrease trend deltas, unitsOverrides for percent signs and decimals, and the DQL gotchas behind wrong-looking tiles (duration literals, server spans, percentages in makeTimeseries, partial timeseries buckets). Also covers executive dashboard layout. Use alongside the dtctl skill for any dashboard work.
---

# Dynatrace Dashboard Design

Use alongside the `dtctl` skill (which covers the base dashboard YAML schema) and
`dt-dashboard-variables` (variables). This skill covers what makes tiles render
*correctly and legibly* — the parts that fail silently.

## The rule that breaks the most dashboards

**`coloring` MUST be nested inside `visualizationSettings`.**

Putting it at tile level is the easiest way to ship a completely colorless
dashboard. The API accepts and stores it there, `dtctl get` round-trips it back
intact, and `apply` reports success — but the UI only ever reads
`visualizationSettings.coloring`.

```yaml
"1":
  title: "Error rate"
  type: data
  query: "..."
  visualization: singleValue
  visualizationSettings:      # ← coloring lives HERE
    singleValue: { recordField: errs, labelMode: none, colorThresholdTarget: background }
    coloring:
      colorRules: [ ... ]
  # coloring: ...             # ← WRONG: stored, never rendered, never warned about
```

### Corollary: saving is not rendering

Confirming a field survived `apply` proves only that it was *stored*. Invalid keys
are stripped silently; unknown keys are kept silently. Neither warns.

Do not guess at schema shapes. Export a dashboard that already does what you want
and copy the shape:

```bash
dtctl get dashboard <id> -o json --plain
# Built-ins are the best reference:
#   dynatrace.services.service-health-overview   singleValue coloring + sparkline
#   dynatrace.quickstart.usage-overview          unitsOverrides
```

## singleValue

```yaml
visualization: singleValue
visualizationSettings:
  autoSelectVisualization: false
  singleValue:
    recordField: errors        # must match the query alias
    labelMode: none            # none = hide the label under the number
    label: "Errors"            # ignored when labelMode is none
    colorThresholdTarget: background   # background | value
```

- `labelMode: none` is what actually hides the label. **`showLabel: false` is
  silently ignored** — it round-trips unchanged but the UI never reads it.
- `colorThresholdTarget` decides what the color rules paint. `background` fills the
  whole tile (bold, readable across a room); `value` tints only the number.

### Sparkline with increase/decrease trend delta

Needs one record holding **both** a timeseries array and a scalar. `trend.isVisible`
renders the up/down delta for the period:

```yaml
query: |
  fetch spans
  | filter span.kind == "server"
  | makeTimeseries requests = count()
  | fieldsAdd requests = arraySlice(requests, from:1, to: arraySize(requests)-1)
  | fieldsAdd total = arraySum(requests)
visualizationSettings:
  singleValue:
    recordField: total          # the scalar → big number
    labelMode: none
    sparklineSettings:
      record: requests          # the ARRAY field → sparkline
      variant: area             # area | bar | line
      lineType: smooth
      color: { Default: "#134fc9" }
    trend:
      isVisible: true
```

Always trim the partial edge buckets (below) — untrimmed they draw a false cliff
and corrupt the delta.

## Color

### Theme variables, not raw hex

Built-ins use CSS variables with a hex fallback so colors follow the user's
light/dark theme. The fallback means a wrong variable name degrades to the hex
rather than breaking.

```
status  green  var(--dt-colors-charts-status-ideal-default, #2f6863)
        amber  var(--dt-colors-charts-status-warning-default, #eea53c)
        red    var(--dt-colors-charts-status-critical-default, #c4233b)
```

For **identity** color (which team / region / line of business — not how healthy it
is) use the categorical palette so it can never be mistaken for status:

```
01 #134fc9  02 #2c2f3f  03 #2a7453  04 #d85a9f  05 #84859a
06 #a9780f  07 #438fb1  08 #8b6ecf  09 #649438  11 #627cfe
12 #cd3741  13 #1c520a  14 #d56b1a  15 #9033a3
```
Pattern: `var(--dt-colors-charts-categorical-color-07-default, #438fb1)`.
Blue `01`, purple `15`, cyan `07`, pink `04` read as clearly distinct and never
resemble green/amber/red.

### colorRules must reference a numeric field

`count()`, `toLong()` and `round()` all serialize as **quoted strings**, so
comparators fail silently (uncolored tile, no error). Check with
`dtctl query ... -o json`: `"c": "42"` is quoted and will not color; `"c": 42` is
fine. Force numeric with `* 1.0`:

```dql
| summarize c = count()
| fieldsAdd open = c * 1.0        -- now unquoted, colors correctly
```

Float division already returns unquoted (`errs * 100.0 / total`), so rate and
percentage fields are safe as-is. Pair `* 1.0` with `decimals: 0` in
`unitsOverrides` or the tile reads `42.00`.

### Colored section banners / header bands

**Markdown tiles cannot be colored.** They have no color property and inline HTML
is sanitized — a `<div style="background:...">` is stripped and vanishes silently.
(Emoji blocks like `🟦🟦🟦` do render, but the palette is nine fixed colors, three
already spoken for by red/amber/green.)

For an arbitrary colored label band, use a `data` tile over a **literal record**.
It renders as a colored text bar and costs nothing — `data record()` touches no
Grail data:

```yaml
"20":
  title: ""
  type: data
  query: 'data record(a="Traffic Analysis")'
  visualization: singleValue
  visualizationSettings:
    singleValue:
      recordField: a
      label: a
      labelMode: none
      isIconVisible: false             # true shows a small leading chart icon
      colorThresholdTarget: background # fills the whole tile
    thresholds:                        # catch-all: a string is always != "0"
      - id: 1
        field: a
        title: ""
        isEnabled: true
        rules:
          - id: 0
            comparator: "!="
            value: "0"
            label: ""
            color: { Default: "var(--dt-colors-charts-categorical-color-01-default, #134fc9)" }
  davis: { enabled: false, davisVisualization: { isAvailable: true } }
```

`h: 1` gives a slim banner; `w: 24` spans a full section divider, `w: 6` makes a
per-column header. Note `thresholds` sits at `visualizationSettings.thresholds`, a
**sibling** of `coloring`, not inside it.

## Unit overrides

Controls decimals, thousands separators and unit suffixes. `identifier` must match
the query alias. Full shape as written by the UI:

```yaml
visualizationSettings:
  unitsOverrides:
    - identifier: p99           # must match query alias
      unitCategory: unspecified # unspecified | percentage | currency | ...
      baseUnit: nanosecond      # nanosecond | millisecond | second | percent | usd | none
      displayUnit: null         # null = auto-format
      decimals: 1
      suffix: ""
      delimiter: true           # thousands separator
      cascade: null
```

- **Durations reading as `1ns` / `349ns`** — don't divide in DQL. Return raw
  nanoseconds and let the override convert: `baseUnit: nanosecond`,
  `displayUnit: millisecond`. Dividing *and* setting a base unit double-converts.
- **A count rendering as `1.00`** — set `decimals: 0`.
- **Want a real `%` sign** — `unitCategory: percentage`, `baseUnit: percent` (the
  value is already 0-100).

## Charts

`axes.yAxis` accepts `label` only. Adding `min`/`max` makes the API reject the
**entire** `axes` object — dropped on save with no error, taking the axis label
with it. There is no supported way to pin a y-axis range.

## DQL gotchas behind wrong-looking tiles

### Duration needs duration literals, not nanosecond numbers

`duration` is typed. Comparing it to a bare number **silently matches nothing** —
no error, just a falsely perfect result:

```dql
-- WRONG: always 0, even when half the requests are slow
| summarize slow = countIf(duration > 2000000000)
-- CORRECT
| summarize slow = countIf(duration > 2s)     -- also 500ms, 1m, 1h
```

### Filter to server spans for user-facing latency

`fetch spans` is dominated by `client` and `internal` spans (short outbound calls)
which drag percentiles into the microseconds and make services look impossibly
fast:

```dql
fetch spans | filter span.kind == "server" | summarize p90 = percentile(duration, 90)
```
Sanity-check with `| summarize count(), by:{span.kind}`. If `client` massively
outnumbers `server`, an unfiltered percentile is meaningless.

### Percentages inside makeTimeseries

Arithmetic inside `makeTimeseries` fails with *"The parameter has to be an
expression-based timeseries aggregation"*. Averaging a 0/100 field gives the
percentage directly, with no arithmetic:

```dql
-- WRONG
| makeTimeseries rate = countIf(status == "ERROR") * 100 / count()
-- CORRECT
| fieldsAdd ok = if(duration <= 2s, 100, else: 0)
| makeTimeseries pct = avg(ok), by:{lob}
```

### Partial buckets at both ends of a timeseries

The first and last `makeTimeseries` buckets are usually partial, drawing a false
cliff at each end and corrupting any increase/decrease delta:

```dql
| makeTimeseries requests = count()
| fieldsAdd requests = arraySlice(requests, from:1, to: arraySize(requests)-1)
| fieldsAdd total = arraySum(requests)
```

`arraySlice`'s `to` is **exclusive**. `to: arraySize(x)-1` drops exactly one
trailing element; `to: arraySize(x)-2` drops two. (Dynatrace's own Service Health
Overview uses `-2` under a comment saying it trims "the last bucket" — it actually
trims two.) Trimming the *leading* bucket matters whenever a trend delta is shown,
since a partial start fakes an increase.

### OR across entity selectors

Tags are ANDed within a single `entitySelector`, so express OR with nested `if` —
which also yields one clean multi-series chart instead of N tiles:

```dql
| fieldsAdd lob = if(in(dt.entity.service, entitySelector("type(SERVICE),tag(\"LOB:Claims\")")), "Claims",
            else: if(in(dt.entity.service, entitySelector("type(SERVICE),tag(\"LOB:Digital\")")), "Digital"))
| filter isNotNull(lob)
| makeTimeseries pct = avg(ok), by:{lob}
```

## Designing an executive dashboard

For a non-technical audience the board must answer *"is everything OK?"* at a
glance. Practical rules that survived contact with a real one:

**Give every metric a target.** A bare error rate or response time means nothing to
an executive. `0.3% errors` is unreadable; `98% of requests answered under 2s`
against a stated 99% target is self-evidently bad. State the target in a markdown
header so the number judges itself.

**Check the metric actually discriminates before building on it.** Error rate was
0% across every line of business on a real board — useless as a headline. Latency
was where the variance was. Query first, then design.

**Lead with Davis problems.** Currently-open problems is the most direct answer to
"is everything OK". Count them by taking problems with no `CLOSED` record:

```dql
fetch events, from:now()-24h
| filter event.kind == "DAVIS_PROBLEM"
| summarize closed = countIf(event.status == "CLOSED"), by:{display_id}
| filter closed == 0
| summarize c = count()
| fieldsAdd open_problems = c * 1.0
```
Keep an explicit `from:` on this tile so shortening the dashboard timeframe cannot
hide open problems. Problem events carry `entity_tags`, so they can be attributed
to a business area — but only where the tag is on the affected entity, which is
often a host rather than a service.

**Keep color meaning exactly one thing.** Once green means healthy, spending it on
"big number" costs the whole scanning rule. Leave volume/throughput tiles
uncolored deliberately, and use the categorical palette for identity.

**Respect the fold.** "Single page, nothing below the fold" is a hard constraint;
~22 grid rows is a safe budget. When generating layouts programmatically, assert on
it so it cannot silently regress:

```python
occupied = {}
for k, L in layouts.items():
    for yy in range(L["y"], L["y"] + L["h"]):
        for xx in range(L["x"], L["x"] + L["w"]):
            assert (xx, yy) not in occupied, f"overlap {k} vs {occupied[(xx,yy)]}"
            occupied[(xx, yy)] = k
assert max(L["y"] + L["h"] for L in layouts.values()) <= 22, "below the fold"
```

**Tiles have no `description` field.** The only keys are `title`, `type`, `query`,
`visualization`, `visualizationSettings`, `coloring`, `davis`. Put per-tile context
in the `title` and section-level context in a `markdown` tile.
