#!/usr/bin/env python3
"""Render and validate the saved EXT-04 affine-synthesis run."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
from pathlib import Path
import re
import statistics
import subprocess
import zipfile


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fixture() -> dict:
    return {
        "id": "ext04-one-stage-noisy-integrator-v1",
        "dynamics": "x_next = [[1,1],[0,1]] x + [[-1],[0]] u",
        "observation": "y = x1 + e, measured and available before decision 0",
        "initial_generators": [[-1, -0.05], [-1, 0.05], [1, -0.05], [1, 0.05]],
        "measurement_error_vertices": [-0.1, 0.1],
        "action_bounds": [-1.101, 1.101],
        "terminal_bounds": {"x1": [-0.16, 0.16], "x2": [-0.051, 0.051]},
        "feasibility_tolerance": 1e-9,
        "joint_vertices": 8,
    }


def expected_initials() -> list[tuple[float, float, float]]:
    return [(x1, x2, error)
            for x1 in (-1.0, 1.0)
            for x2 in (-0.05, 0.05)
            for error in (-0.1, 0.1)]


def check_result(value: dict) -> None:
    if (value.get("assurance") != "numerical" or
            value.get("coverage") != "all_joint_uncertainty" or
            value.get("feasibility") != "within_tolerance" or
            value.get("solver_outcome") != "optimal"):
        raise ValueError("synthesis outcome scope differs")
    gain, offset = value.get("policy_gain"), value.get("policy_offset")
    if any(type(number) not in (int, float) or not math.isfinite(number)
           for number in (gain, offset)):
        raise ValueError("synthesized policy coefficients are nonfinite")
    rows = value.get("generators")
    if not isinstance(rows, list) or len(rows) != 8:
        raise ValueError("the report must retain all eight joint generators")
    for row, (x1, x2, error) in zip(rows, expected_initials(), strict=True):
        observation = x1 + error
        action = gain * observation + offset
        terminal = [x1 + x2 - action, x2]
        if (row.get("initial") != [x1, x2] or
                row.get("measurement_error") != error or
                abs(row.get("observation", math.inf) - observation) > 1e-12 or
                abs(row.get("action", math.inf) - action) > 1e-12 or
                any(abs(actual - expected) > 1e-12
                    for actual, expected in zip(row.get("terminal", []), terminal, strict=True))):
            raise ValueError("saved generator replay differs from the independent plant calculation")
        if (abs(action) > 1.101 or abs(terminal[0]) > 0.16 or abs(terminal[1]) > 0.051):
            raise ValueError("independent action or terminal safety check failed")
        if any(margin < -1e-12 for margin in row.get("action_margins", []) + row.get("terminal_margins", [])):
            raise ValueError("saved safety margin is negative")


def svg(result: dict) -> str:
    scale, center_x, center_y = 200.0, 340.0, 292.0

    def point(state: list[float] | tuple[float, float]) -> tuple[float, float]:
        return center_x + scale * state[0], center_y - scale * state[1]

    initial = [[-1, -0.05], [1, -0.05], [1, 0.05], [-1, 0.05]]
    polygon = " ".join(f"{x:.3f},{y:.3f}" for x, y in map(point, initial))
    elements = [f'<polygon points="{polygon}" fill="#b4cda3" fill-opacity=".22" '
                'stroke="#b4cda3" stroke-width="2.5"/>']
    for coordinate in (-1, -0.5, 0, 0.5, 1):
        x, y = point((coordinate, coordinate))
        elements += [f'<line x1="{x}" y1="52" x2="{x}" y2="532" stroke="#3c493d"/>',
                     f'<line x1="100" y1="{y}" x2="580" y2="{y}" stroke="#3c493d"/>',
                     f'<text x="{x}" y="554" text-anchor="middle">{coordinate:g}</text>',
                     f'<text x="86" y="{y+5}" text-anchor="end">{coordinate:g}</text>']
    for row in result["generators"]:
        start = point(row["initial"])
        end = point(row["terminal"])
        elements.append(f'<line x1="{start[0]:.3f}" y1="{start[1]:.3f}" '
                        f'x2="{end[0]:.3f}" y2="{end[1]:.3f}" '
                        'stroke="#77b8c5" stroke-width="1.5" opacity=".8" marker-end="url(#arrow)"/>')
        elements.append(f'<circle cx="{end[0]:.3f}" cy="{end[1]:.3f}" r="4.5" fill="#d6af75"/>')
    for x, y in map(point, initial):
        elements.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="3.5" fill="#b4cda3"/>')
    elements += [
        '<text x="100" y="35">Initial state set</text>',
        '<circle cx="355" cy="31" r="4" fill="#d6af75"/><text x="367" y="35">Terminal states</text>',
        '<line x1="490" y1="31" x2="520" y2="31" stroke="#77b8c5" marker-end="url(#arrow)"/>',
        '<text x="528" y="35">one-step map</text>',
        '<text x="340" y="586" text-anchor="middle">x₁</text>',
        '<text x="22" y="292" transform="rotate(-90 22 292)" text-anchor="middle">x₂</text>',
        '<text x="340" y="575" text-anchor="middle">Equal axis scale; points show all 8 joint initial/error vertices.</text>',
    ]
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 680 610" role="img" '
            'aria-labelledby="title desc"><title id="title">One-step affine observation policy synthesis</title>'
            '<desc id="desc">Initial states in the x1-x2 plane map to terminal states under a policy '
            'that observes noisy x1. All eight initial-state and sensor-error vertices are shown.</desc>'
            '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" '
            'orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="#77b8c5"/></marker></defs>'
            '<rect width="680" height="610" fill="#172019"/><g fill="#d1d9cc" '
            'font-family="monospace" font-size="13">' + "".join(elements) + '</g></svg>')


def render(trials: Path, smoke: Path, build_log: Path, out: Path, source_commit: str,
           collected_utc: str, environment_file: Path, driver: Path) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("source commit must be a full hexadecimal Git object ID")
    head = subprocess.run(["git", "rev-parse", "HEAD"], check=True,
        capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"],
        check=True, capture_output=True, text=True).stdout
    if head != source_commit or status:
        raise ValueError("measurement must be rendered from a clean checkout of the measured source commit")
    raw = trials.read_bytes()
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    scenario = fixture()
    if len(rows) != 8:
        raise ValueError("collection must contain one warmup and seven measured batches")
    for index, row in enumerate(rows):
        if (row.get("schema") != "csl.ext04-affine-synthesis-trial/1" or
                row.get("round") != index or row.get("warmup") is not (index == 0) or
                row.get("batch") != 100 or row.get("status") != "passed" or
                row.get("fixture") != scenario or row.get("workspace_reused") is not True or
                row.get("generators_per_call") != 8 or
                row.get("feasibility_tolerance") != 1e-9 or
                type(row.get("elapsed_ns")) is not int or row["elapsed_ns"] <= 0):
            raise ValueError("raw measurement identity differs")
        check_result(row.get("result", {}))
    measured = [row["elapsed_ns"] for row in rows[1:]]
    if out.exists():
        raise ValueError("report output already exists")
    result = rows[-1]["result"]
    smoke_text = smoke.read_text(encoding="utf-8")
    smoke_json = smoke_text.lstrip()
    smoke_result, smoke_end = json.JSONDecoder().raw_decode(smoke_json)
    if smoke_json[smoke_end:].strip() != "affine-synthesis smoke passed":
        raise ValueError("standalone smoke output differs")
    check_result(smoke_result)
    environment = json.loads(environment_file.read_text(encoding="utf-8"))
    out.mkdir(parents=True)
    (out / "trials.jsonl").write_bytes(raw)
    (out / "smoke.txt").write_text(smoke_text, encoding="utf-8")
    (out / "environment.json").write_bytes(environment_file.read_bytes())
    (out / "fixture.json").write_text(json.dumps(scenario, indent=2, sort_keys=True) + "\n")
    (out / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    image = svg(result).encode()
    (out / "synthesis-2d.svg").write_bytes(image)
    driver_bytes = driver.read_bytes()
    renderer_bytes = Path(__file__).read_bytes()
    (out / "driver.cpp").write_bytes(driver_bytes)
    (out / "renderer.py").write_bytes(renderer_bytes)
    build_text = build_log.read_text(encoding="utf-8", errors="replace")
    build_text = build_text.replace(str(Path.cwd()), "$SOURCE_ROOT").replace(str(Path.home()), "$HOME")
    build_bytes = build_text.encode()
    (out / "release-build-log.txt").write_bytes(build_bytes)
    scenario_hash = sha(json.dumps(scenario, sort_keys=True, separators=(",", ":")).encode())
    med = statistics.median(measured)
    records = {
        "schema": "csl.ext04-affine-synthesis-report/1",
        "report_id": "ext04-affine-synthesis-" + source_commit[:16],
        "source_commit": source_commit,
        "source_tree_clean_before_measurement": True,
        "collected_utc": collected_utc,
        "algorithm": "synthesize_one_stage_affine_policy",
        "solver": "phase-one-binary64",
        "assurance": "numerical binary64",
        "fixture": scenario,
        "fixture_sha256": scenario_hash,
        "timing_scope": rows[0]["timing_scope"],
        "workspace_reuse": "one phase-one LP workspace reused across sequential calls; immutable system and joint V-domain reused",
        "warmup_policy": "one excluded 100-call warmup batch followed by seven measured 100-call batches",
        "warmups_excluded": 1,
        "measured_batches": 7,
        "batch_size": 100,
        "failures": 0,
        "median_batch_ns": med,
        "minimum_batch_ns": min(measured),
        "maximum_batch_ns": max(measured),
        "median_ns_per_call": med / 100,
        "environment": environment,
        "driver_sha256": sha(driver_bytes),
        "smoke_sha256": sha(smoke_text.encode()),
        "renderer_sha256": sha(renderer_bytes),
        "release_build_log_sha256": sha(build_bytes),
        "evidence_limits": [
            "One one-transition, two-state analytic fixture with eight authored joint vertices.",
            "Coverage is universal only over the caller-authored joint V-hull; its completeness is assumed.",
            "Binary64 LP and replay checks provide numerical evidence, not a validated arithmetic certificate.",
            "The objective is feasibility only; the returned affine policy is not cost-optimal or unique.",
            "A numerical infeasible LP status is inconclusive and does not prove that no policy exists.",
            "Single provider and fixture; timings are descriptive and make no comparison, speedup, or scalability claim.",
        ],
        "performance_conclusion": "descriptive single-adapter measurement; no comparative performance claim",
    }
    records_bytes = (json.dumps(records, indent=2, sort_keys=True) + "\n").encode()
    (out / "records.json").write_bytes(records_bytes)
    with (out / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["round", "batch_calls", "elapsed_ns", "ns_per_call", "status"])
        for row in rows[1:]:
            writer.writerow([row["round"], row["batch"], row["elapsed_ns"],
                row["elapsed_ns"] / row["batch"], row["status"]])
    table = "".join(f'<tr><td>{row["round"]}</td><td>{row["elapsed_ns"]/1e6:.3f}</td>'
        f'<td>{row["elapsed_ns"]/row["batch"]:.1f}</td></tr>' for row in rows[1:])
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>EXT-04 affine policy synthesis</title>
<style>body{{font:16px system-ui,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;line-height:1.5;color:#172019}}img{{max-width:100%}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #9aab99;padding:.5rem;text-align:left}}th{{background:#e4eadf}}code{{overflow-wrap:anywhere}}</style></head><body>
<h1>One-step affine observation policy synthesis</h1>
<p>The synthesizer finds an action affine in a sensor sample available before the decision. The two-state plant is <code>x⁺=[[1,1],[0,1]]x+[-1,0]ᵀu</code>; the sensor reports <code>y=x₁+e</code> with <code>|e|≤0.1</code>. The joint initial/error set has eight vertices. The returned policy and replay cover all eight authored vertices under numerical binary64 checks.</p>
<figure><img src="synthesis-2d.svg" alt="Initial state rectangle and all terminal states in the x1-x2 plane, connected by one-step trajectories"><figcaption>Equal-scale state-space plot. Blue arrows connect the four initial-state vertices to terminal states for each sensor-error vertex.</figcaption></figure>
<p>For this fixture, the saved result has gain {result["policy_gain"]:.12g} and offset {result["policy_offset"]:.12g}. The objective is feasibility only; this policy is not cost-optimal. The LP provider reports a feasible primal, and the controller evaluator plus an independent plant calculation check all generator trajectories and safety rows.</p>
<h2>Measurements</h2><p>Seven measured batches of 100 synthesis calls after one excluded warmup. Median {med/1e6:.3f} ms per batch ({med/100:.1f} ns/call); range {min(measured)/1e6:.3f}–{max(measured)/1e6:.3f} ms. Each interval includes LP construction/solve, full-domain replay, and literal checks. Fixture construction, process startup, JSONL serialization, and rendering are excluded.</p>
<table><thead><tr><th>Round</th><th>Batch ms</th><th>ns/call</th></tr></thead><tbody>{table}</tbody></table>
<h2>Limits</h2><ul><li>The guarantee covers only the caller-authored joint V-hull; completeness of that input is assumed.</li><li>Results use numerical binary64 arithmetic, not validated rounding.</li><li>Numerical solver infeasibility remains inconclusive; it is not a proof that no policy exists.</li><li>One fixture and one provider are measured. No speedup, comparison, or scalability claim is made.</li></ul>
<h2>Reproduce</h2><p>Build with <code>CSL_BUILD_EXT04_AFFINE_SYNTHESIS_REPORT=ON</code>, run <code>csl_ext04_affine_synthesis_report smoke</code> and then <code>measure</code>. The bundle includes the exact C++ driver, fixture, raw JSONL, saved result, independent renderer, Release build log, and checksums.</p>
<p>Source commit <a href="https://github.com/butahlecoq/controlled-systems-lab/commit/{html.escape(source_commit)}"><code>{html.escape(source_commit)}</code></a>. <a href="fixture.json">Fixture</a> · <a href="result.json">Result</a> · <a href="trials.jsonl">Raw trials</a> · <a href="smoke.txt">Smoke output</a> · <a href="summary.csv">CSV</a> · <a href="driver.cpp">Driver</a> · <a href="records.json">Records</a> · <a href="renderer.py">Renderer</a>.</p></body></html>'''
    (out / "index.html").write_text(page, encoding="utf-8")
    files = {path.name: sha(path.read_bytes()) for path in sorted(out.iterdir()) if path.is_file()}
    (out / "manifest.json").write_text(json.dumps({"schema": "csl.ext04-affine-synthesis-manifest/1",
        "report_id": records["report_id"], "files": files}, indent=2, sort_keys=True) + "\n")
    with zipfile.ZipFile(out / f'{records["report_id"]}.zip', "w", compression=zipfile.ZIP_STORED) as archive:
        for path in sorted(out.iterdir()):
            if path.name == f'{records["report_id"]}.zip':
                continue
            info = zipfile.ZipInfo(path.name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=Path, required=True)
    parser.add_argument("--smoke", type=Path, required=True)
    parser.add_argument("--build-log", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--collected-utc", required=True)
    parser.add_argument("--environment", type=Path, required=True)
    parser.add_argument("--driver", type=Path, required=True)
    args = parser.parse_args()
    render(args.trials, args.smoke, args.build_log, args.out, args.source_commit,
        args.collected_utc, args.environment, args.driver)


if __name__ == "__main__":
    main()
