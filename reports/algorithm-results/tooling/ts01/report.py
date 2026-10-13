"""Canonical T-S01 result record validation and standalone HTML rendering."""
from __future__ import annotations

import html
from fractions import Fraction
import hashlib
import json

SCHEMA = "csl.syn07-ts01-analytic-report/1"
SOURCE_COMMIT = "fe5095ce27ab4872cb31df32fab6f3b1b073f4f6"
COORDINATES = ["x0", "x1", "x2", "u0", "u1"]


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def contains(point):
    if len(point) != 5:
        return False
    if any(type(value) not in (int, float) for value in point):
        return False
    try:
        p = [Fraction.from_float(float(x)) for x in point]
    except (TypeError, ValueError, OverflowError):
        return False
    return p[0] == 0 and p[1] == p[3] and p[2] == 1 and 0 <= p[3] <= 1 and 0 <= p[4] <= 1 and p[3] + p[4] == 1


def validate(record):
    errors = []
    if record.get("schema") != SCHEMA:
        errors.append("schema")
    if record.get("source_commit") != SOURCE_COMMIT:
        errors.append("source_commit")
    if record.get("coordinates") != COORDINATES:
        errors.append("coordinates")
    relation = record.get("canonical_relation", {})
    if relation.get("dimension") != 5 or relation.get("equalities") != [[1,0,0,0,0],[0,1,0,-1,0],[0,0,1,0,0],[0,0,0,1,1]] or relation.get("equality_rhs") != [0,0,1,1] or relation.get("inequalities") != [[0,0,0,-1,0],[0,0,0,1,0],[0,0,0,0,-1],[0,0,0,0,1]] or relation.get("inequality_rhs") != [0,1,0,1]:
        errors.append("canonical_relation")
    examples = record.get("membership_examples", [])
    expected = {"s=0", "s=1/4", "s=1", "s=1-2^-53", "feasible_nonoptimal_zero", "feasible_nonoptimal_endpoint", "off_relation_dyadic_perturbation"}
    if {row.get("id") for row in examples} != expected:
        errors.append("membership_inventory")
    for row in examples:
        if row.get("actual_member") is not contains(row.get("point", [])) or row.get("expected_member") is not row.get("actual_member"):
            errors.append("membership_result:" + str(row.get("id")))
    performance = record.get("performance", {})
    measurement = record.get("measurement")
    if performance.get("status") == "unavailable":
        if measurement is not None:
            errors.append("measurement_unexpected")
    elif performance.get("status") == "exploratory_single_strategy" and isinstance(measurement, dict):
        events = measurement.get("events", [])
        expected_order = [(0, True), *[(i, False) for i in range(1, 8)]]
        if len(events) != 8 or [(row.get("repetition"), row.get("warmup")) for row in events] != expected_order:
            errors.append("measurement_event_matrix")
        if any(row.get("schema") != "csl.syn07-ts01-measurement-event/1" or row.get("status") != "passed" or
               type(row.get("elapsed_ns")) is not int or row["elapsed_ns"] < 0 or not row.get("observation_token") for row in events):
            errors.append("measurement_event_invalid")
        if measurement.get("performance_conclusion") != "inconclusive" or measurement.get("counts", {}).get("failed") != 0 or measurement.get("counts", {}).get("measured") != 7:
            errors.append("measurement_scope_invalid")
    else:
        errors.append("performance_status")
    return errors


