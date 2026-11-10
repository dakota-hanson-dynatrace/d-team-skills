#!/usr/bin/env python3
"""Build the tenant assets from facts.json: a findings notebook and a timeframe-driven comparison dashboard.

    uv run --with pyyaml python -X utf8 build_assets.py --dir <out> --customer "<name>" [--test-queries] [--apply --yes-write]

- The DASHBOARD follows the timeframe picker: whatever window is selected is compared with a window of the SAME
  LENGTH shifted back exactly 7 days (a 24 hour window against 24 hours, a 1 hour window against 1 hour).
  Notebooks cannot read the picker ($dt_timeframe_* fails in notebooks), which is why this is a dashboard.
- The NOTEBOOK holds the findings: live queries on fixed relative windows (last 24h against the 24h that ended 7 days ago)
  next to the numbers from this analysis.
- --apply raises the context safety level just long enough to create both, then puts it back. It needs --yes-write,
  which must only be passed after the user has agreed to the write.
"""
import argparse, json, os, re, subprocess, sys, textwrap

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dtq import Tenant, safety_level, set_safety  # noqa: E402

M = "dt.sfm.metrics.ingest.datapoints"
BILL = 'event.kind == "BILLING_USAGE_EVENT" and event.type == "Metrics - Ingest & Process"'
QLOG = 'event.kind == "QUERY_EXECUTION_EVENT" and table == "metrics"'
# The notebook and dashboard UIs read a schema version from the document content. Content saved WITHOUT it is treated as a legacy
# document and its saved visualization is ignored: every tile opens as Raw response. These are the values the UI itself writes.
NB_VERSION = "7"      # notebooks store the version as a string
DB_VERSION = 21       # dashboards store it as an integer; the most common value in a tenant's saved dashboards


def detect_versions(work_dir):
    """Use the most common content version found in the tenant's own exported notebooks and dashboards, when available."""
    import collections
    cdir = os.path.join(work_dir, "corpus")
    seen = {"notebooks": collections.Counter(), "dashboards": collections.Counter()}
    if os.path.isdir(cdir):
        for fn in os.listdir(cdir):
            kind = fn.split("__")[0]
            if kind not in seen:
                continue
            try:
                raw = open(os.path.join(cdir, fn), encoding="utf-8", errors="ignore").read().split("\n", 2)[2]
                c = json.loads(raw)["content"]
                c = json.loads(c) if isinstance(c, str) else c
                if c.get("version") is not None:
                    seen[kind][c["version"]] += 1
            except Exception:
                continue
    nb = seen["notebooks"].most_common(1)
    db = seen["dashboards"].most_common(1)
    return (nb[0][0] if nb else NB_VERSION), (db[0][0] if db else DB_VERSION)


NB_PREFIX = "Metric Ingest Optimization - Findings"
DB_NAME = "Metric Ingest - Billed Window vs 7 Days Earlier"

