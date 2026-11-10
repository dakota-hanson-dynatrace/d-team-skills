#!/usr/bin/env python3
"""Run the Dynatrace Gen2(Classic)->Gen3 upgrade-readiness checks directly
against a tenant via dtctl, so an agent can diagnose what still blocks the
upgrade.

The check definitions (DQL + JS) are bundled with the skill in
`references/readiness-checks.json` — the skill never fetches a dashboard. It
runs each data check's DQL (`dtctl query`) and each code check's JS
(`dtctl exec function`) against the tenant, and emits one consolidated JSON on
stdout:

    {
      "context": "...", "generated": "...",
      "scope_gaps": ["fleet-management:activegates:read", ...],
      "sections": [
        {"section": "### Log Classic",
         "tiles": [{"id","title","description","type","status","result"|"error"|"skipped"}]}
      ]
    }

The agent interprets each check using its own `description` (which encodes the
🟢 ready / 🟡 in progress / 🔴 action-required / ⚪ n/a semantics).

ponytail: thread-pool for speed, no retries/caching. Add backoff only if the
tenant rate-limits.
"""
import argparse, concurrent.futures as cf, json, re, subprocess, sys, tempfile, os, datetime, time


# Transient failures worth retrying: the OS keyring throttles concurrent token
# reads, and networks blip. Not scope/logic errors — those are permanent.
TRANSIENT = re.compile(r"keyring|retrieve token|connection reset|timeout|temporarily", re.I)


def dtctl(args, ctx, timeout=120, code=None, retries=3):
    """Run a dtctl command. Returns (ok, parsed_or_text, stderr)."""
    cmd = ["dtctl", *args, "-o", "json", "--plain"]
    if ctx:
        cmd += ["--context", ctx]
    for attempt in range(retries):
        ok, res, err = _run(cmd, code, timeout)
        if ok or not TRANSIENT.search(str(err)):
            return ok, res, err
        time.sleep(0.4 * (attempt + 1))
    return ok, res, err