def render_html(record):
    errors = validate(record)
    if errors:
        raise ValueError("invalid saved T-S01 record: " + ", ".join(errors))
    esc = lambda x: html.escape(str(x))
    rows = "".join("<tr><th scope=\"row\">" + esc(r["id"]) + "</th><td><code>" + esc(json.dumps(r["point"], separators=(",", ":"))) + "</code></td><td>" + ("member" if r["actual_member"] else "not a member") + "</td><td>" + esc(r["reason"]) + "</td></tr>" for r in record["membership_examples"])
    assumptions = "".join("<li>" + esc(x) + "</li>" for x in record["assumptions"])
    limits = "".join("<li>" + esc(x) + "</li>" for x in record["evidence_limits"])
    measurement = record.get("measurement")
    if measurement:
        summary = measurement["timing_ns"]
        performance = ("<p>Exploratory single-strategy observations. One excluded warmup preceded seven measured repetitions; all seven returned the expected complete H-relation and passed exact-membership checks. Timing scope: " + esc(measurement["scope"]) + ".</p>"
            "<p>Median " + esc(summary["median"]) + " ns; range " + esc(summary["min"]) + "–" + esc(summary["max"]) + " ns (width " + esc(summary["range"]) + " ns). No comparison or speedup is claimed. Performance conclusion: <strong>inconclusive</strong>; no separate limiter profile was collected.</p>"
            "<p>Raw data: <a href=\"measurement-events.jsonl\">measurement JSONL</a> · <a href=\"timings.csv\">timing CSV</a> · <a href=\"measurement.json\">measurement summary</a>.</p>")
    else:
        performance = "<p>Unavailable. No standalone public-path T-S01 measurement executable was present in the pinned algorithm source. No proxy timing is reported.</p>"
    parts = [
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>T-S01 exact analytic family</title>',
        '<style>body{font:16px/1.55 system-ui,sans-serif;max-width:72rem;margin:2rem auto;padding:0 1rem;color:#18232d}h1,h2{line-height:1.2}table{border-collapse:collapse;width:100%;margin:1rem 0}th,td{border:1px solid #8795a1;padding:.55rem;text-align:left;vertical-align:top}code,pre{font-family:ui-monospace,monospace}pre{overflow:auto;background:#f2f5f7;padding:1rem}.note{border-left:4px solid #a36a00;padding:.5rem 1rem;background:#fff8e8}svg{max-width:100%;height:auto}</style></head><body>',
        '<h1>T-S01 exact analytic family</h1><p>Versioned result record <code>' + esc(record["report_id"]) + '</code>, sourced from commit <code>' + SOURCE_COMMIT + '</code>. Strategy <code>csl.synthesis.ts01-analytic</code> version 1; profile <code>ts01_exact_integrator</code>.</p>',
        '<h2>Strict admitted profile</h2><ul>' + assumptions + '</ul>',
        '<h2>Complete canonical relation for this profile</h2><p>For <code>x₀=0</code>, <code>xₜ₊₁=xₜ+uₜ</code>, and <code>u₀,u₁∈[0,1]</code>, the terminal objective is <code>J(x₂)=x₂²−2x₂+1=(x₂−1)²</code>. Since <code>x₂=u₀+u₁</code>, its minimum is zero and is attained exactly when <code>u₀+u₁=1</code>. Thus every optimal joint history, and only such a history, is</p><pre>(x₀,x₁,x₂,u₀,u₁) = (0,s,1,s,1−s),  0 ≤ s ≤ 1.</pre>',
        '<p>The canonical coordinates are <code>(x0,x1,x2,u0,u1)</code>. The exact H-representation is saved in <a href="records.json">records.json</a>.</p>',
        '<figure aria-label="Optimal controls form the closed segment u0 plus u1 equals one"><svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Line segment in the unit square from u0 zero u1 one to u0 one u1 zero" viewBox="0 0 520 300" width="520" height="300"><line x1="70" y1="240" x2="450" y2="240" stroke="#18232d" stroke-width="2"></line><line x1="70" y1="240" x2="70" y2="35" stroke="#18232d" stroke-width="2"></line><line x1="70" y1="35" x2="450" y2="240" stroke="#087e8b" stroke-width="5"></line><circle cx="70" cy="35" r="6" fill="#087e8b"></circle><circle cx="450" cy="240" r="6" fill="#087e8b"></circle><text x="250" y="278" text-anchor="middle" font-size="16">u0</text><text x="24" y="140" text-anchor="middle" font-size="16">u1</text><text x="60" y="263" font-size="14">0</text><text x="445" y="263" font-size="14">1</text><text x="48" y="43" font-size="14">1</text><text x="83" y="49" font-size="14">(0,1)</text><text x="400" y="228" font-size="14">(1,0)</text><text x="185" y="115" font-size="15">u0 + u1 = 1</text></svg><figcaption>The entire optimal control relation is the closed line segment; the canonical states are x0=0, x1=u0, x2=1.</figcaption></figure>',
        '<h2>Exact binary64 membership examples</h2><p>The public relation query uses exact dyadic arithmetic for finite binary64 coordinates.</p><table><thead><tr><th scope="col">Example</th><th scope="col">Coordinates</th><th scope="col">Result</th><th scope="col">Why</th></tr></thead><tbody>' + rows + '</tbody></table>',
        '<h2>Assurance and completeness boundary</h2><p class="note">The relation is complete for the narrowly admitted analytic T-S01 profile. The outer API still reports <strong>numerical assurance</strong>; validated assurance is unavailable. This is not a general strategy or a proof-replayable serialized capability.</p><ul>' + limits + '</ul>',
        '<h2>Performance</h2>' + performance,
        '<h2>Reproduction</h2><pre>git checkout ' + SOURCE_COMMIT + '\ncmake -S . -B build/ts01-report -G \'Visual Studio 17 2022\' -A x64 -DBUILD_TESTING=ON -DCSL_BUILD_SYN07_REPORT=ON\ncmake --build build/ts01-report --config Release --target csl_syn07_ts01_report --parallel 4\nbuild/ts01-report/Release/csl_syn07_ts01_report.exe  # one warmup plus seven measured repetitions; raw JSONL\nctest --test-dir build/ts01-report -C Release --output-on-failure -R strategy_ts01_analytic_profile_tests\npython reports/algorithm-results/tooling/ts01/report.py --check reports/algorithm-results/' + esc(record["report_id"]) + '/records.json</pre>',
        '<p>Membership rows and their raw JSONL/CSV projections are version-controlled with this standalone page. The HTML embeds all styling and figures and needs no network access.</p></body></html>',
    ]
    return "".join(parts)


if __name__ == "__main__":
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("records")
    args = parser.parse_args()
    saved = json.loads(Path(args.records).read_text(encoding="utf-8"))
    errors = validate(saved)
    if errors:
        raise SystemExit("invalid record: " + ", ".join(errors))
    if args.check:
        print("T-S01 saved record valid")
    else:
        print(render_html(saved))