# ---------------------------------------------------------------------------------------------------------------
# Dashboard queries. F and T are the picker bounds. The previous window is F-7d .. T-7d, so it always has the same length.
# ---------------------------------------------------------------------------------------------------------------
F = "toTimestamp($dt_timeframe_from)"
T = "toTimestamp($dt_timeframe_to)"
CUR = f"from:{F}, to:{T}"
PRV = f"from:{F} - 7d, to:{T} - 7d"
DQ = {}
DQ["win"] = f'data record(`Selected window start` = {F}, `Selected window end` = {T}, `Compared against start` = {F} - 7d, `Compared against end` = {T} - 7d, `Window length` = {T} - {F})'
DQ["ingest_head"] = f'''timeseries cur = sum({M}, scalar:true), {CUR}
| append [timeseries prev = sum({M}, scalar:true), {PRV}]
| summarize {{cur = sum(cur), prev = sum(prev)}}
| fieldsAdd delta = cur - prev
| fieldsAdd change_pct = delta * 100.0 / prev'''
# Billing records arrive hours after the usage they describe, so they are matched on usage.start, not arrival time.
DQ["billed_head"] = f'''fetch dt.system.events, from:{F} - 7d
| filter {BILL}
| fieldsAdd us = toTimestamp(usage.start), dp = toLong(data_points)
| summarize {{cur = sum(if(us >= {F} and us < {T}, dp, else: 0)), prev = sum(if(us >= {F} - 7d and us < {T} - 7d, dp, else: 0))}}
| fieldsAdd delta = cur - prev
| fieldsAdd change_pct = delta * 100.0 / prev'''
DQ["billed_by_type"] = f'''fetch dt.system.events, from:{F} - 7d
| filter {BILL}
| fieldsAdd us = toTimestamp(usage.start), dp = toLong(data_points)
| summarize {{`Selected window` = sum(if(us >= {F} and us < {T}, dp, else: 0)), `7 days earlier` = sum(if(us >= {F} - 7d and us < {T} - 7d, dp, else: 0))}}, by:{{`Data type` = metric.type, `Monitoring source` = monitoring_source}}
| fieldsAdd Change = `Selected window` - `7 days earlier`
| fieldsAdd `Change %` = if(`7 days earlier` == 0, 100.0, else: Change * 100.0 / `7 days earlier`)
| sort `Selected window` desc'''
DQ["by_source"] = f'''timeseries cur = sum({M}, scalar:true), by:{{grail.metric.source}}, {CUR}
| append [timeseries prev = sum({M}, scalar:true), by:{{grail.metric.source}}, {PRV}]
| summarize {{cur = sum(cur), prev = sum(prev)}}, by:{{grail.metric.source}}
| fieldsAdd cur = coalesce(cur, 0.0), prev = coalesce(prev, 0.0)
| fieldsAdd delta = cur - prev
| fieldsAdd change_pct = if(prev == 0, 100.0, else: delta * 100.0 / prev)
| sort cur desc
| fields `Source` = coalesce(grail.metric.source, "(none)"), `Selected window` = cur, `7 days earlier` = prev, Change = delta, `Change %` = change_pct'''
DQ["by_source_chart"] = DQ["by_source"].rsplit("\n| fields", 1)[0].replace("| sort cur desc", "| sort cur desc\n| limit 10") + "\n| fields `Source` = coalesce(grail.metric.source, \"(none)\"), `Selected window` = cur, `7 days earlier` = prev"
# The ingest measure lands in 10 minute batches, so a fixed 10m interval keeps both windows aligned for any window length.
DQ["overlay"] = f'''timeseries cur = sum({M}), interval:10m, {CUR}
| append [timeseries prev = sum({M}), interval:10m, {PRV}]
| summarize {{`Selected window` = takeFirst(cur), `Same window 7 days earlier` = takeFirst(prev), timeframe = takeFirst(timeframe), interval = takeFirst(interval)}}
| fields timeframe, interval, `Selected window`, `Same window 7 days earlier`'''
_base = f'''timeseries cur = sum({M}, scalar:true), by:{{grail.metric.key}}, {CUR}
| append [timeseries prev = sum({M}, scalar:true), by:{{grail.metric.key}}, {PRV}]
| summarize {{cur = sum(cur), prev = sum(prev)}}, by:{{grail.metric.key}}
| fieldsAdd cur = coalesce(cur, 0.0), prev = coalesce(prev, 0.0)
| fieldsAdd delta = cur - prev
| fieldsAdd change_pct = if(prev == 0, 100.0, else: delta * 100.0 / prev)'''
_cols = "| fields `Metric` = grail.metric.key, `Selected window` = cur, `7 days earlier` = prev, Change = delta, `Change %` = change_pct"
DQ["top"] = _base + "\n| filter not startsWith(grail.metric.key, \"dt.\")\n| sort cur desc\n| limit 20\n" + _cols
DQ["top_chart"] = _base + "\n| filter not startsWith(grail.metric.key, \"dt.\")\n| sort cur desc\n| limit 12\n| fields `Metric` = grail.metric.key, `Selected window` = cur, `7 days earlier` = prev"
DQ["down"] = _base + "\n| filter not startsWith(grail.metric.key, \"dt.\")\n| sort delta asc\n| limit 20\n" + _cols
DQ["up"] = _base + "\n| filter not startsWith(grail.metric.key, \"dt.\")\n| sort delta desc\n| limit 20\n" + _cols
DQ["status"] = _base + '''
| filter not startsWith(grail.metric.key, "dt.")
| fieldsAdd Status = if(cur == 0, "Stopped", else: if(prev == 0, "New", else: if(cur < prev, "Reduced", else: "Increased or flat")))
| summarize {Metrics = count(), `Selected window` = sum(cur), `7 days earlier` = sum(prev)}, by:{Status}
| fieldsAdd Change = `Selected window` - `7 days earlier`
| sort Change asc'''

