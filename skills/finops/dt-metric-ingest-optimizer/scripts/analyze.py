#!/usr/bin/env python3
"""Turn the raw collector output for ONE tenant into facts.json (numbers) and digest.md (what the model reads).

    uv run --with pyyaml python -X utf8 analyze.py --dir <out>

No tenant calls happen here. Re-run freely after adjusting thresholds.
"""
import argparse, collections, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dtq import num  # noqa: E402

OWN_PREFIXES = ("metric ingest optimization", "metric ingest - ")      # artifacts this skill creates
EXCLUDE_SETTINGS = ("openpipeline", "metric.metadata")                    # they handle metrics, they do not consume them
DETECTOR_SETTINGS = ("davis.anomaly-detectors", "anomaly-detection.metric-events")
TOK = re.compile(r"[A-Za-z0-9_.\-]+")
WILD_CTX = [
    re.compile(r'metric\.key[^\n]{0,160}?"([^"\s]*\*[^"\s]*)"', re.I),
    re.compile(r'(?:metricSelector|metricKey|selector)"?\s*[:=]\s*"([^"\s]*\*[^"\s]*)', re.I),
    re.compile(r'(?:^|\n)\s*metrics\b[^\n]{0,200}?"([^"\s]*\*[^"\s]*)"', re.I),
]
SOURCE_ADVICE = {
    "opentelemetry": "Metrics sent through OTLP. Control volume in the OpenTelemetry Collector or SDK: filter or drop unused metrics, lengthen the export interval, remove high-cardinality attributes, and send histograms natively instead of as per-bucket series.",
    "": "Metrics with no recorded source, typically Prometheus scrapes, Micrometer or Metrics API ingest. Control volume at the scraper or exporter: relabel or drop unused series, lengthen the scrape interval, limit labels.",
    "dynatrace_osagent": "Metrics reported by OneAgent (custom or process-level). Review which custom metrics the agent collects and disable the ones nobody queries.",
    "dynatrace_codemodule": "Metrics from OneAgent code modules (for example Micrometer or JMX inside the application). Restrict the meters or MBeans that are exported, and trim tags.",
    "k8s_monitoring": "Kubernetes monitoring metrics. Review the namespaces and workloads in scope and the Prometheus annotations scraped.",
    "openpipeline": "Metrics extracted by OpenPipeline from spans, logs or events. Review each extraction rule and its dimensions, and delete rules nobody uses.",
    "extension": "Extension metrics. Trim the feature sets or metric selections in the extension configuration and lengthen the polling interval where possible.",
}
INTERACTIVE_SKIP = {"API", "OPERATIONAL", "ALERTING"}
RARE_Q = 10          # interactive queries in the window at or below this count as exploration, not use
STD_INTERVALS = (10, 15, 20, 30, 60, 120, 180, 300, 600, 900, 1800, 3600)


def L(d, name, default=None):
    f = os.path.join(d, "raw", name + ".json")
    if os.path.exists(f):
        try:
            return json.load(open(f, encoding="utf-8"))
        except ValueError:
            pass
    return [] if default is None else default


def source_advice(src):
    s = (src or "").lower()
    if s.startswith("openpipeline"):
        return SOURCE_ADVICE["openpipeline"]
    if s.startswith("com.dynatrace.extension") or s.startswith("custom:") or "extension" in s:
        return SOURCE_ADVICE["extension"]
    return SOURCE_ADVICE.get(s, "Review which of these metrics are queried and trim the rest at the point of collection.")


def family(k):
    m = re.match(r"[A-Za-z0-9]+", k)
    return m.group(0).lower() if m else "other"


SUF = ("_total", "_count", "_sum", "_bucket", "_seconds", "_milliseconds", "_millis", "_ms", "_bytes", "_ratio", "_percent", "_info")


def stem(k):
    s = re.sub(r"[^a-z0-9]+", "_", k.lower()).strip("_")
    ch = True
    while ch:
        ch = False
        for x in SUF:
            if s.endswith(x) and len(s) > len(x) + 3:
                s = s[: -len(x)]
                ch = True
    return s


def metric_wilds(text):
    text = text.replace('\\"', '"')
    out = []
    for rx in WILD_CTX:
        out += rx.findall(text)
    return [w for w in out if "*" in w]


