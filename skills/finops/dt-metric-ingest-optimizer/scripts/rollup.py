#!/usr/bin/env python3
"""Compare several tenants side by side from their facts.json files.

    uv run python -X utf8 rollup.py --out rollup.md <dir1>/facts.json <dir2>/facts.json ...

Use after running collect, analyze and (optionally) the report for each tenant. Tenants are never queried together:
each was collected on its own, one at a time.
"""
import argparse, json


def mm(n):
    n = float(n or 0)
    return f"{n/1e9:,.2f}B" if abs(n) >= 1e9 else f"{n/1e6:,.1f}M"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--rate", type=float, default=0.15)
    ap.add_argument("facts", nargs="+")
    a = ap.parse_args()
    rows = []
    for f in a.facts:
        F = json.load(open(f, encoding="utf-8"))
        o = {x["id"]: x for x in F["opportunities"]}
        b = F["billing"]["totals"]
        top_src = (F["sources"] or [{}])[0]
        rows.append({
            "name": F["meta"].get("context"), "billed_d1": b["d1"], "wow": b["pct_d1_vs_d8"], "keys": F["totals"]["billable_keys"],
            "unused": o.get("O1", {}).get("dp_day", 0), "unused_keys": o.get("O1", {}).get("keys", 0), "rare": o.get("O2b", {}).get("dp_day", 0),
            "otel_share": sum(s["c24"] for s in F["sources"] if s["source"] == "opentelemetry") * 100.0 / (F["totals"]["c24_billable"] or 1),
            "top_source": top_src.get("source") or "(none)", "unassigned": F["billing"]["cost_center_unassigned_pct"],
            "detectors": F.get("detectors", {}).get("enabled"), "errors": len(F["errors"]),
        })
    L = ["# Metric ingest across tenants\n",
         "| Tenant | Billed, last day | vs week earlier | Billable keys | Unused, still arriving (a day) | Rarely used (a day) | OpenTelemetry share | Top source | No cost center | Enabled detectors | Collection errors |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['name']} | {mm(r['billed_d1'])} | {r['wow']}% | {r['keys']:,} | {r['unused_keys']:,} keys, {mm(r['unused'])} | {mm(r['rare'])} | {r['otel_share']:.0f}% | {r['top_source']} | {r['unassigned']}% | {r['detectors'] or '-'} | {r['errors']} |")
    L.append(f"\nUnused volume across tenants: {mm(sum(r['unused'] for r in rows))} datapoints a day, about ${sum(r['unused'] for r in rows)*365/1e6*a.rate:,.0f} a year at ${a.rate} per million datapoints (indicative).")
    open(a.out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(a.out)


if __name__ == "__main__":
    main()