# ---------------------------------------------------------------------------------------------------------------
# Notebook queries (fixed relative windows, no variables)
# ---------------------------------------------------------------------------------------------------------------
NQ = {}
NQ["billed_type"] = f'''fetch dt.system.events, from:now()-9d
| filter {BILL}
| fieldsAdd us = toTimestamp(usage.start), dp = toLong(data_points)
| summarize {{`Last complete day` = sum(if(us >= now()@d - 1d and us < now()@d, dp, else: 0)), `Same day a week earlier` = sum(if(us >= now()@d - 8d and us < now()@d - 7d, dp, else: 0)), `Last 7 complete days` = sum(if(us >= now()@d - 7d and us < now()@d, dp, else: 0))}}, by:{{`Data type` = metric.type, `Monitoring source` = monitoring_source, Bucket = usage.bucket}}
| fieldsAdd `Change %` = if(`Same day a week earlier` == 0, 100.0, else: (`Last complete day` - `Same day a week earlier`) * 100.0 / `Same day a week earlier`)
| sort `Last 7 complete days` desc'''
NQ["billed_daily"] = f'''fetch dt.system.events, from:now()-16d
| filter {BILL}
| makeTimeseries `Billed datapoints` = sum(toLong(data_points)), interval:1d'''
NQ["by_source"] = f'''timeseries `Last 24h` = sum({M}, scalar:true), by:{{grail.metric.source, grail.metric.type}}, from:now()-24h
| append [timeseries `Same 24h, 7 days earlier` = sum({M}, scalar:true), by:{{grail.metric.source, grail.metric.type}}, from:now()-8d, to:now()-7d]
| summarize {{`Last 24h` = sum(`Last 24h`), `Same 24h, 7 days earlier` = sum(`Same 24h, 7 days earlier`)}}, by:{{grail.metric.source, grail.metric.type}}
| fieldsAdd `Change %` = if(coalesce(`Same 24h, 7 days earlier`, 0.0) == 0, 100.0, else: (coalesce(`Last 24h`, 0.0) - `Same 24h, 7 days earlier`) * 100.0 / `Same 24h, 7 days earlier`)
| fieldsAdd Source = concat(coalesce(grail.metric.source, "(none)"), " / ", grail.metric.type)
| sort `Last 24h` desc
| fields Source, `Last 24h`, `Same 24h, 7 days earlier`, `Change %`'''
NQ["top"] = f'''timeseries cur = sum({M}, scalar:true), by:{{grail.metric.key}}, from:now()-24h
| append [timeseries prev = sum({M}, scalar:true), by:{{grail.metric.key}}, from:now()-8d, to:now()-7d]
| summarize {{cur = sum(cur), prev = sum(prev)}}, by:{{grail.metric.key}}
| filter not startsWith(grail.metric.key, "dt.")
| fieldsAdd cur = coalesce(cur, 0.0), prev = coalesce(prev, 0.0)
| sort cur desc
| limit 25
| fields Metric = grail.metric.key, `Last 24h` = cur, `Same 24h, 7 days earlier` = prev, `Change %` = if(prev == 0, 100.0, else: (cur - prev) * 100.0 / prev)'''
NQ["unused"] = f'''timeseries datapoints_per_day = sum({M}, scalar:true), by:{{grail.metric.key}}, from:now()-24h
| filter not startsWith(grail.metric.key, "dt.")
| lookup [
    fetch dt.system.events, from:now()-90d
    | filter {QLOG} and query_pool != "ALERTING"
    | filter not contains(query_string, "dt.sfm.metrics.ingest.datapoints")
    | fieldsAdd toks = arrayDistinct(splitByPattern(query_string, "[^A-Za-z0-9_.]+"))
    | filter arraySize(toks) <= 60
    | expand tok = toks
    | summarize {{queries_90d = count(), last_queried = max(timestamp)}}, by:{{tok}}
  ], sourceField:grail.metric.key, lookupField:tok, fields:{{queries_90d, last_queried}}
| fieldsAdd usage = if(isNull(queries_90d), "Never queried (90d)", else: if(queries_90d <= 10, "Rarely queried (10 or fewer)", else: "Queried"))
| filter usage != "Queried"
| sort datapoints_per_day desc
| limit 100
| fields Metric = grail.metric.key, usage, datapoints_per_day, queries_90d, last_queried'''
NQ["otel_buckets"] = f'''timeseries datapoints = sum({M}, scalar:true), by:{{grail.metric.key, grail.metric.source}}, from:now()-24h
| filter endsWith(grail.metric.key, "_bucket")
| sort datapoints desc
| limit 25
| fields Metric = grail.metric.key, Source = coalesce(grail.metric.source, "(none)"), `Datapoints, last 24h` = datapoints'''
NQ["query_pool"] = f'''fetch dt.system.events, from:now()-7d
| filter {QLOG}
| summarize {{Queries = count(), `Scanned datapoints` = sum(toLong(scanned_data_points)), `Avg ms` = avg(toLong(execution_duration_ms)), Failed = countIf(status != "SUCCEEDED")}}, by:{{`Query pool` = query_pool}}
| sort Queries desc'''
NQ["cost_center"] = f'''fetch dt.system.events, from:now()-8d
| filter {BILL}
| expand cc = dt.cost.costcenter
| summarize `Billed datapoints` = sum(toLong(cc[data_points])), by:{{`Cost center` = cc[key]}}
| sort `Billed datapoints` desc
| limit 20'''
NQ["detectors"] = '''fetch events, from:now()-30d
| filter event.provider == "METRIC_EVENTS" and event.type == "CUSTOM_ALERT" and dt.settings.schema_id == "builtin:davis.anomaly-detectors"
| summarize {`Alerts opened` = countIf(event.status_transition == "CREATED"), `Last alert` = max(timestamp)}, by:{Detector = event.name}
| sort `Alerts opened` desc
| limit 20'''


def _cut_fields(q):
    """Drop the final `| fields ...` line so a chart variant can pick its own columns."""
    return q.rsplit("\n| fields", 1)[0]


# Chart variants: a chart needs exactly one category column and only the numeric columns it should plot.
NQ["by_source_chart"] = NQ["by_source"] + "\n| limit 12\n| fields Source, `Last 24h`, `Same 24h, 7 days earlier`"
NQ["top_chart"] = _cut_fields(NQ["top"]).replace("| limit 25", "| limit 15") + "\n| fields Metric = grail.metric.key, `Last 24h` = cur, `Same 24h, 7 days earlier` = prev"
NQ["usage_mix"] = NQ["unused"].replace(
    '| filter usage != "Queried"\n| sort datapoints_per_day desc\n| limit 100\n| fields Metric = grail.metric.key, usage, datapoints_per_day, queries_90d, last_queried',
    '| summarize `Datapoints a day` = sum(datapoints_per_day), by:{Usage = usage}\n| sort `Datapoints a day` desc')
