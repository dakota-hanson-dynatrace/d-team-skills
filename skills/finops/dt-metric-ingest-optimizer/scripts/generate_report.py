#!/usr/bin/env python3
"""Build the customer report (.md and .docx) for ONE tenant from facts.json plus a short overrides.json.

    uv run --with python-docx python -X utf8 generate_report.py --facts <out>/facts.json --overrides <out>/overrides.json \
        --customer "<name>" --author "<SE>" --rate 0.15 --out-base <out>/<Customer>_Metric_Ingest_Review

The numbers always come from facts.json. overrides.json carries only judgment: the summary, ordering, notes and extra findings.
"""
import argparse, datetime, json, os, re, sys

CATEGORY_ORDER = ["Stop collecting", "Validate then reduce", "Reduce at the source", "Standardize", "Alerting efficiency"]
CATEGORY_INTRO = {
    "Stop collecting": "Metrics that arrive and cost volume but that nothing reads. The safest reduction because no one loses a view.",
    "Validate then reduce": "Metrics with little or unclear use. Confirm with the owner, then drop or trim.",
    "Reduce at the source": "Metrics that are used but sent in a heavier form than needed: too often, too many labels, or as one series per histogram bucket.",
    "Standardize": "The same signal under several names, and volume that cannot be attributed to a team. Standards make the other work repeatable.",
    "Alerting efficiency": "Anomaly detectors and the metrics they depend on. Fewer, cleaner detectors keep every team's alerts and cut evaluation load.",
}
INTERVAL_GUIDE = [
    ("Availability, error rate and latency used by alerts or SLOs", "30 to 60 seconds", "Detectors and SLOs need short windows to react."),
    ("Resource utilization and capacity (CPU, memory, disk, network)", "60 to 120 seconds", "Trends matter more than single samples."),
    ("Inventory, state and configuration (info, labels, tolerations, limits, requests)", "300 seconds or longer", "Values change rarely, so most samples repeat the last one."),
    ("Collector and pipeline self-metrics", "60 to 300 seconds", "Useful for health, rarely needed at high resolution."),
]
SNIPPETS = [
    ("Drop metrics nobody reads (collector filter processor)", """processors:
  filter/drop_unused:
    error_mode: ignore
    metrics:
      metric:
        - 'name == "node_filesystem_device_error"'
        - 'IsMatch(name, "^kube_pod_(tolerations|status_reason)$")'"""),
    ("Lengthen the reporting interval", """# Prometheus receiver
receivers:
  prometheus:
    config:
      scrape_configs:
        - job_name: kube-state-metrics
          scrape_interval: 300s

# SDK-based services: export interval in milliseconds
OTEL_METRIC_EXPORT_INTERVAL=60000"""),
    ("Remove labels nobody uses (transform processor)", """processors:
  transform/drop_labels:
    metric_statements:
      - context: datapoint
        statements:
          - delete_key(attributes, "pod_uid")
          - delete_key(attributes, "container_id")"""),
    ("Send histograms natively and use delta temporality", """processors:
  cumulativetodelta: {}
  batch:
    timeout: 60s
service:
  pipelines:
    metrics:
      receivers: [prometheus]
      processors: [filter/drop_unused, transform/drop_labels, cumulativetodelta, batch]
      exporters: [otlphttp/dynatrace]"""),
]