def _run(cmd, code, timeout):
    try:
        p = subprocess.run(cmd, input=code, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, None, f"timeout after {timeout}s"
    out = p.stdout.strip()
    err = p.stderr.strip()
    if out:
        try:
            parsed = json.loads(out)
        except json.JSONDecodeError:
            return (p.returncode == 0), out, err
        # dtctl agent-mode wraps failures in an {ok,result,error} envelope.
        if isinstance(parsed, dict) and {"ok", "result", "error"} <= set(parsed):
            if parsed["ok"]:
                return True, parsed["result"], ""
            e = parsed["error"]
            msg = e.get("message", "") if isinstance(e, dict) else str(e)
            return False, None, msg
        return (p.returncode == 0), parsed, err
    return (p.returncode == 0), None, err or "(no output)"


SCOPE_RE = re.compile(r"required scope\.?\s*Use one of:\s*\[([^\]]+)\]", re.I)


def parse_scopes(text):
    m = SCOPE_RE.search(text or "")
    if not m:
        return []
    return [s.strip() for s in m.group(1).split(",")]


def leading_status(result):
    """Many code tiles self-report status as a leading emoji string."""
    for emoji in ("🔴", "🟡", "🟢", "⚪"):
        s = json.dumps(result, ensure_ascii=False)
        if emoji in s:
            return emoji
    return None


ROW_CAP = 25  # detail tables can hold thousands of rows; keep the report readable.


def cap(result):
    if isinstance(result, list) and len(result) > ROW_CAP:
        return result[:ROW_CAP], len(result)
    return result, None


def run_tile(tile, ctx):
    tid, ttype = tile["id"], tile["type"]
    base = {k: tile[k] for k in ("id", "title", "description", "type", "section")}
    if ttype == "data":
        q = tile["query"]
        if re.search(r"\$[A-Za-z]", q):
            base["skipped"] = "uses a template variable ($AppsStatus/$ApiStatus) not resolved in standalone mode; the summary checks in this area still run"
            return base
        ok, res, err = dtctl(["query", "-f", "-"], ctx, code=q)
        if ok:
            rows = res.get("records", res) if isinstance(res, dict) else res
            base["result"], total = cap(rows)
            if total:
                base["result_total_rows"] = total
        else:
            base["error"] = (err or "")[:300]
            base["scopes_needed"] = parse_scopes(err)
    elif ttype == "code":
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(tile["input"])
            path = f.name
        try:
            ok, res, err = dtctl(["exec", "function", "-f", path], ctx)
        finally:
            os.unlink(path)
        if ok:
            val = res.get("result", res) if isinstance(res, dict) else res
            base["result"], total = cap(val)
            if total:
                base["result_total_rows"] = total
            st = leading_status(base["result"])
            if st:
                base["status"] = st
        else:
            base["error"] = (err or "")[:300]
            base["scopes_needed"] = parse_scopes(err)
    return base


DOCS_RE = re.compile(r"https://docs\.dynatrace\.com/[^\s)\"'\\]+")


def section_doc_links(content):
    """Doc URLs per section, pulled from the section header markdown tiles —
    Dynatrace's own links, so nothing here is fabricated."""
    tiles, layouts = content["tiles"], content["layouts"]
    headers = sorted(
        (layouts.get(k, {}).get("y", 0), t.get("content", ""))
        for k, t in tiles.items()
        if t["type"] == "markdown" and t.get("content", "").strip()
    )
    links = {}
    for _, md in headers:
        name = md.strip().split("\n")[0]
        urls = [u.rstrip(".,") for u in DOCS_RE.findall(md)]
        if urls:
            links.setdefault(name, [])
            for u in urls:
                if u not in links[name]:
                    links[name].append(u)
    return links


def assign_sections(content):
    """Map every data/code tile to its nearest preceding markdown section header."""
    tiles, layouts = content["tiles"], content["layouts"]
    headers = []
    for k, t in tiles.items():
        if t["type"] == "markdown" and t.get("content", "").strip():
            y = layouts.get(k, {}).get("y", 0)
            headers.append((y, t["content"].strip().split("\n")[0]))
    headers.sort()

    def section_for(y):
        name = "(ungrouped)"
        for hy, h in headers:
            if hy <= y:
                name = h
            else:
                break
        return name

    out = []
    for k, t in tiles.items():
        if t["type"] not in ("data", "code"):
            continue
        y = layouts.get(k, {}).get("y", 0)
        out.append({
            "id": k, "type": t["type"],
            "title": t.get("title", ""),
            "description": t.get("description", ""),
            "query": t.get("query", ""),
            "input": t.get("input", ""),
            "section": section_for(y),
            "_y": y,
        })
    return out


CHECKS = os.path.join(os.path.dirname(__file__), "..", "references", "readiness-checks.json")


def absolutize_links(obj, base):
    """Rewrite root-relative Dynatrace links (markdown `](/ui/...)`) in result
    strings to absolute tenant URLs, so deep links work outside the app — e.g.
    in the standalone HTML report, where `/ui/...` would resolve to file:///ui/."""
    if isinstance(obj, str):
        return obj.replace("](/", "](" + base + "/")
    if isinstance(obj, list):
        return [absolutize_links(x, base) for x in obj]
    if isinstance(obj, dict):
        return {k: absolutize_links(v, base) for k, v in obj.items()}
    return obj


def load_checks():
    """Load the bundled check definitions. Single source of truth — no dashboard
    is ever fetched from the tenant."""
    try:
        with open(CHECKS, encoding="utf-8") as f:
            return json.load(f)["content"]
    except (OSError, KeyError, json.JSONDecodeError) as e:
        sys.exit(f"ERROR: could not read bundled check definitions at {CHECKS} ({e}).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--context", help="dtctl context (default: current)")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    ctx = args.context

    # Resolve and validate the target context up front so we never silently run
    # against the wrong tenant.
    ok, ctxs, _ = dtctl(["ctx"], None)
    known = {c["Name"]: c for c in ctxs} if ok and isinstance(ctxs, list) else {}
    if ctx:
        if known and ctx not in known:
            sys.exit(f"ERROR: context '{ctx}' not found. Available: "
                     f"{', '.join(sorted(known)) or '(none)'}.\n"
                     f"Create it with: dtctl ctx set {ctx} "
                     f"--environment https://<env>.apps.dynatrace.com")
        target = ctx
    else:
        target = next((n for n, c in known.items() if c.get("Current") == "*"), "(active)")
    env = known.get(target, {}).get("Environment", "")
    print(f"Target tenant: context '{target}'" + (f"  ->  {env}" if env else ""),
          file=sys.stderr)

    content = load_checks()
    tiles = assign_sections(content)
    print(f"Running {len(tiles)} checks across "
          f"{len({t['section'] for t in tiles})} sections against the tenant...",
          file=sys.stderr)

    results = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(run_tile, t, ctx): t for t in tiles}
        done = 0
        for fut in cf.as_completed(futs):
            results.append(fut.result())
            done += 1
            print(f"  {done}/{len(tiles)}", end="\r", file=sys.stderr)
    print("", file=sys.stderr)

    # Make tenant deep links absolute so they work in the standalone report.
    if env:
        for r in results:
            if "result" in r:
                r["result"] = absolutize_links(r["result"], env)

    # Group by section, preserving the original check order (by y).
    order = {}
    for t in tiles:
        order.setdefault(t["section"], t["_y"])
    scope_gaps = sorted({s for r in results for s in r.get("scopes_needed", []) if s})
    by_section = {}
    for r in results:
        by_section.setdefault(r["section"], []).append(r)
    doc_links = section_doc_links(content)
    sections = [{"section": s,
                 "doc_links": doc_links.get(s, []),
                 "checks": sorted(by_section[s], key=lambda r: int(r["id"]))}
                for s in sorted(by_section, key=lambda s: order.get(s, 0))]

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    json.dump({
        "context": target, "environment_url": env, "generated": now,
        "upgrade_guide": "https://docs.dynatrace.com/docs/shortlink/upgrade-latest-dynatrace",
        "check_count": len(results),
        "scope_gaps": scope_gaps,
        "sections": sections,
    }, sys.stdout, ensure_ascii=False, indent=2)
    print("", file=sys.stderr)
    print(f"Done. {len(results)} checks, {len(scope_gaps)} scope gap(s).", file=sys.stderr)


if __name__ == "__main__":
    main()
