#!/usr/bin/env python3
"""Collect raw metric-ingest and metric-query data from ONE Dynatrace tenant via dtctl.

    uv run --with pyyaml python -X utf8 collect.py --context "<ctx>" --out <dir> [options]

Writes <out>/raw/*.json (query results), <out>/corpus/* (saved config, for usage evidence) and <out>/meta.json.
Everything runs sequentially. Run one tenant at a time; to cover several tenants call this once per tenant.
"""
import argparse, datetime, json, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dtq import Tenant, contexts, num, safety_level  # noqa: E402

M = "dt.sfm.metrics.ingest.datapoints"
BILL = 'event.kind == "BILLING_USAGE_EVENT" and event.type == "Metrics - Ingest & Process"'
QLOG = 'event.kind == "QUERY_EXECUTION_EVENT" and table == "metrics"'
SKIP_SELF = 'not contains(query_string, "dt.sfm.metrics.ingest.datapoints") and not contains(query_string, "BILLING_USAGE_EVENT")'

Q = {}
# ---- what is billed -------------------------------------------------------------------------------------
Q["billing_types"] = f'''fetch dt.system.events, from:now()-30d
| filter event.kind == "BILLING_USAGE_EVENT" and matchesValue(event.type, "Metric*")
| summarize {{events = count(), first_seen = min(timestamp), last_seen = max(timestamp)}}, by:{{event.type}}'''
Q["billing_other_sample"] = '''fetch dt.system.events, from:now()-30d
| filter event.kind == "BILLING_USAGE_EVENT" and matchesValue(event.type, "Metric*") and event.type != "Metrics - Ingest & Process"
| limit 3'''
Q["billing_by_type"] = f'''fetch dt.system.events, from:now()-9d
| filter {BILL}
| fieldsAdd us = toTimestamp(usage.start), dp = toLong(data_points)
| summarize {{d1 = sum(if(us >= now()@d - 1d and us < now()@d, dp, else: 0)), d8 = sum(if(us >= now()@d - 8d and us < now()@d - 7d, dp, else: 0)), d7 = sum(if(us >= now()@d - 7d and us < now()@d, dp, else: 0))}}, by:{{metric.type, monitoring_source, usage.bucket}}
| sort d7 desc'''
Q["billing_daily"] = f'''fetch dt.system.events, from:now()-16d
| filter {BILL}
| fieldsAdd us = toTimestamp(usage.start), dp = toLong(data_points)
| summarize dp = sum(dp), by:{{day = formatTimestamp(us, format:"yyyy-MM-dd")}}
| sort day asc'''
Q["billing_costcenter"] = f'''fetch dt.system.events, from:now()-8d
| filter {BILL}
| expand cc = dt.cost.costcenter
| summarize dp = sum(toLong(cc[data_points])), by:{{cost_center = cc[key]}}
| sort dp desc
| limit 40'''
Q["billing_product"] = f'''fetch dt.system.events, from:now()-8d
| filter {BILL}
| expand pr = dt.cost.product
| summarize dp = sum(toLong(pr[data_points])), by:{{cost_product = pr[key]}}
| sort dp desc
| limit 40'''
# ---- what is ingested -----------------------------------------------------------------------------------
DIMS = "grail.metric.source, grail.metric.type, grail.monitoring_source"
Q["sfm_by_source"] = f'''timeseries cur = sum({M}, scalar:true), by:{{{DIMS}}}, from:now()-24h
| append [timeseries prev = sum({M}, scalar:true), by:{{{DIMS}}}, from:now()-8d, to:now()-7d]
| summarize {{cur = sum(cur), prev = sum(prev)}}, by:{{{DIMS}}}
| sort cur desc'''
Q["sfm_daily"] = f'''timeseries d = sum({M}), interval:1d, from:now()-15d
| fields timeframe, interval, d'''
KD = "grail.metric.key, grail.metric.source, grail.metric.type"
Q["keys"] = f'''timeseries d7 = sum({M}, scalar:true), by:{{{KD}}}, from:now()-7d
| append [timeseries c24 = sum({M}, scalar:true), by:{{{KD}}}, from:now()-24h]
| append [timeseries p24 = sum({M}, scalar:true), by:{{{KD}}}, from:now()-8d, to:now()-7d]
| summarize {{d7 = sum(d7), c24 = sum(c24), p24 = sum(p24)}}, by:{{{KD}}}
| sort d7 desc'''
# ---- who reads metrics (Metric - Query side) ------------------------------------------------------------
Q["query_by_pool"] = f'''fetch dt.system.events, from:now()-7d
| filter {QLOG}
| summarize {{queries = count(), users = countDistinctApprox(user.email), scanned_dp = sum(toLong(scanned_data_points)), scanned_bytes = sum(toLong(scanned_bytes)), ondemand_bytes = sum(toLong(`scanned_bytes.on_demand`)), avg_ms = avg(toLong(execution_duration_ms)), p95_ms = percentile(toLong(execution_duration_ms), 95), failed = countIf(status != "SUCCEEDED")}}, by:{{query_pool}}
| sort queries desc'''
Q["query_top_runs"] = f'''fetch dt.system.events, from:now()-7d
| filter {QLOG} and query_pool != "ALERTING"
| summarize {{runs = count(), scanned_dp = sum(toLong(scanned_data_points)), users = countDistinctApprox(user.email), pool = takeFirst(query_pool)}}, by:{{q = substring(query_string, from:0, to:300)}}
| sort runs desc
| limit 40'''
Q["query_top_scan"] = f'''fetch dt.system.events, from:now()-7d
| filter {QLOG} and query_pool != "ALERTING"
| summarize {{runs = count(), scanned_dp = sum(toLong(scanned_data_points)), users = countDistinctApprox(user.email), pool = takeFirst(query_pool)}}, by:{{q = substring(query_string, from:0, to:300)}}
| sort scanned_dp desc
| limit 40'''
Q["query_api_users"] = f'''fetch dt.system.events, from:now()-7d
| filter {QLOG} and query_pool == "API"
| summarize {{runs = count(), scanned_dp = sum(toLong(scanned_data_points)), distinct_queries = countDistinctApprox(query_string)}}, by:{{user.email}}
| sort runs desc
| limit 25'''
Q["query_alerting"] = f'''fetch dt.system.events, from:now()-7d
| filter {QLOG} and query_pool == "ALERTING"
| summarize runs = count(), by:{{query_string}}
| limit 30000'''