NQ["buckets_chart"] = _cut_fields(NQ["otel_buckets"]).replace("| limit 25", "| limit 15") + "\n| fields Metric = grail.metric.key, `Datapoints, last 24h` = datapoints"
NQ["pool_chart"] = NQ["query_pool"] + "\n| fields `Query pool`, Queries"
NQ["detectors_chart"] = NQ["detectors"] + "\n| fields Detector, `Alerts opened`"

# One entry per notebook tile: id -> (title, query, visualization, (category field, [value fields]) or None, height).
# The visualization is chosen from the SHAPE of the result and set explicitly. See references/visualization-guide.md.
NB_TILES = {
    "q-billed": ("Billed datapoints by data type and source", NQ["billed_type"], "table", None, 280),
    "q-daily": ("Billed datapoints per day", NQ["billed_daily"], "barChart", None, 320),
    "q-source": ("Datapoints by source and type: last 24h vs a week earlier", NQ["by_source_chart"], "categoricalBarChart", ("Source", ["Last 24h", "Same 24h, 7 days earlier"]), 420),
    "q-source-t": ("Datapoints by source and type, with change", NQ["by_source"], "table", None, 340),
    "q-top-bar": ("Top 15 metrics: last 24h vs a week earlier", NQ["top_chart"], "categoricalBarChart", ("Metric", ["Last 24h", "Same 24h, 7 days earlier"]), 480),
    "q-top": ("Top 25 metrics, with change", NQ["top"], "table", None, 560),
    "q-usage-mix": ("Share of datapoints by how the metric is used", NQ["usage_mix"], "donutChart", None, 340),
    "q-unused": ("Never or rarely queried, still arriving", NQ["unused"], "table", None, 560),
    "q-buckets": ("Heaviest histogram bucket series", NQ["buckets_chart"], "categoricalBarChart", ("Metric", ["Datapoints, last 24h"]), 420),
    "q-pool": ("Share of metric queries by source, last 7 days", NQ["pool_chart"], "donutChart", None, 340),
    "q-pool-t": ("Metric queries by source: scan and failures", NQ["query_pool"], "table", None, 280),
    "q-cc": ("Billed datapoints by cost center, last 8 days", NQ["cost_center"], "pieChart", None, 380),
    "q-det": ("Top 20 detectors by alerts opened, last 30 days", NQ["detectors_chart"], "categoricalBarChart", ("Detector", ["Alerts opened"]), 520),
    "q-det-t": ("Detectors with last alert time", NQ["detectors"], "table", None, 480),
}


def viz_settings(viz, axes):
    """visualizationSettings for a tile. Tables use the defaults, time series get a legend, category bars map their axes."""
    vs = {"autoSelectVisualization": False}
    if viz == "categoricalBarChart" and axes:
        vs["chartSettings"] = {"categoricalBarChartSettings": {"categoryAxis": [axes[0]], "valueAxis": list(axes[1])}}
    elif viz in ("lineChart", "barChart", "areaChart"):
        vs["chartSettings"] = {"legend": {"position": "bottom", "showLegend": True}}
    else:
        vs["chartSettings"] = {}
    return vs


RESULTS = {}   # tile id -> records, filled by --embed-results so tiles are saved the way the UI saves them


def _iso(v):
    return isinstance(v, str) and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(Z|[+-]\d\d:\d\d)", v) is not None


def _dql_type(name, v):
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, dict) and "start" in v and "end" in v:
        return "timeframe"
    if isinstance(v, list):
        return "array"
    if name == "interval" and isinstance(v, str) and v.isdigit():
        return "duration"
    if _iso(v):
        return "timestamp"
    if isinstance(v, int):
        return "long"
    if isinstance(v, float):
        return "double"
    if isinstance(v, str) and re.fullmatch(r"-?\d+", v):
        return "long"
    if isinstance(v, str) and re.fullmatch(r"-?\d+\.\d+([eE][+-]?\d+)?", v):
        return "double"
    return "string"


def make_result(query, recs):
    """A cached query result in the shape the notebook UI stores, so a tile opens with its saved visualization."""
    import datetime as _dt
    mappings = {}
    for r in recs[:50]:
        for k, v in r.items():
            if v is None or k in mappings:
                continue
            t = _dql_type(k, v)
            if t == "array":
                inner = next((x for x in v if x is not None), 0)
                mappings[k] = {"type": "array", "types": [{"indexRange": [0, max(len(v) - 1, 0)], "mappings": {"element": {"type": _dql_type("", inner) if not isinstance(inner, str) else "double"}}}]}
            else:
                mappings[k] = {"type": t}
    for r in recs:
        for k, v in r.items():
            k_t = mappings.get(k, {}).get("type")
            if k_t in ("long",) and isinstance(v, int) and not isinstance(v, bool):
                r[k] = str(v)
    qs = {"defaultSamplingRatio": 10, "defaultScanLimitGbytes": 500, "enableSampling": False, "maxResultMegaBytes": 1, "maxResultRecords": 1000}
    inp = {"filterSegments": [], "querySettings": qs, "timeframe": {"from": "now()-24h", "to": "now()"}, "value": query.strip()}
    return {"code": 200, "dateTime": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"), "input": inp, "notifications": [], "querySettings": qs,
            "value": {"metadata": {"grail": {"dqlVersion": "V1_0", "locale": "en-US", "notifications": [], "query": query.strip(), "sampled": False, "timezone": "UTC"}},
                      "records": recs, "types": [{"indexRange": [0, max(len(recs) - 1, 0)], "mappings": mappings}]}}


