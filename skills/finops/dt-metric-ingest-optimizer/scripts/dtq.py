"""Shared dtctl helpers for the metric-ingest-optimizer skill.

Rules baked in (each one cost a debugging session once):
- Run dtctl calls SEQUENTIALLY. Concurrent calls refreshed the OAuth token at the same time and wiped it.
- Pass DQL through a file. PowerShell 5.1 strips the double quotes out of inline queries.
- dtctl 0.28 has no --limit or --jq. Use --max-result-records on `query` only.
- `dtctl auth login` resets a context to readwrite-all. Always read the safety level back afterwards.
"""
import json, os, subprocess, tempfile


class Tenant:
    def __init__(self, ctx, out):
        self.ctx, self.out = ctx, out
        self.raw = os.path.join(out, "raw")
        os.makedirs(self.raw, exist_ok=True)
        self.errors, self.warnings = [], []

    # -- low level ---------------------------------------------------------------------------------
    def _run(self, args, timeout):
        return subprocess.run(["dtctl", *args, "--context", self.ctx], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)

    def q(self, name, dql, max_records=100000, timeout=170, save=True):
        """Run DQL, return the list of records ([] on any failure, which is recorded in self.errors)."""
        with tempfile.NamedTemporaryFile("w", suffix=".dql", delete=False, encoding="utf-8") as f:
            f.write(dql)
            path = f.name
        try:
            p = self._run(["query", "-f", path, "-o", "json", "--plain", "--max-result-records", str(max_records)], timeout)
        except subprocess.TimeoutExpired:
            self.errors.append(f"{name}: timed out after {timeout}s")
            return []
        finally:
            os.unlink(path)
        err = (p.stderr or "").strip()
        if p.returncode != 0:
            self.errors.append(f"{name}: {err[:200] or p.stdout[:200]}")
            return []
        if "scan" in err.lower() and "limit" in err.lower():
            self.warnings.append(f"{name}: hit the Grail scan limit, result is partial")
        try:
            j = json.loads(p.stdout)
        except ValueError:
            self.errors.append(f"{name}: unparseable output")
            return []
        recs = j.get("records", j) if isinstance(j, dict) else j
        if save:
            json.dump(recs, open(os.path.join(self.raw, f"{name}.json"), "w", encoding="utf-8"))
        return recs or []

    def get_json(self, args, timeout=300):
        """dtctl get ... -o json --plain. Returns parsed JSON or None."""
        p = self._run(["get", *args, "-o", "json", "--plain"], timeout)
        if p.returncode != 0:
            self.errors.append(f"get {' '.join(args)}: {(p.stderr or '').strip()[:160]}")
            return None
        try:
            j = json.loads(p.stdout)
        except ValueError:
            return None
        return j.get("result", j) if isinstance(j, dict) else j


def num(x, d=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def contexts():
    """List dtctl contexts as dicts: Name, Environment, SafetyLevel."""
    p = subprocess.run(["dtctl", "config", "get-contexts", "-o", "json", "--plain"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    j = json.loads(p.stdout)
    return j.get("result", j) if isinstance(j, dict) else j


def safety_level(ctx):
    for c in contexts():
        if c.get("Name") == ctx:
            return c.get("SafetyLevel")
    return None


def set_safety(ctx, level):
    p = subprocess.run(["dtctl", "config", "set-context", ctx, "--safety-level", level], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return p.returncode == 0