def usage_q(days):
    return f'''fetch dt.system.events, from:now()-{days}d
| filter {QLOG} and query_pool != "ALERTING"
| filter {SKIP_SELF}
| fieldsAdd toks = arrayDistinct(splitByPattern(query_string, "[^A-Za-z0-9_.]+"))
| filter arraySize(toks) <= 60
| expand tok = toks
| summarize {{q = count(), last_q = max(timestamp)}}, by:{{tok, query_pool}}'''


def wildcard_q(days):
    return f'''fetch dt.system.events, from:now()-{days}d
| filter {QLOG} and query_pool != "ALERTING" and contains(query_string, "*")
| filter {SKIP_SELF}
| summarize runs = count(), by:{{query_string}}
| limit 20000'''


Q["detector_triggers"] = '''fetch events, from:now()-30d
| filter event.provider == "METRIC_EVENTS" and event.type == "CUSTOM_ALERT" and dt.settings.schema_id == "builtin:davis.anomaly-detectors"
| summarize {triggers = countIf(event.status_transition == "CREATED"), last_seen = max(timestamp)}, by:{dt.settings.object_id}'''

SCHEMAS = [
    "builtin:davis.anomaly-detectors", "builtin:anomaly-detection.metric-events", "builtin:monitoring.slo",
    "builtin:metric.query", "builtin:openpipeline.metrics.pipelines", "builtin:openpipeline.metrics.routing",
    "builtin:openpipeline.metrics.ingest-sources", "builtin:openpipeline.metrics.pipeline-groups",
    "builtin:custom-metrics", "builtin:histogram-metrics", "builtin:opentelemetry-metrics", "builtin:metric.metadata",
    "builtin:alerting.profile", "builtin:problem.notifications", "builtin:anomaly-detection.kubernetes.workload",
    "builtin:anomaly-detection.kubernetes.node", "builtin:anomaly-detection.kubernetes.namespace",
    "builtin:anomaly-detection.kubernetes.cluster", "builtin:anomaly-detection.kubernetes.pvc",
    "builtin:logmonitoring.schemaless-log-metric", "builtin:unified-services-endpoint-metrics",
]


