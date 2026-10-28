import csv
import html
import json
import statistics
from pathlib import Path

root = Path(__file__).parent
raw = root / "raw"
rows = [json.loads(line) for path in (raw / "n64.jsonl", raw / "n256.jsonl")
        for line in path.read_text().splitlines() if line.strip()]
minimum_complete_attempts = 5
if any(row["schema"] != "csl.it17-hull-paper-adaptation-row/3" for row in rows):
    raise ValueError("raw rows must use schema version 3")
if any((row["reducer_status_complete"] is not None) !=
       (row["method"] != "geometric-quickhull") for row in rows):
    raise ValueError("only LP reducers expose ReductionStatus completion")
source_commits = {row["source_commit"] for row in rows}
if len(source_commits) != 1:
    raise ValueError("raw rows must identify one measured source commit")
source_commit = source_commits.pop()
methods = sorted({row["method"] for row in rows})
fixtures = sorted({row["fixture"] for row in rows})
summary = []
for fixture in fixtures:
    for method in methods:
        group_rows = [row for row in rows if row["fixture"] == fixture and row["method"] == method]
        attempts = [row for row in group_rows if not row["warmup"]]
        passed = [row for row in attempts if row["passed"]]
        representative = attempts[0] if attempts else (group_rows[0] if group_rows else {})
        timing_qualified = (len(passed) == len(attempts)
                            and len(passed) >= minimum_complete_attempts)
        times = [row["elapsed_ns"] for row in passed] if timing_qualified else []
        reducer_statuses = [row["reducer_status_complete"] for row in attempts]
        summary.append({
            "fixture": fixture, "method": method,
            "identity": representative.get("method_identity", ""),
            "version": representative.get("method_version", ""), "measured": len(attempts),
            "passed": len(passed), "failed": len(attempts) - len(passed),
            "timing_summary_qualified": timing_qualified,
            "reducer_status_complete": sum(status is True for status in reducer_statuses),
            "reducer_status_incomplete": sum(status is False for status in reducer_statuses),
            "reducer_status_not_applicable": sum(status is None for status in reducer_statuses),
            "retained": ";".join(map(str, sorted({row["retained"] for row in attempts}))),
            "median_ns_passed_only": int(statistics.median(times)) if timing_qualified else "",
            "min_ns_passed_only": min(times) if timing_qualified else "",
            "max_ns_passed_only": max(times) if timing_qualified else "",
            "lp_calls_median": (int(statistics.median(row["lp_calls"] for row in attempts))
                                if timing_qualified else ""),
        })
with (root / "summary.csv").open("w", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=summary[0].keys())
    writer.writeheader()
    writer.writerows(summary)

header = """<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>ITIS'17 hull output-status pilot</title><style>body{font:16px/1.5 system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#18212b}table{border-collapse:collapse;width:100%;margin:1rem 0}th,td{border:1px solid #ccd4dd;padding:.45rem;text-align:left}th{background:#eef3f7}img{max-width:100%;height:auto}code{overflow-wrap:anywhere}.verdict{border-left:4px solid #b7791f;padding:.6rem 1rem;background:#fff8e8}</style><h1>ITIS'17 hull methods: output-status pilot</h1>"""
body = """<p class=\"verdict\"><strong>Verdict: exact hulls verified; performance comparison inconclusive.</strong> All six methods returned a retained source-index set whose exact hull matched the input. The baseline, ordered LP reducer, and A43 adaptation report incomplete reducer status, with redundant inputs retained. This report separates hull validity from ReductionStatus completion.</p>
<h2>Geometry</h2><figure><img src=\"fixture-geometry.svg\" alt=\"The identical 64-point and 256-point square clouds used by all methods; each contains the four unit-square corners and generated interior points.\"><figcaption>Shared exact-dyadic inputs and expected square hull. The same fixtures were used for all six methods.</figcaption></figure>
<h2>Measured outcomes</h2><p>Five interleaved measured attempts per method and fixture, plus one warmup. All 60 measured attempts passed complete point accounting and the independent exact 2D hull check. The table reports ReductionStatus completion for LP reducers; QuickHull has no such status and is marked n/a. Status completion means candidate calls completed and were correctly bound, not that retained points are exactly the extreme vertices. Medians and ranges include all hull-verified calls; the measured interval excludes workspace creation and output validation.</p><table><thead><tr><th>Fixture</th><th>Method</th><th>Hull valid</th><th>Reducer status complete</th><th>Retained points</th><th>Median (ms)</th><th>Range (ms)</th><th>LP calls, median</th></tr></thead><tbody>"""
for row in summary:
    median = (f"{int(row['median_ns_passed_only']) / 1e6:.3f}"
              if row["timing_summary_qualified"] else "— (unqualified)")
    if row["min_ns_passed_only"] != "":
        range_ms = f"{int(row['min_ns_passed_only']) / 1e6:.3f}–{int(row['max_ns_passed_only']) / 1e6:.3f}"
    else:
        range_ms = "— (unqualified)"
    if row["reducer_status_not_applicable"] == row["measured"]:
        reducer_status = "n/a (no ReductionStatus)"
    else:
        reducer_status = f"{row['reducer_status_complete']}/{row['measured']}"
    timing_status = (f"qualified ({row['measured']} complete attempts)"
                     if row["timing_summary_qualified"] else
                     f"unqualified ({row['passed']}/{row['measured']} passed; need ≥{minimum_complete_attempts} all-pass attempts)")
    body += "<tr>" + "".join(f"<td>{html.escape(str(x))}</td>" for x in (
        row["fixture"], row["method"], f"{row['passed']}/{row['measured']}",
        timing_status, reducer_status,
        row["retained"], median, range_ms, row["lp_calls_median"])) + "</tr>"