def nb_text(raw):
    try:
        d = json.loads(raw.split("\n", 2)[2])
        c = d["content"]
        c = json.loads(c) if isinstance(c, str) else c
        return "\n".join((s.get("markdown", "") or "") + "\n" + (((s.get("state") or {}).get("input") or {}).get("value", "") or "") for s in c.get("sections", []))
    except Exception:
        return raw


def norm_query(q):
    q = q.replace('\\"', '"')
    q = re.sub(r'"""[^"]*"""', '"S"', q)
    q = re.sub(r'"[^"]*"', '"S"', q)
    q = re.sub(r"\b\d+(\.\d+)?(ms|s|m|h|d)?\b", "N", q)
    return re.sub(r"\s+", " ", q).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    a = ap.parse_args()
    D = a.dir
    meta = json.load(open(os.path.join(D, "meta.json"))) if os.path.exists(os.path.join(D, "meta.json")) else {}
    F = {"meta": {k: meta.get(k) for k in ("context", "environment", "started", "finished")}, "errors": meta.get("errors", []), "warnings": meta.get("warnings", [])}

    # ---------------------------------------------------------------- billing
    types = L(D, "billing_types")
    by_type = L(D, "billing_by_type")
    tot = {k: sum(num(r.get(k)) for r in by_type) for k in ("d1", "d8", "d7")}
    tot["pct_d1_vs_d8"] = round((tot["d1"] - tot["d8"]) * 100.0 / tot["d8"], 1) if tot["d8"] else None
    cc = L(D, "billing_costcenter")
    cc_tot = sum(num(r.get("dp")) for r in cc)
    unassigned = sum(num(r.get("dp")) for r in cc if str(r.get("cost_center", "")).lower() in ("unassigned", "", "none", "null"))
    F["billing"] = {
        "types_found": [{"type": r.get("event.type"), "events": int(num(r.get("events"))), "last_seen": r.get("last_seen")} for r in types],
        "metric_query_billed": any("query" in str(r.get("event.type", "")).lower() for r in types),
        "other_type_sample": L(D, "billing_other_sample"),
        "by_type": [{"metric_type": r.get("metric.type"), "monitoring_source": r.get("monitoring_source"), "bucket": r.get("usage.bucket"),
                     "d1": int(num(r.get("d1"))), "d8": int(num(r.get("d8"))), "d7": int(num(r.get("d7")))} for r in by_type],
        "totals": tot,
        "daily": [{"day": r.get("day"), "dp": int(num(r.get("dp")))} for r in L(D, "billing_daily")],
        "cost_centers": [{"name": r.get("cost_center"), "dp": int(num(r.get("dp")))} for r in cc],
        "cost_center_unassigned_pct": round(unassigned * 100.0 / cc_tot, 1) if cc_tot else None,
        "products": [{"name": r.get("cost_product"), "dp": int(num(r.get("dp")))} for r in L(D, "billing_product")],
    }

    # ---------------------------------------------------------------- ingest by source
    src_rows = L(D, "sfm_by_source")
    F["ingest_by_source"] = [{"source": r.get("grail.metric.source") or "", "metric_type": r.get("grail.metric.type"),
                              "monitoring_source": r.get("grail.monitoring_source"), "cur": int(num(r.get("cur"))), "prev": int(num(r.get("prev")))} for r in src_rows]

    # ---------------------------------------------------------------- keys
    keyrows = L(D, "keys")
    K = {}
    for r in keyrows:
        k = r.get("grail.metric.key")
        if not k:
            continue
        x = K.setdefault(k, {"key": k, "d7": 0, "c24": 0, "p24": 0, "source": r.get("grail.metric.source") or "", "type": r.get("grail.metric.type") or ""})
        x["d7"] += num(r.get("d7")); x["c24"] += num(r.get("c24")); x["p24"] += num(r.get("p24"))
        if num(r.get("c24")) > num(x.get("_best", 0)):
            x["source"] = r.get("grail.metric.source") or ""; x["type"] = r.get("grail.metric.type") or ""; x["_best"] = num(r.get("c24"))
    keys = set(K)

    # usage evidence from the query log
    inter, api, det_runs, last_inter = collections.Counter(), collections.Counter(), collections.Counter(), {}
    for r in L(D, "usage_tokens"):
        t = r.get("tok"); pool = r.get("query_pool") or ""
        if t not in keys:
            continue
        q = int(num(r.get("q")))
        if pool == "API":
            api[t] += q
        elif pool in INTERACTIVE_SKIP:
            continue
        else:
            inter[t] += q
            if str(r.get("last_q", "")) > last_inter.get(t, ""):
                last_inter[t] = str(r.get("last_q", ""))
    alerting = L(D, "query_alerting")
    for r in alerting:
        runs = int(num(r.get("runs")))
        for t in set(TOK.findall(r.get("query_string", ""))):
            if t in keys:
                det_runs[t] += runs
    wild_patterns = collections.defaultdict(set)
    for r in L(D, "wildcards"):
        for w in set(metric_wilds(r.get("query_string", ""))):
            wild_patterns[w].add("query log")

    # saved config
    cfg = collections.defaultdict(set)
    cdir = os.path.join(D, "corpus")
    detectors_raw = []
    docs = 0
    if os.path.isdir(cdir):
        for fn in sorted(os.listdir(cdir)):
            raw = open(os.path.join(cdir, fn), encoding="utf-8", errors="ignore").read()
            if fn.startswith("settings__"):
                if any(s in fn for s in EXCLUDE_SETTINGS):
                    continue
                if "davis.anomaly-detectors" in fn:
                    try:
                        detectors_raw = json.loads(raw)
                    except ValueError:
                        pass
                    continue
                kind = "Classic metric event" if "metric-events" in fn else "Setting"
            else:
                kind = {"dashboards": "Dashboard", "notebooks": "Notebook", "workflows": "Workflow", "slos": "SLO"}.get(fn.split("__")[0], "Config")
                m = re.match(r"NAME: (.*)", raw)
                name = (m.group(1) if m else "").lower()
                if name.startswith(OWN_PREFIXES):
                    continue
                if kind == "Notebook":
                    raw = nb_text(raw)
                if "dt.sfm.metrics.ingest.datapoints" in raw:   # usage or cost analysis documents list metrics, they do not consume them
                    continue
                docs += 1
            for t in set(TOK.findall(raw)):
                if t in keys:
                    cfg[t].add(kind)
            for w in set(metric_wilds(raw)):
                wild_patterns[w].add(kind)
    wild_rx = []
    for p in wild_patterns:
        lit = re.sub(r"[^A-Za-z0-9]", "", p.replace("*", ""))
        if len(lit) >= 3 and re.search(r"[A-Za-z]", lit) and p.replace("*", "") not in keys:
            wild_rx.append((p, re.compile("^" + ".*".join(re.escape(x) for x in p.split("*")) + "$")))

    # classify
    rows = []
    for k, x in K.items():
        billable = not k.startswith("dt.")
        used = []
        if inter.get(k): used.append("interactive")
        if api.get(k): used.append("API client")
        if det_runs.get(k): used.append("detector")
        if cfg.get(k): used.append("saved config")
        wh = [p for p, rx in wild_rx if rx.match(k)]
        if not billable:
            cls = "Platform metric (dt.*)"
        elif inter.get(k) and inter[k] <= RARE_Q and not det_runs.get(k) and not cfg.get(k):
            cls = "Rarely used"
        elif inter.get(k):
            cls = "Used interactively"
        elif api.get(k):
            cls = "Used by API clients only"
        elif det_runs.get(k) or "Classic metric event" in cfg.get(k, set()):
            cls = "Used by detectors only"
        elif cfg.get(k):
            cls = "Referenced in saved config only"
        elif wh:
            cls = "Possible wildcard use"
        else:
            cls = "No usage found"
        rows.append({"key": k, "family": family(k), "source": x["source"], "type": x["type"], "c24": int(x["c24"]), "p24": int(x["p24"]), "d7": int(x["d7"]),
                     "class": cls, "used_by": ", ".join(used), "q_interactive": int(inter.get(k, 0)), "q_api": int(api.get(k, 0)),
                     "detector_runs": int(det_runs.get(k, 0)), "config": ", ".join(sorted(cfg.get(k, []))), "wildcard": "; ".join(wh[:3]),
                     "last_interactive": last_inter.get(k, "")[:10], "bucket": k.endswith("_bucket")})
    rows.sort(key=lambda r: -r["c24"])
    F["keys"] = rows
    bill = [r for r in rows if r["class"] != "Platform metric (dt.*)"]
    F["totals"] = {"keys": len(rows), "billable_keys": len(bill), "c24_all": sum(r["c24"] for r in rows), "c24_billable": sum(r["c24"] for r in bill),
                   "p24_billable": sum(r["p24"] for r in bill), "d7_billable": sum(r["d7"] for r in bill)}
    cls_sum = collections.OrderedDict()
    for c in ("Used interactively", "Rarely used", "Used by API clients only", "Used by detectors only", "Referenced in saved config only", "Possible wildcard use", "No usage found", "Platform metric (dt.*)"):
        s = [r for r in rows if r["class"] == c]
        cls_sum[c] = {"keys": len(s), "c24": sum(r["c24"] for r in s)}
    F["usage_classes"] = cls_sum
    F["evidence"] = {"usage_window_days": (meta.get("args") or {}).get("usage_days", 90), "config_documents_used": docs, "wildcard_patterns": len(wild_rx),
                     "config_collected": os.path.isdir(cdir), "alerting_distinct_queries": len(alerting)}

    # families and sources
    fam = collections.defaultdict(lambda: {"keys": 0, "c24": 0, "unused_c24": 0})
    for r in bill:
        f = fam[r["family"]]; f["keys"] += 1; f["c24"] += r["c24"]
        if r["class"] == "No usage found": f["unused_c24"] += r["c24"]
    F["families"] = sorted(({"family": k, **v} for k, v in fam.items()), key=lambda x: -x["c24"])[:30]
    smry = collections.defaultdict(lambda: {"keys": 0, "c24": 0, "unused_c24": 0, "unused_keys": 0})
    for r in bill:
        s = smry[r["source"]]; s["keys"] += 1; s["c24"] += r["c24"]
        if r["class"] == "No usage found": s["unused_c24"] += r["c24"]; s["unused_keys"] += 1
    F["sources"] = sorted(({"source": k, **v, "advice": source_advice(k)} for k, v in smry.items()), key=lambda x: -x["c24"])

    # movers 24h vs 7 days earlier
    mov = sorted(bill, key=lambda r: r["c24"] - r["p24"])
    F["movers"] = {"down": [{k: r[k] for k in ("key", "c24", "p24")} for r in mov[:15]], "up": [{k: r[k] for k in ("key", "c24", "p24")} for r in mov[::-1][:15]]}

    # standardization: same signal under dotted and underscore names, or from several sources
    stems = collections.defaultdict(list)
    for r in bill:
        stems[stem(r["key"])].append(r)
    dup = []
    for s, g in stems.items():
        if len(g) < 2:
            continue
        dotted = any("." in r["key"] for r in g); under = any("." not in r["key"] and "_" in r["key"] for r in g)
        srcs = {r["source"] for r in g}
        if (dotted and under) or len(srcs) > 1:
            dup.append({"stem": s, "keys": [r["key"] for r in g][:6], "sources": sorted(x or "(none)" for x in srcs), "c24": sum(r["c24"] for r in g)})
    F["duplicate_signals"] = sorted(dup, key=lambda x: -x["c24"])[:30]

    # opentelemetry / series probes
    probes = L(D, "probes", default=[])
    P = []
    for p in probes:
        est = p["est_interval_s"]
        if not (5 <= est <= 3600):          # outside this range the estimate is not trustworthy (lag, bursts, counters)
            continue
        snap = min(STD_INTERVALS, key=lambda x: abs(x - est))
        kr = K.get(p["key"], {})
        dims = sorted(p["dims"], key=lambda d: -d["distinct"])
        le = next((d["distinct"] for d in dims if d["name"] in ("le", "bucket", "upper_bound")), None)
        view, seen = [], {}
        for d in dims:                       # labels with identical distinct counts are the same identity repeated (pod name, pod uid ...)
            if d["distinct"] >= 50 and d["distinct"] in seen:
                seen[d["distinct"]]["dups"] += 1
                continue
            e = {"name": d["name"], "distinct": d["distinct"], "dups": 0}
            seen[d["distinct"]] = e; view.append(e)
        P.append({**p, "interval_s": snap, "c24": int(kr.get("c24", 0)), "source": kr.get("source", ""), "type": kr.get("type", ""), "dims": dims, "dims_view": view, "le_count": le,
                  "class": next((r["class"] for r in rows if r["key"] == p["key"]), "")})
    F["probes"] = P
    targets = (60, 120, 300)
    F["interval_scenarios"] = {str(t): int(sum(p["c24"] * (1 - p["interval_s"] / t) for p in P if p["interval_s"] < t)) for t in targets}

    # opportunities ---------------------------------------------------------------------------------
    O = []
    def opp(id, cat, title, c24, keys_n, effort, evidence, steps, confidence="high", unit="metric keys"):
        O.append({"id": id, "category": cat, "title": title, "dp_day": int(c24), "keys": keys_n, "unit": unit, "effort": effort, "evidence": evidence, "steps": steps, "confidence": confidence})
    unused = [r for r in bill if r["class"] == "No usage found" and r["c24"] > 0]
    stopped = [r for r in bill if r["class"] == "No usage found" and r["c24"] == 0]
    opp("O1", "Stop collecting", "Metrics still arriving that nothing reads", sum(r["c24"] for r in unused), len(unused), "Low",
        f"{len(unused):,} billable metric keys received data in the last 24h, with no interactive or API query in {F['evidence']['usage_window_days']} days, no detector, no saved-config reference and no wildcard match.",
        ["Share the list with the metric owners and agree which to drop.", "Drop at the source first (collector filter, scrape relabel, extension config); use an OpenPipeline drop only where the source cannot change.",
         "Watch dashboards and alerts for no-data for one week.", "Remove the keys from the drop list as they stop arriving."])
    apionly = [r for r in bill if r["class"] == "Used by API clients only"]
    opp("O2", "Validate then reduce", "Metrics read only by API clients", sum(r["c24"] for r in apionly), len(apionly), "Medium",
        "Queried only through the API (for example Grafana or scripts), never from Dynatrace apps, dashboards, detectors or config.",
        ["Identify the API clients from the query log (user and token).", "Confirm the metrics are still needed; if so, keep and agree an owner.", "Reduce frequency or labels where the client does not need them."], "medium")
    rare = [r for r in bill if r["class"] == "Rarely used"]
    opp("O2b", "Validate then reduce", f"Rarely used metrics ({RARE_Q} or fewer queries in {F['evidence']['usage_window_days']} days)", sum(r["c24"] for r in rare), len(rare), "Low",
        "A handful of interactive queries over the whole window usually means exploration, not a live dashboard or alert.",
        ["Review the top rarely used metrics with their owners.", "Drop the ones nobody claims, or keep and trim labels.", "Re-run the review each quarter."], "medium")
    detonly = [r for r in bill if r["class"] == "Used by detectors only"]
    opp("O3", "Alerting efficiency", "Metrics read only by anomaly detectors", sum(r["c24"] for r in detonly), len(detonly), "Medium",
        "No person or dashboard reads these. Only detectors run on them.",
        ["Check whether those detectors have fired recently (see the detector section).", "Retire detectors that never fire and have no owner, then drop the metric.", "Where the alert matters, keep the metric and trim labels."], "medium")
    buckets_used = [r for r in bill if r["bucket"] and r["class"] not in ("No usage found",)]
    opp("O4", "Reduce at the source", "Histogram bucket series that are used", sum(r["c24"] for r in buckets_used), len(buckets_used), "Medium",
        "Each _bucket key is one series per bucket boundary. Native histograms send one datapoint per series instead of one per bucket.",
        ["Prefer native histograms (OTLP Histogram or exponential histogram) over per-bucket counters.", "Reduce the number of buckets and drop labels the dashboards do not use.", "Keep the _sum and _count series; drop _bucket for histograms nobody needs percentiles from."], "medium")
    unused_b = [r for r in unused if r["bucket"]]
    if probes:
        s60 = F["interval_scenarios"]["60"]; s300 = F["interval_scenarios"]["300"]
        opp("O5", "Reduce at the source", "Longer reporting interval on the probed high-volume metrics", s300, len(P), "Low",
            f"Estimated reporting interval was measured for {len(P)} high-volume metrics. Moving them to 5 minutes frees about {s300:,} datapoints a day (60s: {s60:,}).",
            ["Raise the export or scrape interval in the collector, SDK or exporter (see the OpenTelemetry guidance).", "Keep 60s for SLO and alerting metrics. Use 5 minutes for capacity and inventory metrics.", "Check detectors that use short sliding windows before changing intervals."], "medium")
    cards = [p for p in P if any(d["distinct"] >= 1000 and d["name"] not in ("le",) for d in p["dims"])]
    if cards:
        opp("O6", "Reduce at the source", "High-cardinality labels on high-volume metrics", 0, len(cards), "Medium",
            f"{len(cards)} probed metrics carry a label with 1,000 or more distinct values. Only labels that multiply series cut datapoints (for example a mount point or interface name on every node). A label that repeats the same identity as another (pod name and pod uid) does not change the series count.",
            ["Review the largest labels on each probed metric with its owner and remove or aggregate the ones nobody filters or splits by (transform processor, relabel).", "Re-measure the series count afterwards."], "medium")
    if F["duplicate_signals"]:
        opp("O7", "Standardize", "Same signal arriving under more than one name or source", sum(d["c24"] for d in F["duplicate_signals"]), sum(len(d["keys"]) for d in F["duplicate_signals"]), "Medium",
            "The same signal is delivered with dotted (OpenTelemetry) and underscore (Prometheus) names, or from more than one source.",
            ["Pick one naming standard per signal (OpenTelemetry semantic conventions are the usual choice).", "Move dashboards and detectors to the chosen name, then stop the duplicate."], "medium")
    if F["billing"]["cost_center_unassigned_pct"] and F["billing"]["cost_center_unassigned_pct"] >= 20:
        opp("O8", "Standardize", "Billed metric volume without a cost center", 0, 0, "Low",
            f"{F['billing']['cost_center_unassigned_pct']}% of billed datapoints carry no cost center, so they cannot be charged back to a team.",
            ["Add a cost-center and product attribute at the collector (resource attribute) or with an OpenPipeline rule.", "Review the unassigned list monthly."], "high")
    F["opportunities"] = O

    # ---------------------------------------------------------------- query load (Metric - Query side)
    pools = L(D, "query_by_pool")
    total_q = sum(num(r.get("queries")) for r in pools) or 1
    F["query"] = {
        "billed_as_metric_query": F["billing"]["metric_query_billed"],
        "by_pool": [{"pool": r.get("query_pool"), "queries": int(num(r.get("queries"))), "share_pct": round(num(r.get("queries")) * 100.0 / total_q, 2), "users": int(num(r.get("users"))),
                     "scanned_dp": int(num(r.get("scanned_dp"))), "scanned_gb": round(num(r.get("scanned_bytes")) / 2**30, 2), "ondemand_gb": round(num(r.get("ondemand_bytes")) / 2**30, 2),
                     "avg_ms": round(num(r.get("avg_ms")), 1), "p95_ms": round(num(r.get("p95_ms")), 1), "failed": int(num(r.get("failed")))} for r in pools],
        "top_runs": L(D, "query_top_runs")[:25], "top_scan": L(D, "query_top_scan")[:25], "api_users": L(D, "query_api_users")[:15],
    }

    # ---------------------------------------------------------------- detectors (from saved config)
    trig = {r.get("dt.settings.object_id"): r for r in L(D, "detector_triggers")}
    dets = []
    for o in detectors_raw:
        v = o.get("value", {}); an = v.get("analyzer", {}); inp = {i["key"]: i["value"] for i in an.get("input", [])}
        props = {p["key"]: p["value"] for p in v.get("eventTemplate", {}).get("properties", [])}
        q = inp.get("query", ""); title = v.get("title", "")
        parts = [x.strip().replace("\\", "") for x in title.split(" | ")]
        dets.append({"id": o.get("objectId"), "title": title, "alert": parts[-1] if len(parts) >= 5 else title, "enabled": bool(v.get("enabled")),
                     "analyzer": an.get("name", "").split(".")[-1], "is_metric": q.lstrip().startswith("timeseries"), "query": q,
                     "metrics": sorted({t for t in TOK.findall(q) if t in keys}), "triggers30": int(num((trig.get(o.get("objectId")) or {}).get("triggers"))),
                     "route": props.get("routingKey", ""), "team": props.get("product", ""),
                     "params": [inp.get(p, "") for p in ("alertCondition", "threshold", "violatingSamples", "dealertingSamples", "slidingWindow")]})
    if dets:
        en = [d for d in dets if d["enabled"]]
        fired = [d for d in en if d["triggers30"]]
        em = [d for d in en if d["is_metric"]]
        tpl = collections.defaultdict(list)
        for d in em:
            tpl[(d["analyzer"], norm_query(d["query"]), d["alert"])].append(d)
        multi = [g for g in tpl.values() if len(g) > 1]
        fams = collections.defaultdict(list)
        for d in em:
            fams[d["alert"]].append(d)
        topfam = []
        for n, g in sorted(fams.items(), key=lambda kv: -len(kv[1]))[:12]:
            ps = collections.Counter(tuple(d["params"]) for d in g)
            topfam.append({"alert": n, "detectors": len(g), "fired": sum(1 for d in g if d["triggers30"]), "threshold_sets": len(ps), "teams": len({d["team"] for d in g}),
                           "routes": len({d["route"] for d in g}), "metrics": sorted({m for d in g for m in d["metrics"]})[:4]})
        dn = collections.Counter(m for d in en for m in d["metrics"])
        dvol = sum(r["c24"] for r in bill if r["key"] in dn)
        F["detectors"] = {"total": len(dets), "enabled": len(en), "disabled": len(dets) - len(en), "fired_30d": len(fired), "metric_based": len(em),
                          "metric_never_fired": sum(1 for d in em if not d["triggers30"]), "templates": len(tpl), "templates_with_copies": len(multi),
                          "detectors_in_copies": sum(len(g) for g in multi), "evaluations_per_day": 1440 * len(em), "evaluations_after_merge": 1440 * len(tpl),
                          "billable_metrics_read": len([m for m in dn if m in {r['key'] for r in bill}]), "metric_volume_c24": int(dvol),
                          "top_families": topfam, "triggers_collected": bool(trig),
                          "most_alerting": [{"title": d["title"][:120], "triggers30": d["triggers30"]} for d in sorted(fired, key=lambda d: -d["triggers30"])[:15]]}
        if multi:
            opp("O9", "Alerting efficiency", "Anomaly detectors that are copies of one template", 0, len(F["detectors"]) and F["detectors"]["detectors_in_copies"], "Medium",
                f"{F['detectors']['detectors_in_copies']:,} enabled metric detectors reduce to {F['detectors']['templates']:,} templates once per-team values are ignored. {F['detectors']['metric_never_fired']:,} metric detectors never fired in 30 days.",
                ["Merge copies into one detector per template and threshold tier, grouped by the workload dimensions.", "Move per-team notification into a workflow with a lookup table so each team still gets its own alerts.",
                 "Pilot on one family, run side by side for a week, then disable the copies."], "medium", unit="detectors")
    F["opportunities"] = O

    # ---------------------------------------------------------------- write
    json.dump(F, open(os.path.join(D, "facts.json"), "w"), indent=1)
    write_digest(D, F, unused, stopped)
    print(f"facts.json and digest.md written to {D}")


