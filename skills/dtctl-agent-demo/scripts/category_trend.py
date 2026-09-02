#!/usr/bin/env python3
"""Render dtctl query output with dynatui-style threshold coloring + inline sparkline.

ponytail: one batched timeseries query supplies every row's trend (dynatui's
enrichCap pattern) instead of one dtctl call per category. Coloring is a fixed
red/yellow/green band; swap for real percentile thresholds when this graduates
past a demo script.
"""
import json
import subprocess
import sys

RED, YELLOW, GREEN, DIM, RESET, BOLD = (
    "\033[31m", "\033[33m", "\033[32m", "\033[2m", "\033[0m", "\033[1m",
)
BLOCKS = "▁▂▃▄▅▆▇█"


def dtctl_json(query: str) -> list[dict]:
    out = subprocess.run(
        ["dtctl", "--context", "demo-live", "query", query, "-o", "json", "--plain"],
        capture_output=True, text=True, check=True,
    ).stdout
    return json.loads(out)["result"]["records"]


def sparkline(values: list[float]) -> str:
    lo, hi = min(values), max(values)
    span = hi - lo or 1
    return "".join(BLOCKS[int((v - lo) / span * (len(BLOCKS) - 1))] for v in values)


def band(total: int) -> tuple[str, str]:
    if total >= 8:
        return RED, "CRITICAL"
    if total >= 3:
        return YELLOW, "WARNING"
    return GREEN, "OK"


def main() -> None:
    counts = dtctl_json(
        'fetch dt.davis.problems, from: now()-7d '
        '| filter event.kind == "DAVIS_PROBLEM" and event.status == "ACTIVE" '
        '| dedup event.id | summarize total = count(), by: {event.category} '
        "| sort total desc"
    )
    trends = {
        r["event.category"]: r["count"]
        for r in dtctl_json(
            'fetch dt.davis.problems, from: now()-14d '
            '| filter event.kind == "DAVIS_PROBLEM" '
            "| makeTimeseries count = count(), by: {event.category}, interval: 1d"
        )
    }

    max_total = max(int(r["total"]) for r in counts)
    name_w = max(len(r["event.category"]) for r in counts)

    print(f"{BOLD}ACTIVE PROBLEMS BY CATEGORY{RESET}  (demo-live, last 7d)\n")
    for r in counts:
        cat, total = r["event.category"], int(r["total"])
        color, label = band(total)
        bar_w = 30
        filled = max(1, round(total / max_total * bar_w))
        bar = color + "█" * filled + DIM + "░" * (bar_w - filled) + RESET
        spark = trends.get(cat)
        spark_str = f"  {DIM}trend{RESET} {color}{sparkline(spark)}{RESET}" if spark else ""
        print(f"{cat:<{name_w}}  {bar}  {color}{total:>3} {label:<8}{RESET}{spark_str}")


if __name__ == "__main__":
    sys.exit(main())