def log(m):
    print(time.strftime("%H:%M:%S"), m, flush=True)


def fetch_config(t, corpus):
    """Export dashboards, notebooks, workflows, SLOs and metric-related settings as text for usage evidence."""
    import yaml
    os.makedirs(corpus, exist_ok=True)

    def decode(txt):
        try:
            d = yaml.safe_load(txt)
        except Exception:
            return txt
        if isinstance(d, dict):
            c = d.get("content")
            if isinstance(c, list) and c and all(isinstance(i, int) for i in c):
                try:
                    d["content"] = bytes(c).decode("utf-8")
                except Exception:
                    pass
            return json.dumps(d, default=str)
        return txt

    for s in SCHEMAS:
        f = os.path.join(corpus, "settings__" + s.replace(":", "_") + ".txt")
        if os.path.exists(f):
            continue
        j = t.get_json(["settings", "--schema", s])
        if j is not None:
            open(f, "w", encoding="utf-8").write(json.dumps(j))
    for kind, sub in (("slos", "slo"), ("workflows", "workflow"), ("notebooks", "notebook"), ("dashboards", "dashboard")):
        items = t.get_json([kind]) or []
        items = [(x.get("id"), x.get("name", "")) for x in items if isinstance(x, dict) and x.get("id")]
        log(f"config: {kind} {len(items)}")
        for n, (i, name) in enumerate(items):
            f = os.path.join(corpus, f"{kind}__{i}.txt")
            if os.path.exists(f):
                continue
            p = t._run(["get", sub, i, "-o", "yaml", "--plain"], 120)
            if p.returncode != 0 or not p.stdout.strip():
                p = t._run(["get", sub, i, "-o", "json", "--plain"], 120)
            open(f, "w", encoding="utf-8").write(f"NAME: {name}\nID: {i}\n" + decode(p.stdout))
            if n and n % 100 == 0:
                log(f"config: {kind} {n}/{len(items)}")