def _isnum(v):
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    return isinstance(v, str) and re.fullmatch(r"-?\d+(\.\d+)?([eE][+-]?\d+)?", v) is not None


def shape_problem(viz, recs, axes=None):
    """Return why a result does not suit its visualization, or None when it does."""
    if not recs:
        return "no rows"
    r0 = recs[0]
    strs = [k for k, v in r0.items() if isinstance(v, str) and not _isnum(v) and k != "interval"]
    nums = [k for k, v in r0.items() if _isnum(v) and k != "interval"]
    if viz in ("categoricalBarChart", "pieChart", "donutChart"):
        if len(strs) != 1:
            return f"needs exactly one category column, found {len(strs)}: {strs}"
        if not nums:
            return "needs at least one numeric column"
        if axes:
            missing = [f for f in [axes[0], *axes[1]] if f not in r0]
            if missing:
                return f"axis fields missing from the result: {missing}"
    elif viz in ("lineChart", "barChart", "areaChart"):
        if not any(isinstance(v, list) for v in r0.values()):
            return "needs a time series (an array column), found none"
    elif viz == "singleValue" and len(recs) != 1:
        return f"single value needs one row, found {len(recs)}"
    return None


QS = "defaultSamplingRatio: 10\ndefaultScanLimitGbytes: 500\nenableSampling: false\nmaxResultMegaBytes: 1\nmaxResultRecords: 1000"


def mdtable(rows, heads):
    out = ["| " + " | ".join(heads) + " |", "|" + "---|" * len(heads)]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def mm(n):
    return f"{n/1e6:,.1f}M"


