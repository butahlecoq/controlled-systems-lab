#!/usr/bin/env python3
"""Render the saved HORIZON-01 summary as a standalone HTML report."""

from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path


def fmt_ns(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "—"
    return f"{value / 1_000_000:.3f} ms"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True, type=Path)
    args = parser.parse_args()
    bundle = args.bundle.resolve(strict=True)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((bundle / "summary.json").read_text(encoding="utf-8"))
    build = json.loads((bundle / "build-provenance.json").read_text(encoding="utf-8"))
    checks = [json.loads(line) for line in (bundle / "checks.jsonl").read_text(encoding="utf-8").splitlines() if line]
    statuses = {status: sum(row.get("status") == status for row in checks)
                for status in ("verified", "inconclusive", "incorrect", "unavailable")}
    table_rows = []
    representation_rows = []
    all_pairs_verified = all(case.get("verified_paired_repetitions") == 6
                             for case in summary["horizons"])
    for case in summary["horizons"]:
        strategies = case["strategies"]
        def strategy_row(strategy: str) -> str:
            data = strategies.get(strategy, {})
            lo = data.get("min_strategy_run_ns_within_verified_pairs")
            hi = data.get("max_strategy_run_ns_within_verified_pairs")
            median = data.get("median_strategy_run_ns_within_verified_pairs")
            return (f"<td>{escape(fmt_ns(median))}</td><td>{escape(fmt_ns(lo))} – "
                    f"{escape(fmt_ns(hi))}</td>")
        table_rows.append(
            "<tr>" + f"<th scope=\"row\">T={case['horizon']}</th>" +
            strategy_row("csl.synthesis.reach-back") +
            strategy_row("csl.synthesis.strategy-b") +
            f"<td>{case['verified_attempts']}/12</td><td>{case['verified_paired_repetitions']}/6</td></tr>"
        )
        for strategy, label in (("csl.synthesis.reach-back", "Reach-back"),
                                ("csl.synthesis.strategy-b", "Strategy B")):
            shapes = strategies.get(strategy, {}).get("verified_representation_shapes", [])
            for shape in shapes:
                representation_rows.append(
                    f"<tr><th scope=\"row\">T={case['horizon']}</th><td>{escape(label)}</td>"
                    f"<td>{shape['joint_coordinates']}</td><td>{shape['inequality_rows']}</td>"
                    f"<td>{shape['equality_rows']}</td><td>{shape['nonzero_h_coefficients']}</td></tr>"
                )
    env = manifest["environment"]
    sources = " ".join(f"{escape(name)}: {escape(digest)}" for name, digest in
                        sorted(env["measurement_source_sha256"].items()))
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>HORIZON-01 scalar horizon pilot</title>
<style>
:root{{color-scheme:light dark;font:16px/1.55 system-ui,sans-serif}}body{{max-width:1080px;margin:2rem auto;padding:0 1rem}}
h1,h2{{line-height:1.2}}.scope{{border-left:5px solid #b57900;padding:.75rem 1rem;background:color-mix(in srgb,#b57900 12%,transparent)}}
table{{border-collapse:collapse;width:100%;margin:1rem 0}}th,td{{border:1px solid #888;padding:.55rem;text-align:left}}th{{background:color-mix(in srgb,#888 18%,transparent)}}
code{{overflow-wrap:anywhere}}.counts{{display:flex;gap:1rem;flex-wrap:wrap}}.counts span{{padding:.4rem .7rem;border:1px solid #888;border-radius:.4rem}}
</style></head><body>
<h1>HORIZON-01: scalar integrator horizon pilot</h1>
<p>This report records a synthetic scalar integrator run at horizons 2, 4, and 8.
Each horizon has one excluded warmup pair and six measured alternating pairs. The timed interval is
<code>SynthesisWorkspace::run()</code>; process launch and setup are excluded.</p>
<p class="scope"><strong>Evidence limit:</strong> {"Each relation passed the fixture-specific exact analytic oracle, and timing rows below include only the six matched pairs where both strategies passed." if all_pairs_verified else "Timing rows below include only matched pairs where both strategy outputs passed the fixture-specific analytic oracle."}
These are descriptive timings, not a performance ranking, speedup, general completeness, or complexity claim.</p>
<h2>Results</h2>
<table><thead><tr><th scope="col">Horizon</th><th scope="col">Reach-back median†</th><th scope="col">Reach-back range†</th>
<th scope="col">Strategy B median†</th><th scope="col">Strategy B range†</th><th scope="col">Verified attempts</th><th scope="col">Verified pairs</th></tr></thead>
<tbody>{''.join(table_rows)}</tbody></table>
<p>† Median and range use only matched, independently verified measured pairs; inconclusive and failed outcomes are retained but excluded from timing summaries. Raw records are available in <a href="attempts.jsonl">attempts.jsonl</a>;
independent result checks are in <a href="checks.jsonl">checks.jsonl</a>, with per-horizon details in <a href="summary.json">summary.json</a>.</p>
<h2>Representation and output growth</h2>
<p>The scalar state/control dimensions stay fixed while the horizon grows. The relation coordinate count, H-row counts, and nonzero H coefficients are counted from each emitted candidate relation after its independent check. These counts do not measure allocated bytes.</p>
<table><thead><tr><th scope="col">Horizon</th><th scope="col">Strategy</th><th scope="col">Joint coordinates</th><th scope="col">Inequality rows</th><th scope="col">Equality rows</th><th scope="col">Nonzero H coefficients</th></tr></thead>
<tbody>{''.join(representation_rows)}</tbody></table>
<h2>Analytic fixture</h2>
<pre><code>x[t+1] = x[t] + u[t], x[0] = 0, 0 &lt;= u[t] &lt;= 1; minimize x[T].</code></pre>
<p>Because <code>x[T] = sum(u[t])</code>, the exact optimal value is 0, attained by the all-zero history.
The checker verifies each relation includes that history, contains the initial, transition, and control-bound rows, and imposes <code>x[T] &lt;= 0</code> (or equality). Together with <code>x[T] = sum(u[t])</code> and <code>u[t] &gt;= 0</code>, these conditions force the relation to be exactly the singleton all-zero optimum for these fixtures. This is a fixture-specific independent proof; neither strategy's general candidate-family completeness is inferred.</p>
<h2>Run environment</h2>
<p>Host: <code>{escape(str(env.get('host')))}</code>; platform: <code>{escape(str(env.get('platform')))}</code>;
architecture: <code>{escape(str(env.get('machine')))}</code>; logical CPUs: <code>{escape(str(env.get('logical_cpus')))}</code>;
physical memory: <code>{escape(str(env.get('physical_memory_bytes')))} bytes</code>;
binary SHA-256: <code>{escape(str(env.get('binary_sha256')))}</code>; source revision: <code>{escape(str(env.get('source_revision')))}</code>.</p>
<p>Build: {escape(str(build.get('build_type')))} with {escape(str(build.get('cxx_compiler')))},
CMake {escape(str(build.get('cmake_version')))}, Ninja {escape(str(build.get('ninja_version')))}.
See <a href="build-provenance.json">build provenance</a> and the full <a href="build.log">build log</a>.</p>
<p>Each process requested one backend thread and used one driver worker. Observed backend scheduler widths and explicit unavailable counts are in <a href="summary.json">summary.json</a>.</p>
<p>Attempt checks: <span class="counts">{''.join(f'<span>{escape(k)}: {v}</span>' for k,v in statuses.items())}</span></p>
<p>Measurement source hashes: <code>{sources}</code></p>
<p>Fixture inputs: <a href="inputs/horizon01-t02.json">T=2</a>, <a href="inputs/horizon01-t04.json">T=4</a>,
<a href="inputs/horizon01-t08.json">T=8</a>. See the <a href="README.md">benchmark instructions</a> for rebuild and replay commands.</p>
</body></html>
"""
    (bundle / "index.html").write_text(document, encoding="utf-8")
    print(bundle / "index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