def num(x, d=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def mm(n):
    n = num(n)
    return f"{n/1e9:,.2f}B" if abs(n) >= 1e9 else f"{n/1e6:,.1f}M"


class R:
    """Tiny block model rendered to Markdown and Word."""

    def __init__(self):
        self.b = []

    def h(self, level, text): self.b.append(("h", level, text))
    def p(self, text): self.b.append(("p", text))
    def bullets(self, items): self.b.append(("ul", [i for i in items if i]))
    def numbered(self, items): self.b.append(("ol", [i for i in items if i]))
    def table(self, heads, rows): self.b.append(("t", heads, rows))
    def code(self, title, text): self.b.append(("code", title, text))
    def pb(self): self.b.append(("pb",))

    def md(self):
        o = []
        for x in self.b:
            k = x[0]
            if k == "h": o.append("#" * x[1] + " " + x[2] + "\n")
            elif k == "p": o.append(x[1] + "\n")
            elif k == "ul": o.append("\n".join("- " + i for i in x[1]) + "\n")
            elif k == "ol": o.append("\n".join(f"{n}. {i}" for n, i in enumerate(x[1], 1)) + "\n")
            elif k == "t":
                o.append("| " + " | ".join(x[1]) + " |\n|" + "---|" * len(x[1]) + "\n" + "\n".join("| " + " | ".join(str(c) for c in r) + " |" for r in x[2]) + "\n")
            elif k == "code": o.append(f"**{x[1]}**\n\n```yaml\n{x[2]}\n```\n")
        return "\n".join(o)

    def docx(self, path, title, subtitle, author):
        from docx import Document
        from docx.enum.text import WD_BREAK
        from docx.shared import Pt, RGBColor
        d = Document()
        st = d.styles["Normal"]; st.font.name = "Arial"; st.font.size = Pt(10)
        t = d.add_heading(title, 0)
        d.add_paragraph(subtitle)
        d.add_paragraph(f"Prepared by {author}" if author else "")
        for x in self.b:
            k = x[0]
            if k == "h": d.add_heading(x[2], x[1])
            elif k == "p": d.add_paragraph(x[1])
            elif k == "ul":
                for i in x[1]: d.add_paragraph(i, style="List Bullet")
            elif k == "ol":
                for i in x[1]: d.add_paragraph(i, style="List Number")
            elif k == "t":
                tb = d.add_table(rows=1, cols=len(x[1])); tb.style = "Light Grid Accent 1"
                for i, h in enumerate(x[1]):
                    c = tb.rows[0].cells[i]; c.text = h
                    for r_ in c.paragraphs[0].runs: r_.font.bold = True; r_.font.size = Pt(9)
                for r in x[2]:
                    cells = tb.add_row().cells
                    for i, v in enumerate(r):
                        cells[i].text = str(v)
                        for p_ in cells[i].paragraphs:
                            for r_ in p_.runs: r_.font.size = Pt(9)
                d.add_paragraph("")
            elif k == "code":
                d.add_paragraph(x[1]).runs[0].font.bold = True
                p = d.add_paragraph(); r_ = p.add_run(x[2]); r_.font.name = "Consolas"; r_.font.size = Pt(8)
            elif k == "pb":
                d.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        d.save(path)


def build(F, O, customer, rate, created):
    ann = lambda dp_day: dp_day * 365 / 1e6 * rate           # datapoints per day -> dollars per year
    usd = lambda dp_day: f"${ann(dp_day):,.0f}"
    r = R()
    b, t, uc = F["billing"], F["totals"], F["usage_classes"]
    opps = {x["id"]: x for x in F["opportunities"]}
    day = F["billing"]["totals"]
    o1 = opps.get("O1", {"keys": 0, "dp_day": 0})

    r.h(1, "Executive summary")
    r.p(O.get("summary") or (
        f"{customer} sends about {mm(t['c24_billable'])} billable metric datapoints a day across {t['billable_keys']:,} metric keys. "
        f"{o1['keys']:,} of those keys ({mm(o1['dp_day'])} datapoints a day) are read by nothing we could find. "
        f"A further {uc['Rarely used']['keys']:,} keys ({mm(uc['Rarely used']['c24'])} a day) were queried ten times or fewer in {F['evidence']['usage_window_days']} days."))
    r.table(["Measure", "Value"], [
        ["Billed datapoints, last complete day", f"{mm(day['d1'])}"],
        ["Same day a week earlier", f"{mm(day['d8'])} ({day['pct_d1_vs_d8']}%)" if day["pct_d1_vs_d8"] is not None else mm(day["d8"])],
        ["Billable metric keys receiving data", f"{t['billable_keys']:,}"],
        ["Never used and still arriving", f"{o1['keys']:,} keys, {mm(o1['dp_day'])} a day ({usd(o1['dp_day'])} a year)"],
        ["Rarely used", f"{uc['Rarely used']['keys']:,} keys, {mm(uc['Rarely used']['c24'])} a day ({usd(uc['Rarely used']['c24'])} a year)"],
        ["Read only by API clients", f"{uc['Used by API clients only']['keys']:,} keys, {mm(uc['Used by API clients only']['c24'])} a day"],
        ["Dollar figures", f"Indicative, at ${rate} per million datapoints. Replace with the contracted rate."],
    ])
    if O.get("summary_points"):
        r.bullets(O["summary_points"])
    if O.get("priorities"):
        r.h(2, "Priorities")
        r.numbered(O["priorities"])

    r.h(1, "What we looked at")
    types = ", ".join(x["type"] for x in b["types_found"]) or "none found"
    r.bullets([
        f"Billing usage records for metrics: {types}.",
        "Metric - Query: " + ("billed as its own usage type in this tenant." if b["metric_query_billed"] else "no separate usage type appears in billing, so query opportunities are framed as load and efficiency (see Metric query load)."),
        f"Ingested datapoints for every metric key over 7 days, by source, data type and monitoring source.",
        f"Who reads each metric: {F['evidence']['usage_window_days']} days of metric query history, split into dashboards and apps, API clients and anomaly detectors.",
        f"Saved configuration: {F['evidence']['config_documents_used']} dashboards, notebooks, workflows and SLOs, plus detector and metric settings." if F["evidence"]["config_collected"] else "Saved configuration was not collected in this run.",
        f"Measured reporting interval and labels for {len(F['probes'])} high-volume metrics." if F["probes"] else "Reporting interval was not measured in this run.",
    ])

    r.h(1, "How metric ingest looks today")
    r.h(2, "Billed ingest by data type and source")
    tot7 = sum(x["d7"] for x in b["by_type"]) or 1
    r.table(["Data type", "Monitoring source", "Billing bucket", "Last 7 days", "Share", "Last day", "Week earlier"],
            [[x["metric_type"], x["monitoring_source"] or "(none)", x["bucket"], mm(x["d7"]), f"{x['d7']*100/tot7:.1f}%", mm(x["d1"]), mm(x["d8"])] for x in b["by_type"]])
    r.h(2, "Where the metrics come from")
    r.table(["Source", "Metric keys", "Datapoints a day", "Never used (a day)", "How to manage"],
            [[s["source"] or "(none)", f"{s['keys']:,}", mm(s["c24"]), mm(s["unused_c24"]), s["advice"]] for s in F["sources"][:8]])
    r.h(2, "Largest metrics")
    r.table(["Metric", "Source", "Datapoints a day", "Who reads it"],
            [[x["key"], x["source"] or "(none)", mm(x["c24"]), x["class"] + (f" ({x['used_by']})" if x["used_by"] else "")] for x in [k for k in F["keys"] if k["class"] != "Platform metric (dt.*)"][:20]])
    if b["cost_centers"]:
        r.h(2, "Attribution to teams")
        tc = sum(c["dp"] for c in b["cost_centers"]) or 1
        r.table(["Cost center", "Billed datapoints, last 8 days", "Share"], [[c["name"], mm(c["dp"]), f"{c['dp']*100/tc:.1f}%"] for c in b["cost_centers"][:10]])
    r.h(2, "Biggest reductions: last 24 hours against the same 24 hours a week earlier")
    r.table(["Metric", "A week earlier", "Last 24 hours"], [[x["key"], mm(x["p24"]), mm(x["c24"])] for x in F["movers"]["down"][:8]])
    r.h(2, "Biggest increases")
    r.table(["Metric", "A week earlier", "Last 24 hours"], [[x["key"], mm(x["p24"]), mm(x["c24"])] for x in F["movers"]["up"][:8]])

    r.h(1, "Findings and how to manage the metrics coming in")
    notes = O.get("opportunity_notes", {})
    by_cat = {}
    for x in F["opportunities"]:
        by_cat.setdefault(x["category"], []).append(x)
    for cat in CATEGORY_ORDER:
        if cat not in by_cat:
            continue
        r.h(2, cat)
        r.p(CATEGORY_INTRO[cat])
        for x in by_cat[cat]:
            r.h(3, f"{x['id']}. {x['title']}")
            r.bullets([f"What we found: {x['evidence']}", notes.get(x["id"]),
                       f"Volume: {x['keys']:,} {x.get('unit','metric keys')}, {mm(x['dp_day'])} datapoints a day ({usd(x['dp_day'])} a year at the assumed rate)." if x["dp_day"] else (f"Scope: {x['keys']:,} {x.get('unit','metric keys')}." if x["keys"] else None),
                       f"Effort: {x['effort']}. Confidence: {x['confidence']}."])
            r.p("Steps to remediate:")
            r.numbered(x["steps"])
            rows = {"O1": [k for k in F["keys"] if k["class"] == "No usage found" and k["c24"] > 0][:15],
                    "O2": [k for k in F["keys"] if k["class"] == "Used by API clients only"][:12],
                    "O2b": [k for k in F["keys"] if k["class"] == "Rarely used"][:15],
                    "O3": [k for k in F["keys"] if k["class"] == "Used by detectors only"][:10],
                    "O4": [k for k in F["keys"] if k["bucket"] and k["class"] not in ("No usage found", "Platform metric (dt.*)")][:10]}.get(x["id"])
            if rows:
                r.table(["Metric", "Source", "Datapoints a day", "Interactive queries", "API queries"], [[k["key"], k["source"] or "(none)", mm(k["c24"]), k["q_interactive"], k["q_api"]] for k in rows])
            if x["id"] == "O7":
                r.table(["Signal", "Names seen", "Sources", "Datapoints a day"], [[d["stem"], ", ".join(d["keys"][:3]), ", ".join(d["sources"]), mm(d["c24"])] for d in F["duplicate_signals"][:10]])
    for ef in O.get("extra_findings", []):
        r.h(3, ef["title"]); r.p(ef.get("text", ""))
        if ef.get("steps"): r.numbered(ef["steps"])

    r.h(1, "OpenTelemetry metrics and the sampling window")
    r.p("The sampling window is how often each series reports a value. A series that reports every 10 seconds sends six times the datapoints of one that reports every minute and thirty times those of one that reports every five minutes, with no extra insight for most metrics.")
    if F["probes"]:
        r.table(["Metric", "Series", "Reporting interval", "Largest labels (distinct values)", "Datapoints a day", "Buckets"],
                [[p["key"], f"{p['series']:,}", f"{p['interval_s']}s", ", ".join(f"{d['name']} ({d['distinct']:,}" + (f", +{d['dups']} repeating it" if d["dups"] else "") + ")" for d in p["dims_view"][:3]), mm(p["c24"]), p["le_count"] or ""] for p in F["probes"]])
        sc = F["interval_scenarios"]
        r.table(["If the probed metrics reported every", "Datapoints a day freed", "Per year at the assumed rate"],
                [[f"{k} seconds", mm(v), usd(v)] for k, v in sc.items()])
        r.p("Intervals were estimated from datapoints against active series, then rounded to the nearest standard interval. Treat them as an estimate and confirm in the collector or SDK configuration.")
    else:
        r.p("No metric could be probed in this run, so no reporting interval is shown.")
    r.h(2, "Recommended interval by kind of metric")
    r.table(["Kind of metric", "Suggested interval", "Why"], [list(x) for x in INTERVAL_GUIDE])
    r.h(2, "Histograms")
    r.p("A histogram sent as one series per bucket boundary multiplies datapoints by the number of boundaries. Sending it as a native histogram (OpenTelemetry Histogram or exponential histogram) sends one datapoint per series. Keep the sum and count series, and drop the buckets nobody uses for percentiles.")
    r.h(2, "Collector and SDK configuration examples")
    for title, text in SNIPPETS:
        r.code(title, text)

    q = F["query"]
    r.h(1, "Metric query load")
    r.p("Metric queries come from anomaly detectors (once a minute each), API clients, dashboards and apps. " +
        ("Metric - Query is billed as its own usage type in this tenant." if q["billed_as_metric_query"] else "Billing usage in this tenant shows no separate Metric - Query type, so the measures below show load and efficiency."))
    r.table(["Source", "Queries (7 days)", "Share", "Datapoints scanned", "On-demand scan (GB)", "Avg ms", "p95 ms", "Failed"],
            [[x["pool"], f"{x['queries']:,}", f"{x['share_pct']}%", mm(x["scanned_dp"]), x["ondemand_gb"], x["avg_ms"], x["p95_ms"], f"{x['failed']:,}"] for x in q["by_pool"]])
    r.bullets(["Detector runs dominate the query log. They make every metric they read look queried, so usage checks must exclude them.",
               "API clients that poll at a fixed rate with the same query are candidates for a longer refresh interval or caching.",
               "Dashboards that refresh often over long ranges scan the most datapoints. Shorten the default range or the refresh rate."])
    if q["api_users"]:
        r.h(2, "Heaviest API clients")
        r.table(["Client", "Queries (7 days)", "Datapoints scanned", "Distinct queries"], [[x.get("user.email"), f"{int(num(x.get('runs'))):,}", mm(x.get("scanned_dp")), x.get("distinct_queries")] for x in q["api_users"][:8]])

    if "detectors" in F:
        d = F["detectors"]
        r.h(1, "Anomaly detectors")
        r.table(["Measure", "Value"], [["Configured / enabled", f"{d['total']:,} / {d['enabled']:,}"], ["Opened an alert in 30 days", f"{d['fired_30d']:,}" if d["triggers_collected"] else "not collected"],
                                      ["Metric based", f"{d['metric_based']:,}"], ["Templates after ignoring per-team values", f"{d['templates']:,}"],
                                      ["Detectors that are copies of another", f"{d['detectors_in_copies']:,}"], ["Evaluations a day", f"{d['evaluations_per_day']/1e6:,.1f}M (about {d['evaluations_after_merge']/1e6:,.1f}M after merging copies)"]])
        r.table(["Alert family", "Detectors", "Fired in 30d", "Threshold sets", "Teams"], [[f["alert"], f["detectors"], f["fired"], f["threshold_sets"], f["teams"]] for f in d["top_families"][:8]])
        r.p("To consolidate without losing per-team alerts: merge each family into one detector per threshold tier grouped by workload dimensions, put those dimensions in the event, and route notifications from a workflow using a team lookup table.")

    r.h(1, "Phased plan")
    phases = O.get("phases") or default_phases(opps, F, usd)
    for ph in phases:
        r.h(2, ph["name"])
        r.p(ph.get("goal", ""))
        r.numbered(ph["steps"])
        r.p(f"Owners: {ph.get('owners','Platform and metric owners')}. Effort: {ph.get('effort','Medium')}. Expected outcome: {ph.get('outcome','')}")

    r.h(1, "Appendix: method, limits and assets")
    r.bullets(["Billed volume comes from billing usage records matched on the usage period. Per-metric volume comes from the ingest datapoint measure, which is within a few percent of billed volume outside dt.* platform metrics.",
               f"Usage is judged from {F['evidence']['usage_window_days']} days of query history. Work that runs less often, such as quarter-end jobs, would be missed.",
               "Detector runs are excluded from usage because they execute every minute. Metrics read only by detectors are listed separately.",
               "Wildcard use is checked in saved config and query history. A metric used only through a wildcard query is kept as possible use.",
               "Dollar figures use the rate stated above and are indicative.",
               ] + O.get("caveats", []) + [f"Collection warning: {w}" for w in (F["errors"] + F["warnings"])[:6]])
    if created:
        r.h(2, "Assets created in the tenant")
        r.bullets([f"{c.get('resourceType')}: {c.get('name')} {c.get('url','')}" for c in created])
    return r


def default_phases(opps, F, usd):
    g = lambda i: opps.get(i, {"dp_day": 0, "keys": 0})
    return [
        {"name": "Phase 0: Foundations (week 1)", "goal": "Agree ownership and a baseline so every later change can be measured.",
         "steps": ["Share this report with the platform and metric owners and agree who owns each source.", "Record the baseline: billed datapoints a day and the weekly comparison dashboard.",
                   "Agree a naming standard and a cost-center attribute for new metrics."], "owners": "Platform lead, metric owners", "effort": "Low", "outcome": "A named owner per source and a baseline to compare against."},
        {"name": "Phase 1: Quick wins (weeks 1 to 3)", "goal": "Stop collecting what nothing reads.",
         "steps": [f"Drop the {g('O1')['keys']:,} unused metrics at the source (about {g('O1')['dp_day']/1e6:,.0f}M datapoints a day).", "Review the rarely used list and drop what no owner claims.",
                   "Watch dashboards and alerts for no-data for a week after each batch."], "owners": "Metric owners, platform team", "effort": "Low", "outcome": f"About {usd(g('O1')['dp_day'])} a year at the assumed rate, with no loss of views."},
        {"name": "Phase 2: Reduce at the source (weeks 3 to 8)", "goal": "Send what is used in a lighter form.",
         "steps": ["Lengthen the reporting interval on capacity and inventory metrics.", "Remove labels nobody splits by.", "Move per-bucket histograms to native histograms and drop unused buckets.",
                   "Validate the metrics read only by API clients with their owners."], "owners": "Platform and application teams", "effort": "Medium", "outcome": "Fewer datapoints per series and fewer series for the same insight."},
        {"name": "Phase 3: Standardize and consolidate (weeks 6 to 12)", "goal": "Make the estate easier to manage and cheaper to run.",
         "steps": ["Pick one name per signal and retire the duplicates.", "Merge copied anomaly detectors by template and route per-team notifications from a workflow.", "Review detectors that never fire with their owners."],
         "owners": "Platform team, alert owners", "effort": "Medium", "outcome": "Fewer detectors and queries, one standard, every team still alerted."},
        {"name": "Phase 4: Govern (ongoing)", "goal": "Keep the gains.",
         "steps": ["Review the unused and rarely used lists quarterly.", "Alert on week-over-week ingest change using the comparison dashboard.", "Require owner, cost center and interval for every new metric source."],
         "owners": "Platform lead", "effort": "Low", "outcome": "Ingest stays flat as the estate grows."},
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--facts", required=True)
    ap.add_argument("--overrides")
    ap.add_argument("--customer", required=True)
    ap.add_argument("--author", default="")
    ap.add_argument("--rate", type=float, default=0.15, help="dollars per million datapoints")
    ap.add_argument("--out-base", required=True)
    ap.add_argument("--created", help="created.json written by build_assets.py")
    a = ap.parse_args()
    F = json.load(open(a.facts, encoding="utf-8"))
    O = json.load(open(a.overrides, encoding="utf-8")) if a.overrides and os.path.exists(a.overrides) else {}
    created = json.load(open(a.created, encoding="utf-8")) if a.created and os.path.exists(a.created) else []
    rep = build(F, O, a.customer, a.rate, created)
    title = f"Metric Ingest Optimization Review: {a.customer}"
    sub = f"Tenant {F['meta'].get('environment')}  |  {datetime.date.today().isoformat()}"
    md = f"# {title}\n\n{sub}\n\n" + (f"Prepared by {a.author}\n\n" if a.author else "") + rep.md()
    if re.search(r"—", md):
        md = md.replace("—", "-")
    open(a.out_base + ".md", "w", encoding="utf-8").write(md)
    rep.docx(a.out_base + ".docx", title, sub, a.author)
    print(a.out_base + ".md\n" + a.out_base + ".docx")


if __name__ == "__main__":
    main()