# ---------------------------------------------------------------------------------------------------------------
# Notebook
# ---------------------------------------------------------------------------------------------------------------
def build_notebook(F_, customer, suffix="", diagnostics=False, NB_VER=NB_VERSION):
    def md(i, t):
        return f"    - id: {i}\n      type: markdown\n      markdown: |-\n{textwrap.indent(t.strip(), '        ')}\n"

    def dql(i, mode=None, tile=None, rkey=None, title_prefix=""):
        """mode: plain (settings only), ui (what the UI writes for a new table tile), marker (plain plus a success state),
        result (plain plus a success state and the cached result, which is how a UI-saved tile looks)."""
        title, q, viz, axes, h = tile or NB_TILES[i]
        rkey = rkey or i
        mode = mode or ("result" if rkey in RESULTS else "plain")
        vs = viz_settings(viz, axes)
        if mode == "ui" and viz == "table":
            vs = {"table": {"hideColumnsForLargeResults": True}, "autoSelectVisualization": True, "chartSettings": {}}
        vs_txt = textwrap.indent(yaml.safe_dump(vs, default_flow_style=False, sort_keys=False).rstrip(), "          ")
        extra = ""
        if mode in ("marker", "result"):
            extra += "        state: success\n"
        if mode == "result" and rkey in RESULTS:
            extra += "        result: " + json.dumps(make_result(q, [dict(r) for r in RESULTS[rkey]]), separators=(",", ":")) + "\n"
        return f"""    - id: {i}
      type: dql
      title: "{title_prefix}{title}"
      showTitle: true
      showInput: false
      height: {h}
      drilldownPath: []
      filterSegments: []
      previousFilterSegments: []
      state:
        davis:
          davisVisualization:
            isAvailable: true
          includeLogs: true
        input:
          timeframe:
            from: now()-24h
            to: now()
          value: |-
{textwrap.indent(q.strip(), '            ')}
          querySettings:
{textwrap.indent(QS, '            ')}
        querySettings:
{textwrap.indent(QS, '          ')}
        visualization: {viz}
        visualizationSettings:
{vs_txt}
{extra}"""

    b = F_["billing"]; t = F_["totals"]; uc = F_["usage_classes"]
    name = f"{NB_PREFIX} ({customer}){suffix}"
    o = f"name: \"{name}\"\ntype: notebook\ncontent:\n  version: \"{NB_VER}\"\n  defaultSegments: []\n  defaultTimeframe:\n    from: now()-24h\n    to: now()\n  sections:\n"
    o += md("hdr", f"""
# Metric ingest findings: {customer}
Where metric volume comes from, how it is used, and what can be reduced or standardized. Live tiles use fixed windows: the last 24 hours against the 24 hours that ended exactly 7 days earlier. For a window you pick yourself, use the dashboard "{DB_NAME}".

**Measures.** Billed ingest is read from billing usage records (Metrics - Ingest & Process). Ingested datapoints come from `{M}`. Billing records arrive a few hours after the usage, so billed tiles use complete days.
""")
    o += md("sum", f"""
## 1. Headline
| | |
|---|---|
| Billed datapoints, last complete day | {mm(b['totals']['d1'])} |
| Same day a week earlier | {mm(b['totals']['d8'])} ({b['totals']['pct_d1_vs_d8']}%) |
| Billable metric keys receiving data | {t['billable_keys']:,} ({mm(t['c24_billable'])} datapoints a day) |
| Never used, still arriving | {uc['No usage found']['keys']:,} keys, {mm(uc['No usage found']['c24'])} a day |
| Rarely used (10 or fewer queries in 90 days) | {uc['Rarely used']['keys']:,} keys, {mm(uc['Rarely used']['c24'])} a day |
| Read only by API clients | {uc['Used by API clients only']['keys']:,} keys, {mm(uc['Used by API clients only']['c24'])} a day |
""")
    o += md("h2", "## 2. What is billed\nEvery data type and monitoring source that bills under Metrics - Ingest & Process.")
    o += dql("q-billed")
    o += dql("q-daily")
    o += md("h3", "## 3. Where it comes from\nIngest by metric source and type, last 24 hours against the same 24 hours a week earlier.")
    o += dql("q-source") + dql("q-source-t")
    o += dql("q-top-bar") + dql("q-top")
    o += md("h4", "## 4. Used or not\nMetrics that nothing reads, or that were queried 10 times or fewer in 90 days, excluding detector runs (which execute every minute and make every metric look used).")
    o += dql("q-usage-mix") + dql("q-unused")
    o += md("h5", "## 5. Histograms and OpenTelemetry\nEach `_bucket` key is one series per bucket boundary. Native histograms send one datapoint per series.")
    o += dql("q-buckets")
    if F_["probes"]:
        rows = [(p["key"], f"{p['series']:,}", f"{p['interval_s']}s", ", ".join(f"{d['name']} ({d['distinct']:,})" for d in p["dims_view"][:3]), mm(p["c24"])) for p in F_["probes"]]
        o += md("h5b", "### Measured reporting interval and labels\n" + mdtable(rows, ["Metric", "Series", "Reporting interval", "Largest labels (distinct values)", "Datapoints a day"]))
    o += md("h6", "## 6. Who reads metrics (Metric - Query)\nDetector runs and API clients drive most metric queries. Metrics are not billed as a separate query type unless the tenant shows one in billing usage.")
    o += dql("q-pool") + dql("q-pool-t")
    o += md("h7", "## 7. Attribution\nBilled datapoints by cost center. Volume without a cost center cannot be charged back to a team.")
    o += dql("q-cc")
    if "detectors" in F_:
        d = F_["detectors"]
        o += md("h8", f"""
## 8. Anomaly detectors
{d['total']:,} detectors configured, {d['enabled']:,} enabled, {d['fired_30d']:,} opened an alert in the last 30 days. {d['metric_based']:,} are metric based and reduce to {d['templates']:,} templates ({d['detectors_in_copies']:,} are copies of another). They run about {d['evaluations_per_day']/1e6:,.1f}M evaluations a day.
""")
        o += dql("q-det") + dql("q-det-t")
    plan = "\n".join(f"- **{x['id']} {x['title']}** ({x['category']}, effort {x['effort']}): {x['keys']:,} {x.get('unit','metric keys')}, {mm(x['dp_day'])} datapoints a day" for x in F_["opportunities"] if x["dp_day"] or x["keys"])
    o += md("hplan", "## 9. Opportunities from this analysis\n" + plan + "\n\nThe written report has the remediation steps and the phased plan.")
    if diagnostics:
        o += md("hdiag", """
## Visualization diagnostics (remove after validation)
The same table stored four ways. Open this notebook without changing anything and note which tiles open as a Table and which as Raw.
- A: settings only (what earlier notebooks used)
- B: the settings the UI writes for a new table tile
- C: settings plus a success state
- D: settings, a success state and a cached result (how a UI-saved tile looks)
""")
        base = ("diagnostic", NQ["billed_type"], "table", None, 240)
        for sid, mode, label in (("diag-a", "plain", "A"), ("diag-b", "ui", "B"), ("diag-c", "marker", "C"), ("diag-d", "result", "D")):
            o += dql(sid, mode=mode, tile=base, rkey="q-billed", title_prefix=f"Diagnostic {label}: ")
    yaml.safe_load(o)
    return name, o


