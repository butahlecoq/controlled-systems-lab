import csv
import html
import json
import statistics
from pathlib import Path

root = Path(__file__).parent
raw = root / "raw"
rows = [json.loads(line) for path in (raw / "n64.jsonl", raw / "n256.jsonl")
        for line in path.read_text().splitlines() if line.strip()]
source_commits = {row["source_commit"] for row in rows}
if len(source_commits) != 1:
    raise ValueError("raw rows must identify one measured source commit")
source_commit = source_commits.pop()
methods = sorted({row["method"] for row in rows})
fixtures = sorted({row["fixture"] for row in rows})
summary = []
for fixture in fixtures:
    for method in methods:
        attempts = [row for row in rows if row["fixture"] == fixture and row["method"] == method and not row["warmup"]]
        passed = [row for row in attempts if row["passed"]]
        times = [row["elapsed_ns"] for row in passed]
        summary.append({
            "fixture": fixture, "method": method, "identity": attempts[0]["method_identity"],
            "version": attempts[0]["method_version"], "measured": len(attempts),
            "passed": len(passed), "failed": len(attempts) - len(passed),
            "retained": ";".join(map(str, sorted({row["retained"] for row in attempts}))),
            "median_ns_passed_only": int(statistics.median(times)) if times else "",
            "min_ns_passed_only": min(times) if times else "",
            "max_ns_passed_only": max(times) if times else "",
            "lp_calls_median": int(statistics.median(row["lp_calls"] for row in attempts)),
        })
with (root / "summary.csv").open("w", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=summary[0].keys())
    writer.writeheader()
    writer.writerows(summary)

header = """<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>ITIS'17 A44 hull comparison v2</title><style>body{font:16px/1.5 system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#18212b}table{border-collapse:collapse;width:100%;margin:1rem 0}th,td{border:1px solid #ccd4dd;padding:.45rem;text-align:left}th{background:#eef3f7}img{max-width:100%;height:auto}code{overflow-wrap:anywhere}.verdict{border-left:4px solid #b7791f;padding:.6rem 1rem;background:#fff8e8}</style><h1>ITIS'17 A44 hull comparison, implementation v2</h1>"""
body = """<p class=\"verdict\"><strong>Verdict: inconclusive as a performance comparison.</strong> This bounded 2D pilot establishes passing geometry outcomes for the A44 v2 implementation on two interior-heavy square clouds. It does not support a general speed or scalability claim.</p>
<h2>Geometry</h2><figure><img src=\"fixture-geometry.svg\" alt=\"The identical 64-point and 256-point square clouds used by all methods; each contains the four unit-square corners and generated interior points.\"><figcaption>Shared exact-dyadic inputs and expected square hull. The same fixtures were used for all six methods.</figcaption></figure>
<h2>Measured outcomes</h2><p>Five measured attempts per method and fixture, plus one warmup per method and fixture. Medians and ranges below include only attempts that passed all driver and independent hull checks. Failed attempts remain in the raw files and are counted in the table.</p><table><thead><tr><th>Fixture</th><th>Method</th><th>Passes</th><th>Failures</th><th>Retained points</th><th>Passing median (ms)</th><th>Passing range (ms)</th><th>LP calls, median</th></tr></thead><tbody>"""
for row in summary:
    median = f"{int(row['median_ns_passed_only']) / 1e6:.3f}" if row["median_ns_passed_only"] != "" else "—"
    if row["min_ns_passed_only"] != "":
        range_ms = f"{int(row['min_ns_passed_only']) / 1e6:.3f}–{int(row['max_ns_passed_only']) / 1e6:.3f}"
    else:
        range_ms = "—"
    body += "<tr>" + "".join(f"<td>{html.escape(str(x))}</td>" for x in (
        row["fixture"], row["method"], f"{row['passed']}/{row['measured']}", row["failed"],
        row["retained"], median, range_ms, row["lp_calls_median"])) + "</tr>"
body += """</tbody></table><p>Passing rows: geometric QuickHull, phase-one basis reuse, and A44 v2. The LP baseline, ordered membership, and A43 certificate-safe adaptation failed their completion checks on every measured attempt. Their diagnostic elapsed times are not performance results. A44 v2 passed 5/5 at both sizes and retained the four expected corners.</p>
<h2>Method and verification</h2><p>A44 v2 follows the paper's described k+1 seed and normalized Euclidean distance score, choosing farthest-first to resolve the paper's conflict between its “increasing distance” sentence and its description of the first k+1 points as farthest. Every removal remains authorized by an exact binary64 convex-combination certificate. The final retained hull is independently checked against all source points. Its identity is <code>csl.hull.itis17.a44-incremental-lp@2.0.0</code>; earlier v1 measurements remain distinct.</p><p>Measured source commit: <code>{html.escape(source_commit)}</code>. Raw rows bind all attempts and outcome flags to that commit.</p>
<p>Release build, GCC 16.2.1, HiGHS 1.11.0, one LP solver thread, serial execution on an 8-logical-CPU AMD Ryzen 5 3550H host. The measured interval covers reducer calls; LP workspace creation and output verification are excluded. No resource limiter was enforced. A separate unreported profile observed the process near 100% of one logical CPU. A44 v2 made a median of 65 and 257 LP calls on the 64 and 256 point clouds, respectively; LP solving is the likely limiter, but the profiler did not sample source functions. This is not an end-to-end measurement.</p>
<h2>Files</h2><ul><li><a href=\"summary.csv\">Summary CSV</a></li><li><a href=\"raw/n64.jsonl\">64-point raw rows</a></li><li><a href=\"raw/n256.jsonl\">256-point raw rows</a></li><li><a href=\"raw/n64.stderr\">64-point diagnostics</a></li><li><a href=\"raw/n256.stderr\">256-point diagnostics</a></li><li><a href=\"raw/top-profile.txt\">Separate CPU profile</a></li><li><a href=\"README.md\">Full notes and reproduction commands</a></li></ul>
</html>"""
body = body.replace("{html.escape(source_commit)}", html.escape(source_commit))
(root / "index.html").write_text(header + body)