def m(n):
    return f"{n/1e6:,.1f}M"


def write_digest(D, F, unused, stopped):
    b = F["billing"]; t = F["totals"]; o = []
    o.append(f"# Digest: {F['meta'].get('context')} ({F['meta'].get('environment')})\n")
    o.append("## Billed metric ingest (Metrics - Ingest & Process)")
    o.append(f"- Billing types found: {', '.join(x['type'] for x in b['types_found']) or 'none'}. Metric - Query billed as its own type: {b['metric_query_billed']}")
    o.append(f"- Last complete day {m(b['totals']['d1'])} vs same day a week earlier {m(b['totals']['d8'])} ({b['totals']['pct_d1_vs_d8']}%). Last 7 complete days {m(b['totals']['d7'])}.")
    o.append("- By data type / monitoring source (d7):")
    for r in b["by_type"][:10]:
        o.append(f"  - {r['metric_type']} / {r['monitoring_source']} / {r['bucket']}: {m(r['d7'])}")
    if b["cost_center_unassigned_pct"] is not None:
        o.append(f"- Cost center unassigned: {b['cost_center_unassigned_pct']}% of billed datapoints. Top: " + ", ".join(f"{c['name']} {m(c['dp'])}" for c in b['cost_centers'][:5]))
    o.append("\n## Ingest by source (24h)")
    for r in F["ingest_by_source"][:10]:
        o.append(f"- {r['source'] or '(none)'} / {r['metric_type']} / {r['monitoring_source']}: {m(r['cur'])} (was {m(r['prev'])})")
    o.append(f"\n## Keys: {t['keys']} total, {t['billable_keys']} billable, {m(t['c24_billable'])}/day billable")
    for c, v in F["usage_classes"].items():
        o.append(f"- {c}: {v['keys']} keys, {m(v['c24'])}/day")
    o.append("\n## Opportunities (volume per day)")
    for x in F["opportunities"]:
        o.append(f"- {x['id']} [{x['category']}] {x['title']}: {x['keys']} {x.get('unit','metric keys')}, {m(x['dp_day'])}/day, effort {x['effort']}")
    o.append("\n## Top 15 billable keys (24h) with usage class")
    for r in [r for r in F["keys"] if r["class"] != "Platform metric (dt.*)"][:15]:
        o.append(f"- {r['key']} ({r['source'] or '-'}): {m(r['c24'])} | {r['class']} | interactive {r['q_interactive']}, api {r['q_api']}, detector runs {r['detector_runs']}")
    o.append("\n## Top 10 unused and still arriving")
    for r in unused[:10]:
        o.append(f"- {r['key']}: {m(r['c24'])}/day")
    o.append("\n## Probed series (reporting interval estimate)")
    for p in F["probes"]:
        hi = ", ".join(f"{d['name']}={d['distinct']}" + (f" (+{d['dups']} same)" if d["dups"] else "") for d in p["dims_view"][:3])
        o.append(f"- {p['key']}: series {p['series']:,}, est interval {p['interval_s']}s (raw {p['est_interval_s']}s), top dims {hi}, le={p['le_count']}")
    o.append(f"Interval scenarios (datapoints/day freed): {F['interval_scenarios']}")
    o.append("\n## Sources")
    for s in F["sources"][:8]:
        o.append(f"- {s['source'] or '(none)'}: {s['keys']} keys, {m(s['c24'])}/day, unused {m(s['unused_c24'])}/day")
    o.append("\n## Query load (7 days)")
    for r in F["query"]["by_pool"][:8]:
        o.append(f"- {r['pool']}: {r['queries']:,} queries ({r['share_pct']}%), scanned {m(r['scanned_dp'])} datapoints, on-demand {r['ondemand_gb']} GB, failed {r['failed']:,}")
    if "detectors" in F:
        d = F["detectors"]
        o.append(f"\n## Detectors: {d['total']} configured, {d['enabled']} enabled, fired in 30d {d['fired_30d']} (triggers collected {d['triggers_collected']}), {d['metric_based']} metric based, {d['templates']} templates, {d['detectors_in_copies']} in copies")
        for f in d["top_families"][:6]:
            o.append(f"- {f['alert']}: {f['detectors']} detectors, fired {f['fired']}, {f['threshold_sets']} threshold sets, {f['teams']} teams")
    o.append("\n## Duplicate signals (top 8)")
    for d in F["duplicate_signals"][:8]:
        o.append(f"- {d['stem']}: {', '.join(d['keys'][:3])} ({m(d['c24'])}/day)")
    o.append("\n## Collection errors and warnings")
    for e in F["errors"] + F["warnings"]:
        o.append(f"- {e}")
    open(os.path.join(D, "digest.md"), "w", encoding="utf-8").write("\n".join(o) + "\n")


if __name__ == "__main__":
    main()