# ---------------------------------------------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------------------------------------------
def build_dashboard(db_version=DB_VERSION):
    G, R = "#2f6862", "#c62239"
    DAV = {"enabled": False, "davisVisualization": {"isAvailable": True}}
    tiles, layouts, n = {}, {}, [0]

    def add(x, y, w, h, tile):
        n[0] += 1
        k = str(n[0]); tiles[k] = tile; layouts[k] = {"x": x, "y": y, "w": w, "h": h}

    def data(x, y, w, h, title, q, viz, vs=None):
        vs = dict(vs or {}); vs.setdefault("autoSelectVisualization", False)
        add(x, y, w, h, {"title": title, "type": "data", "query": q, "visualization": viz, "visualizationSettings": vs, "davis": DAV})

    def banner(y, text):
        add(0, y, 24, 1, {"title": "", "type": "data", "query": f'data record(a="{text}")', "visualization": "singleValue",
            "visualizationSettings": {"autoSelectVisualization": False,
              "singleValue": {"recordField": "a", "label": "a", "labelMode": "none", "isIconVisible": False, "colorThresholdTarget": "background"},
              "thresholds": [{"id": 1, "field": "a", "title": "", "isEnabled": True, "rules": [{"id": 0, "comparator": "!=", "value": "0", "label": "",
                              "color": {"Default": "var(--dt-colors-charts-categorical-color-01-default, #134fc9)"}}]}]}, "davis": DAV})

    def sv(field, label, rules=None, dec=1, pct=False):
        s = {"singleValue": {"recordField": field, "label": label, "labelMode": "label", "colorThresholdTarget": "background" if rules else "value"}}
        if rules:
            s["coloring"] = {"colorRules": [{"colorMode": "custom-color", "comparator": c, "customColor": {"Default": col}, "field": field, "value": v} for c, col, v in rules]}
        uo = {"identifier": field, "unitCategory": "percentage" if pct else "unspecified", "baseUnit": "percent" if pct else "none", "displayUnit": None, "decimals": dec, "suffix": "", "delimiter": True}
        s["unitsOverrides"] = [uo]
        return s

    def cells(field):
        return {"coloring": {"colorRules": [{"colorMode": "custom-color", "comparator": ">", "customColor": {"Default": c}, "field": field, "value": v} for c, v in [(G, -100000), (R, 0)]]}}

    good_bad = [(">", G, -100000), (">", R, 0)]       # green when lower than a week earlier, red when higher
    add(0, 0, 24, 3, {"title": "", "type": "markdown", "content": "## Metric ingest: selected window vs the same window 7 days earlier\nChange the dashboard timeframe (top right). Every tile compares it with a window of the SAME LENGTH shifted back exactly 7 days: 24 hours against 24 hours, 1 hour against 1 hour. Green means lower than a week earlier.\n\n**Billed** tiles read billing usage records and match them on the usage period; records arrive a few hours late, so avoid a window that ends in the last 6 hours. **Ingested** tiles read the live datapoint measure and are close to billed volume."})
    data(0, 3, 24, 2, "Windows being compared", DQ["win"], "table")
    banner(5, "BILLED METRIC INGEST (Metrics - Ingest & Process)")
    data(0, 6, 6, 4, "Billed: change vs 7 days earlier", DQ["billed_head"], "singleValue", sv("change_pct", "Change %", good_bad, 1, True))
    data(6, 6, 6, 4, "Billed: selected window", DQ["billed_head"], "singleValue", sv("cur", "Billed datapoints", None, 0))
    data(12, 6, 6, 4, "Billed: 7 days earlier", DQ["billed_head"], "singleValue", sv("prev", "Billed datapoints, 7 days earlier", None, 0))
    data(18, 6, 6, 4, "Billed: absolute change", DQ["billed_head"], "singleValue", sv("delta", "Datapoint change", [(">", G, -1e15), (">", R, 0)], 0))
    data(0, 10, 24, 6, "Billed datapoints by data type and monitoring source", DQ["billed_by_type"], "table", cells("Change %"))
    banner(16, "INGESTED DATAPOINTS (live)")
    data(0, 17, 6, 4, "Ingested: change vs 7 days earlier", DQ["ingest_head"], "singleValue", sv("change_pct", "Change %", good_bad, 1, True))
    data(6, 17, 6, 4, "Ingested: selected window", DQ["ingest_head"], "singleValue", sv("cur", "Datapoints", None, 0))
    data(12, 17, 6, 4, "Ingested: 7 days earlier", DQ["ingest_head"], "singleValue", sv("prev", "Datapoints, 7 days earlier", None, 0))
    data(18, 17, 6, 4, "Ingested: absolute change", DQ["ingest_head"], "singleValue", sv("delta", "Datapoint change", [(">", G, -1e15), (">", R, 0)], 0))
    data(0, 21, 24, 7, "Datapoints over time: selected window vs 7 days earlier", DQ["overlay"], "lineChart", {"chartSettings": {"legend": {"position": "bottom", "showLegend": True}}})
    data(0, 28, 12, 7, "By metric source: selected window vs 7 days earlier", DQ["by_source_chart"], "categoricalBarChart",
         {"chartSettings": {"categoricalBarChartSettings": {"categoryAxis": ["Source"], "valueAxis": ["Selected window", "7 days earlier"]}}})
    data(12, 28, 12, 7, "By metric source, with % change", DQ["by_source"], "table", cells("Change %"))
    banner(35, "TOP METRICS")
    data(0, 36, 12, 10, "Top 12 metrics: selected window vs 7 days earlier", DQ["top_chart"], "categoricalBarChart",
         {"chartSettings": {"categoricalBarChartSettings": {"categoryAxis": ["Metric"], "valueAxis": ["Selected window", "7 days earlier"]}}})
    data(12, 36, 12, 10, "Top 20 metrics, with % change", DQ["top"], "table", cells("Change %"))
    banner(46, "WHAT CHANGED")
    data(0, 47, 12, 9, "Biggest reductions (-100% = stopped)", DQ["down"], "table", cells("Change %"))
    data(12, 47, 12, 9, "Biggest increases", DQ["up"], "table", cells("Change %"))
    data(0, 56, 24, 4, "Metrics grouped by what happened", DQ["status"], "table")
    d = {"name": DB_NAME, "type": "dashboard",
         "content": {"version": db_version, "annotations": [], "importedWithCode": False,
                     "settings": {"defaultTimeframe": {"enabled": True, "value": {"from": "now()-1d@d", "to": "now()@d"}}},
                     "layouts": layouts, "tiles": tiles}}
    return d