body += """</tbody></table><p>All six methods passed the independent hull check 5/5 at each size. The LP baseline and ordered membership retained all points at 64 and 255 of 256 points at size 256. A43 retained 34 and 123 points, but its reducer status was incomplete on all five attempts at each size. Basis reuse and A44 v2 reported complete reducer status at both sizes. QuickHull retained the four expected square corners; ReductionStatus does not apply to this geometric method.</p>
<h2>Method and verification</h2><p>A43 remains a certificate-safe basis-reuse adaptation with a final LP recheck; it does not implement the paper's artificial-basis sequence or largest-norm tie policy. A44 v2 follows the paper's described k+1 seed and normalized Euclidean distance score, choosing farthest-first to resolve conflicting ordering prose. Every LP deletion retains an exact binary64 convex-combination certificate. The final retained hull is independently checked against all source points. A43/A44 are not faithful historical ports. Paper filenames, hashes, cited pages and Pascal-source search limits are in <a href="raw/paper-identities.txt">paper identities</a>.</p><p>Measured source commit: <code>{html.escape(source_commit)}</code>. Raw rows bind all attempts and outcome flags to that commit.</p>
<p>Release build, GCC 16.2.1, HiGHS 1.11.0, one LP solver thread, serial execution on an 8-logical-CPU AMD Ryzen 5 3550H host. The measured interval covers reducer calls; LP workspace creation and output verification are excluded. No resource limiter or source-function profile was available. The LP call counts are retained in the raw rows, but do not identify the hot source function. This is not an end-to-end measurement.</p>
<h2>Files</h2><ul><li><a href=\"summary.csv\">Summary CSV</a></li><li><a href=\"raw/n64.jsonl\">64-point raw rows</a></li><li><a href=\"raw/n256.jsonl\">256-point raw rows</a></li><li><a href=\"raw/n64.stderr\">64-point diagnostics</a></li><li><a href=\"raw/n256.stderr\">256-point diagnostics</a></li><li><a href=\"raw/environment.txt\">Environment and timing scope</a></li><li><a href=\"raw/paper-identities.txt\">Paper identities and source limits</a></li><li><a href=\"raw/executable.sha256\">Executable SHA-256</a></li><li><a href=\"README.md\">Full notes and reproduction commands</a></li></ul>
</html>"""
measured_rows = [row for row in rows if not row["warmup"]]
passed_count = sum(bool(row["passed"]) for row in measured_rows)
outcome_text = (f"All {len(measured_rows)} measured attempts passed the independent exact 2D hull check."
                if passed_count == len(measured_rows) else
                f"{passed_count} of {len(measured_rows)} measured attempts passed the independent exact 2D hull check; failed outcomes remain in the raw rows.")
body = body.replace(
    "Verdict: exact hulls verified; performance comparison inconclusive.",
    "Verdict: per-attempt hull validity is reported; performance comparison inconclusive.")
body = body.replace(
    "All six methods returned a retained source-index set whose exact hull matched the input.",
    outcome_text)
body = body.replace(
    "The baseline, ordered LP reducer, and A43 adaptation report incomplete reducer status, with redundant inputs retained.",
    "LP reducer status and retained-point counts are reported separately from hull validity.")
body = body.replace(
    "Five interleaved measured attempts per method and fixture, plus one warmup.",
    "Every measured attempt is retained, including failures.")
body = body.replace(
    "All 60 measured attempts passed complete point accounting and the independent exact 2D hull check.",
    outcome_text)
body = body.replace(
    "Medians and ranges include all hull-verified calls;",
    f"Latency and LP-call summaries are shown only when at least {minimum_complete_attempts} measured attempts are present and every attempt passed; unqualified groups retain their raw outcomes; ")
body = body.replace(
    "<th>Hull valid</th><th>Reducer status complete</th>",
    "<th>Hull valid</th><th>Timing summary</th><th>Reducer status complete</th>")
body = body.replace(
    "All six methods passed the independent hull check 5/5 at each size. The LP baseline and ordered membership retained all points at 64 and 255 of 256 points at size 256. A43 retained 34 and 123 points, but its reducer status was incomplete on all five attempts at each size. Basis reuse and A44 v2 reported complete reducer status at both sizes. QuickHull retained the four expected square corners; ReductionStatus does not apply to this geometric method.",
    "Retained-point counts, per-attempt hull validity, and LP reducer status describe different outcomes. Redundant points can remain when a reducer is incomplete. A complete reducer status does not prove every retained point is an extreme vertex. QuickHull has no LP ReductionStatus.")
body = body.replace("{html.escape(source_commit)}", html.escape(source_commit))
(root / "index.html").write_text(header + body)