def probe_series(t, key, hours=24, lag_hours=3):
    """Estimate series count, per-dimension cardinality and reporting interval for one metric key.

    The ingest measure for some keys lands hours late, so both counts use the same window ending lag_hours ago.
    Every non-dt.* dimension is used: a partial dimension list undercounts series and inflates the interval.
    Series are counted in a 30 minute slice (not the whole window) so short-lived pods do not inflate the count.
    """
    recs = t.q("probe_meta", f'metrics from:now()-2h\n| filter metric.key == "{key}"\n| limit 50', save=False, timeout=90)
    dims = []
    for r in recs:
        for k, v in r.items():
            if v is not None and k != "metric.key" and not k.startswith("dt.") and k not in dims:
                dims.append(k)
    dims = dims[:80]
    if not dims:
        return None
    win = f"from:now()-{(hours + lag_hours) * 60}m, to:now()-{lag_hours * 60}m"          # datapoints
    swin = f"from:now()-{lag_hours * 60 + 30}m, to:now()-{lag_hours * 60}m"             # series active in a 30 minute slice
    by = ", ".join(f"`{d}`" for d in dims)
    cnt = ", ".join(f"c{i} = countDistinct(`{d}`)" for i, d in enumerate(dims))
    rows = t.q("probe_series", f'timeseries x = avg(`{key}`, scalar:true), by:{{{by}}}, {swin}\n| summarize {{series = count(), {cnt}}}', save=False, timeout=170)
    dp = t.q("probe_dp", f'timeseries d = sum({M}, scalar:true, filter:{{grail.metric.key == "{key}"}}), {win}', save=False, timeout=90)
    if not rows or not dp:
        return None
    series = num(rows[0].get("series"))
    d = num(dp[0].get("d"))
    if series <= 0 or d <= 0:
        return None
    return {"key": key, "series": int(series), "datapoints_window": int(d), "window_s": hours * 3600,
            "est_interval_s": round(hours * 3600 * series / d, 1),
            "dims": [{"name": dm, "distinct": int(num(rows[0].get(f"c{i}")))} for i, dm in enumerate(dims)]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--context", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--usage-days", type=int, default=90, help="query-log lookback for usage evidence (max 90)")
    ap.add_argument("--otel-top", type=int, default=15, help="metrics to probe for series count and reporting interval")
    ap.add_argument("--probe-sources", default="opentelemetry", help="comma list of grail.metric.source values to probe")
    ap.add_argument("--skip-config", action="store_true", help="skip dashboards/notebooks/workflows/settings export")
    ap.add_argument("--skip-probe", action="store_true")
    a = ap.parse_args()

    t = Tenant(a.context, a.out)
    env = next((c.get("Environment") for c in contexts() if c.get("Name") == a.context), "")
    meta = {"context": a.context, "environment": env, "safety_level": safety_level(a.context), "started": datetime.datetime.now(datetime.timezone.utc).isoformat(), "args": vars(a)}
    log(f"tenant {a.context} {env} safety={meta['safety_level']}")

    steps = [("billing_types", Q["billing_types"]), ("billing_other_sample", Q["billing_other_sample"]),
             ("billing_by_type", Q["billing_by_type"]), ("billing_daily", Q["billing_daily"]),
             ("billing_costcenter", Q["billing_costcenter"]), ("billing_product", Q["billing_product"]),
             ("sfm_by_source", Q["sfm_by_source"]), ("sfm_daily", Q["sfm_daily"]), ("keys", Q["keys"]),
             ("query_by_pool", Q["query_by_pool"]), ("query_top_runs", Q["query_top_runs"]),
             ("query_top_scan", Q["query_top_scan"]), ("query_api_users", Q["query_api_users"]),
             ("query_alerting", Q["query_alerting"]), ("usage_tokens", usage_q(a.usage_days)),
             ("wildcards", wildcard_q(a.usage_days))]
    for name, dql in steps:
        t0 = time.time()
        r = t.q(name, dql)
        log(f"{name}: {len(r)} rows ({time.time()-t0:.0f}s)")

    keys = json.load(open(os.path.join(t.raw, "keys.json"))) if os.path.exists(os.path.join(t.raw, "keys.json")) else []
    if not a.skip_probe and keys:
        srcs = {s.strip() for s in a.probe_sources.split(",") if s.strip()}
        live = [k for k in keys if not str(k.get("grail.metric.key", "")).startswith("dt.")]
        by_key = {}
        for k in live:                       # a key can appear once per source and type; keep the heaviest row
            kk = k["grail.metric.key"]
            if kk not in by_key or num(k.get("c24")) > num(by_key[kk].get("c24")):
                by_key[kk] = k
        rows = sorted(by_key.values(), key=lambda k: -num(k.get("c24")))
        picked = [k["grail.metric.key"] for k in rows if (k.get("grail.metric.source") or "") in srcs][: a.otel_top]
        # also probe the heaviest histogram bucket series from any source: they show the bucket multiplier (le)
        picked += [k["grail.metric.key"] for k in rows if k["grail.metric.key"].endswith("_bucket") and k["grail.metric.key"] not in picked][:5]
        probes = []
        for key in picked:
            t0 = time.time()
            p = probe_series(t, key)
            log(f"probe {key}: {'ok' if p else 'no result'} ({time.time()-t0:.0f}s)")
            if p:
                probes.append(p)
        json.dump(probes, open(os.path.join(t.raw, "probes.json"), "w"))

    if not a.skip_config:
        fetch_config(t, os.path.join(a.out, "corpus"))
        if any(f.startswith("settings__builtin_davis.anomaly-detectors") for f in os.listdir(os.path.join(a.out, "corpus"))):
            r = t.q("detector_triggers", Q["detector_triggers"], max_records=20000)
            log(f"detector_triggers: {len(r)} rows")

    meta["errors"], meta["warnings"] = t.errors, t.warnings
    meta["finished"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    json.dump(meta, open(os.path.join(a.out, "meta.json"), "w"), indent=1)
    log(f"done. errors={len(t.errors)} warnings={len(t.warnings)}")
    for e in t.errors:
        log("  ERROR " + e)


if __name__ == "__main__":
    main()