def literal(dql, f="2026-01-14T00:00:00Z", t="2026-01-15T00:00:00Z"):
    """Replace the picker variables with literals so a dashboard query can be tested from the command line."""
    return dql.replace("$dt_timeframe_from", f'"{f}"').replace("$dt_timeframe_to", f'"{t}"')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--customer", required=True)
    ap.add_argument("--embed-results", action="store_true", help="NOT RECOMMENDED: embeds a synthesized cached result. It produced tiles showing [object Object]. The schema version is what fixes the default view.")
    ap.add_argument("--diagnostics", action="store_true", help="add a section that stores one table four ways (a troubleshooting aid, off by default)")
    ap.add_argument("--name-suffix", default="", help="text added to the notebook name, for example ' - Validation'")
    ap.add_argument("--only", choices=("notebook", "dashboard", "both"), default="both")
    ap.add_argument("--test-queries", action="store_true", help="run every notebook and dashboard query once and report errors")
    ap.add_argument("--apply", action="store_true", help="create the notebook and dashboard in the tenant")
    ap.add_argument("--yes-write", action="store_true", help="the user has agreed to a temporary write on this tenant")
    a = ap.parse_args()
    F_ = json.load(open(os.path.join(a.dir, "facts.json"), encoding="utf-8"))
    ctx = F_["meta"]["context"]
    os.makedirs(os.path.join(a.dir, "assets"), exist_ok=True)
    if a.embed_results:
        tt = Tenant(ctx, a.dir)
        for tid, (title, q, viz, axes, h) in NB_TILES.items():
            RESULTS[tid] = tt.q(f"embed_{tid}", q, save=False, timeout=170)
            print(f"embedded {tid}: {len(RESULTS[tid])} rows")
        for e in tt.errors:
            print("ERROR", e)
    nb_ver, db_ver = detect_versions(a.dir)
    nb_name, nb_yaml = build_notebook(F_, a.customer, a.name_suffix, a.diagnostics, nb_ver)
    nb_path = os.path.join(a.dir, "assets", "findings_notebook.yaml")
    open(nb_path, "w", encoding="utf-8").write(nb_yaml)
    db = build_dashboard(db_ver)
    db_path = os.path.join(a.dir, "assets", "compare_dashboard.yaml")
    yaml.safe_dump(db, open(db_path, "w", encoding="utf-8"), sort_keys=False, width=1000, allow_unicode=True)
    print(f"wrote {nb_path} and {db_path} ({len(db['content']['tiles'])} dashboard tiles)")

    if a.test_queries:
        t = Tenant(ctx, a.dir)
        bad = 0
        # two window lengths prove the previous window follows the selected length
        for label, f, to in (("24h", "2026-01-14T00:00:00Z", "2026-01-15T00:00:00Z"), ("1h", "2026-01-14T10:00:00Z", "2026-01-14T11:00:00Z")):
            import datetime as _dt
            now = _dt.datetime.now(_dt.timezone.utc)
            f2 = (now - _dt.timedelta(days=2)).strftime("%Y-%m-%dT%H:00:00Z")
            to2 = (now - _dt.timedelta(days=2) + _dt.timedelta(hours=24 if label == "24h" else 1)).strftime("%Y-%m-%dT%H:00:00Z")
            for k, q in DQ.items():
                r = t.q(f"test_dash_{label}_{k}", literal(q, f2, to2), save=False, timeout=170)
                viz = {"by_source_chart": "categoricalBarChart", "top_chart": "categoricalBarChart", "overlay": "lineChart"}.get(k)
                prob = shape_problem(viz, r) if viz else None
                print(f"dashboard[{label}] {k}: {len(r)} rows" + (f"  SHAPE PROBLEM: {prob}" if prob else ""))
                if prob:
                    bad += 1
        for tid, (title, q, viz, axes, h) in NB_TILES.items():
            r = t.q(f"test_nb_{tid}", q, save=False, timeout=170)
            prob = shape_problem(viz, r, axes)
            print(f"notebook {tid} [{viz}]: {len(r)} rows" + (f"  SHAPE PROBLEM: {prob}" if prob else ""))
            if prob:
                bad += 1
        for e in t.errors:
            print("ERROR", e); bad += 1
        print("query test:", "FAILED" if bad else "ok")

    if a.apply:
        if not a.yes_write:
            sys.exit("Refusing to write: pass --yes-write only after the user has agreed to a temporary write on this tenant.")
        orig = safety_level(ctx)
        print(f"safety level is {orig}; raising to readwrite-mine for the apply, then restoring")
        created = []
        try:
            if orig != "readwrite-mine" and orig not in ("readwrite-all", "dangerously-unrestricted"):
                if not set_safety(ctx, "readwrite-mine"):
                    sys.exit("could not raise the safety level")
            for path in [x for x, w in ((nb_path, "notebook"), (db_path, "dashboard")) if a.only in (w, "both")]:
                p = subprocess.run(["dtctl", "apply", "-f", path, "--plain", "--context", ctx], capture_output=True, text=True, encoding="utf-8", errors="replace")
                print(p.stdout.strip()[:600], p.stderr.strip()[:300])
                try:
                    j = json.loads(p.stdout)
                    created.append(j.get("result", {}))
                except ValueError:
                    pass
        finally:
            if orig and safety_level(ctx) != orig:
                set_safety(ctx, orig)
            print(f"safety level now: {safety_level(ctx)} (was {orig})")
        json.dump(created, open(os.path.join(a.dir, "assets", "created.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
