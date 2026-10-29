#!/usr/bin/env python3
"""Validate and render EXP-06 from saved paired comparison artifacts only."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_source_indices import check as check_source_indices

ROOT = Path(__file__).resolve().parents[3]
PORT_ROOT = ROOT / "tools/legacy-ports/A29"
METHODS = ("csl.geometry.a29-a30-python", "csl.geometry.quickhull-2d")
ARTIFACTS = ("index.html", "hulls.svg", "trials.csv")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strict_json(path: Path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key in {path}")
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)


def digest_bytes(hex_text: str) -> bytes:
    return bytes.fromhex(hex_text)


def read_saved(bundle: Path):
    capture = strict_json(bundle / "capture.json")
    wire = strict_json(bundle / "comparison-record.json")
    if wire.get("schema") != "csl.comparison-record/1" or wire.get("track") != "new-comparison":
        raise ValueError("saved comparison is not a registered paired comparison record")
    spec = strict_json_bytes(wire["spec"].encode())
    if canonical(spec) != wire["spec"]:
        raise ValueError("comparison spec is not canonical")
    if spec.get("schema") != "csl.comparison-spec/2" or spec.get("input_manifest_source") != "csl.geometry-hull-input/1":
        raise ValueError("comparison spec is not the bounded geometry pilot")
    spec_id = sha256(wire["spec"].encode())
    if wire.get("comparison_spec_id") != spec_id:
        raise ValueError("comparison spec identity differs")
    if spec.get("request_digest") != capture.get("request_digest"):
        raise ValueError("comparison request digest differs from capture metadata")
    methods = {}
    rows = []
    manifest = None
    expected_order = [{"method_id": METHODS[0], "repetition": 0},
                      {"method_id": METHODS[1], "repetition": 0}]
    for repetition in range(1, capture["measured_repetitions_per_method"] + 1):
        method_order = METHODS if repetition % 2 == 1 else METHODS[::-1]
        expected_order.extend({"method_id": method_id, "repetition": repetition}
                              for method_id in method_order)
    if capture.get("execution_order") != expected_order:
        raise ValueError("captured execution order is not the declared alternating schedule")
    for item in wire["attempts"]:
        run_text = item["run"]
        run = json.loads(run_text)
        if run.get("schema") != "csl.external-method-run/1":
            raise ValueError("comparison contains an unsupported method-run schema")
        if canonical(run) != run_text or sha256(run_text.encode()) != item["run_digest"]:
            raise ValueError("method-run bytes or content digest differ")
        arm = item["arm_index"]
        repetition = item["repetition_index"]
        if (arm >= len(METHODS) or item["run_id"] != run["run"] or
                run["request_digest"] != spec["request_digest"] or
                run["problem"] != spec["problem_id"] or
                run["configuration"]["id"] != spec["arms"][arm]["configuration_id"] or
                run["method"]["id"] != spec["arms"][arm]["strategy"] or
                run["method"]["id"] != METHODS[arm] or
                item["reported_status"] != run["status"]):
            raise ValueError("paired attempt identity differs from spec or run")
        attached = run["input_manifest"]
        content = digest_bytes(attached["content_hex"])
        manifest_value = strict_json_bytes(content)
        if (sha256(content) != attached["sha256"] or canonical(manifest_value).encode() != content or
                run["problem"] != "csl.problem.v1.sha256:" + attached["sha256"]):
            raise ValueError("saved input manifest digest differs")
        if (attached["schema"] != spec["input_manifest_source"] or
                attached["sha256"] != spec["input_manifest_hash"]):
            raise ValueError("run manifest identity differs from comparison spec")
        if manifest is None:
            manifest = manifest_value
        elif manifest != manifest_value:
            raise ValueError("paired methods do not share bit-identical manifest bytes")
        method_id = run["method"]["id"]
        if method_id not in METHODS:
            raise ValueError("unexpected comparison method")
        result = run["result"]
        payload = result
        indices = payload.get("indices", [])
        points = manifest["points"]
        source_index_check = check_source_indices(indices, len(points))
        output_points = ([points[index] for index in indices
                          if type(index) is int and 0 <= index < len(points)]
                         if isinstance(indices, list) else [])
        sys.path.insert(0, str(PORT_ROOT))
        from oracle import check as exact_check
        checker_evidence = payload.get("checker", {})
        budget = checker_evidence.get("budget", {})
        max_points = budget.get("max_points")
        if (checker_evidence.get("schema") != "csl.exp06-exact-hull-check/1" or
                not isinstance(max_points, int) or max_points < len(points) or max_points > 64):
            raise ValueError("saved checker budget or schema is invalid")
        quality = exact_check(points, output_points, max_points=max_points)
        saved_quality = {key: value for key, value in checker_evidence.items()
                         if key not in ("schema", "budget", "source_index_check")}
        if quality != saved_quality:
            raise ValueError("saved checker result differs from exact source-hull recheck")
        if checker_evidence.get("source_index_check") != source_index_check:
            raise ValueError("saved source-index check differs from method output")
        status = item["reported_status"]
        if status != run["status"]:
            raise ValueError("attempt status differs from method-run status")
        event_text = item["measurement_payload"]
        event = json.loads(event_text)
        if canonical(event) != event_text:
            raise ValueError("measurement event is not canonical")
        if (event["method_id"] != method_id or event["status"] != status_word(status) or
                payload.get("method_id") != method_id):
            raise ValueError("saved event identity or status differs")
        if (event["schema"] != "csl.external-method-event/1" or
                event["repetition"] != repetition or event["warmup"] != (repetition == 0) or
                event["duration_ns"] != payload.get("duration_ns")):
            raise ValueError("saved warmup/repetition identity differs")
        algorithm = payload.get("algorithm", {})
        expected_status = ("completed" if algorithm.get("algorithm_status") == "completed" and
                           quality["status"] == "verified" and
                           source_index_check["status"] == "verified" else
                           "timed_out" if algorithm.get("algorithm_status") == "timed_out" else
                           "incomplete" if algorithm.get("algorithm_status") == "inconclusive" or
                           quality["status"] == "inconclusive" else "failed")
        if status != expected_status:
            raise ValueError("attempt terminal status hides its algorithm or checker outcome")
        row = {"method": method_id, "repetition": repetition, "warmup": event["warmup"],
            "status": status, "duration_ns": payload.get("duration_ns"),
            "indices": (":".join(str(index) for index in indices) if isinstance(indices, list)
                        else canonical(indices)),
            "checker": quality["status"], "run_id": run["run"],
            "run_sha256": item["run_digest"]}
        rows.append(row)
        methods.setdefault(method_id, []).append(row)
    if manifest is None or len(manifest["points"]) != 9:
        raise ValueError("expected the shared nine-point square fixture")
    if capture["fixture_sha256"] != sha256(canonical(manifest).encode()):
        raise ValueError("capture metadata and shared fixture digest differ")
    controls = capture.get("checker_controls", {})
    if (controls.get("schema") != "csl.exp06-checker-controls/1" or
            controls.get("omitted_corner", {}).get("status") != "incorrect" or
            controls.get("all_redundant_points_retained", {}).get("status") != "verified" or
            controls.get("omitted_corner", {}).get("budget") != {"max_points": 64} or
            controls.get("all_redundant_points_retained", {}).get("budget") != {"max_points": 64}):
        raise ValueError("independent checker negative controls are missing or failed")
    expected_runs = 2 * (capture["warmups_per_method"] + capture["measured_repetitions_per_method"])
    if (len(rows) != expected_runs or set(methods) != set(METHODS) or
            spec.get("repetitions") != capture["warmups_per_method"] + capture["measured_repetitions_per_method"] or
            len(wire["attempts"]) != expected_runs):
        raise ValueError("comparison record does not retain every declared attempt")
    for method_id in METHODS:
        values = sorted(methods[method_id], key=lambda row: row["repetition"])
        if [row["repetition"] for row in values] != list(range(len(values))):
            raise ValueError("method repetitions are missing or duplicated")
    comparison_material = {"attempts": wire["attempts"], "comparison_spec_id": spec_id,
                           "schema": "csl.comparison-record/1"}
    if wire.get("comparison_run_id") != sha256(canonical(comparison_material).encode()):
        raise ValueError("comparison run identity differs")
    return capture, wire, spec, manifest, methods, rows


def strict_json_bytes(data: bytes):
    return json.loads(data)


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def status_word(status: str) -> str:
    return {"completed": "passed", "failed": "failed", "incomplete": "incomplete",
        "unsupported": "unsupported", "refused": "refused", "timed_out": "timed_out",
        "cancelled": "cancelled", "resource_limited": "resource_limited"}[status]


def hull_order(points, indices):
    if len(indices) < 3:
        return indices
    cx = sum(points[index][0] for index in indices) / len(indices)
    cy = sum(points[index][1] for index in indices) / len(indices)
    return sorted(indices, key=lambda index: math.atan2(points[index][1] - cy, points[index][0] - cx))


def render_svg(manifest, methods):
    width, height = 940, 560
    left, right, top, bottom = 90, 900, 70, 470
    low, high = -0.25, 2.25
    x = lambda value: left + (value - low) / (high - low) * (right - left)
    y = lambda value: bottom - (value - low) / (high - low) * (bottom - top)
    points = manifest["points"]
    palette = {METHODS[0]: "#eb6f92", METHODS[1]: "#3e8fb0"}
    items = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">EXP-06 shared square hull comparison</title>',
        '<desc id="desc">The same nine source points and the hull vertices returned by A29 and QuickHull, plotted in two dimensions.</desc>',
        '<rect width="100%" height="100%" fill="#191724"/>',
        f'<path d="M {left} {bottom} H {right} M {left} {bottom} V {top}" stroke="#908caa" stroke-width="2"/>',
        f'<text x="{(left + right) / 2}" y="530" text-anchor="middle" fill="#e0def4" font-family="sans-serif">x</text>',
        f'<text x="28" y="{(top + bottom) / 2}" text-anchor="middle" transform="rotate(-90 28 {(top + bottom) / 2})" fill="#e0def4" font-family="sans-serif">y</text>']
    for index in range(3):
        value = index
        items.append(f'<path d="M {x(value)} {top} V {bottom}" stroke="#393552"/>')
        items.append(f'<path d="M {left} {y(value)} H {right}" stroke="#393552"/>')
        items.append(f'<text x="{x(value)}" y="{bottom + 20}" text-anchor="middle" fill="#908caa" font-family="sans-serif">{value}</text>')
        items.append(f'<text x="{left - 14}" y="{y(value) + 4}" text-anchor="end" fill="#908caa" font-family="sans-serif">{value}</text>')
    for method_id in METHODS:
        successful = next((row for row in methods[method_id] if row["repetition"] == 1), None)
        if successful and successful["checker"] == "verified":
            indices = [int(value) for value in successful["indices"].split(":") if value]
            order = hull_order(points, indices)
            if len(order) >= 2:
                coords = " ".join(f"{x(points[index][0]):.2f},{y(points[index][1]):.2f}" for index in order)
                items.append(f'<polygon points="{coords}" fill="none" stroke="{palette[method_id]}" stroke-width="3" stroke-dasharray="{ "8 5" if method_id == METHODS[0] else "none" }"/>')
    hull_indices = {0, 1, 2, 3}
    for index, point in enumerate(points):
        kind = "hull vertex" if index in hull_indices else "redundant edge or interior point"
        fill = "#f6c177" if index in hull_indices else "#c4a7e7"
        items.append(f'<circle cx="{x(point[0]):.2f}" cy="{y(point[1]):.2f}" r="7" fill="{fill}" stroke="#191724" stroke-width="2"><title>point {index}: {kind}</title></circle>')
        items.append(f'<text x="{x(point[0]) + 9:.2f}" y="{y(point[1]) - 8:.2f}" fill="#e0def4" font-size="13" font-family="sans-serif">{index}</text>')
    items.extend(['<g font-family="sans-serif" font-size="14" fill="#e0def4">',
        '<line x1="525" y1="32" x2="565" y2="32" stroke="#eb6f92" stroke-width="3" stroke-dasharray="8 5"/><text x="573" y="37">A29/A30 port hull</text>',
        '<line x1="525" y1="52" x2="565" y2="52" stroke="#3e8fb0" stroke-width="3"/><text x="573" y="57">QuickHull hull</text>',
        '<circle cx="535" cy="500" r="6" fill="#f6c177"/><text x="548" y="505">source extreme</text>',
        '<circle cx="690" cy="500" r="6" fill="#c4a7e7"/><text x="703" y="505">redundant source point</text>',
        '</g></svg>'])
    return "\n".join(items) + "\n"


def render_html(capture, wire, manifest, methods, rows, report_id):
    method_rows = []
    for method_id in METHODS:
        measured = [row for row in methods[method_id] if not row["warmup"] and isinstance(row["duration_ns"], int)]
        timings = ", ".join(f"r{row['repetition']}: {row['duration_ns']} ns" for row in measured)
        values = [row["duration_ns"] for row in measured]
        summary = f"median {statistics.median(values)} ns; range {min(values)}–{max(values)} ns" if values else "no measured duration"
        method_rows.append(f"<tr><th>{html.escape(method_id)}</th><td>{len(measured)}</td><td>{html.escape(summary)}</td><td>{html.escape(timings)}</td><td>{sum(row['checker'] == 'verified' for row in methods[method_id])}/{len(methods[method_id])} attempts verified</td></tr>")
    body_rows = []
    for row in rows:
        body_rows.append("<tr>" + "".join(f"<td>{html.escape(str(row[key]))}</td>" for key in
            ("method", "repetition", "warmup", "status", "duration_ns", "indices", "checker")) + "</tr>")
    points_text = html.escape(json.dumps(manifest["points"], separators=(",", ":")))
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EXP-06 bounded hull pilot</title><style>
body{{margin:0;background:#191724;color:#e0def4;font:16px/1.55 system-ui,sans-serif}}main,header,footer{{max-width:1050px;margin:auto;padding:1rem}}section{{background:#232136;border:1px solid #524f67;border-radius:12px;padding:1rem;margin:1rem 0}}a{{color:#9ccfd8}}table{{border-collapse:collapse;width:100%;display:block;overflow:auto}}td,th{{border:1px solid #524f67;padding:.45rem;text-align:left;vertical-align:top}}code,pre{{overflow-wrap:anywhere}}img{{width:100%;height:auto}}
</style></head><body><header><p>Controlled Systems Lab · EXP-06</p><h1>Bounded 2D geometry pilot</h1>
<p>One shared nine-point square fixture, checked with an independent exact binary64 source-hull oracle.</p></header><main>
<section><h2>Geometry</h2><p>The square corners are the hull. The center and four edge midpoints are redundant. Both methods receive the same canonical input bytes.</p><img src="hulls.svg" alt="Square hull with four extreme corners, a center, four edge midpoints, and both method hull outlines"><p>Input points in source order: <code>{points_text}</code></p></section>
<section><h2>Recorded attempts</h2><p>{capture['warmups_per_method']} excluded warmup and {capture['measured_repetitions_per_method']} measured repetitions per method. Execution order alternated between methods. Every attempt, including failure statuses, remains in the paired comparison record. Timings are method-local observations. Python/NumPy and C++ runtime measurements have different intervals and are inconclusive for speed comparison.</p>
<p>A29 timing wraps the Python port call and excludes the checker. QuickHull timing wraps the library call and excludes process startup, JSON intake, and the checker. No common limiter profile was collected. Host: {html.escape(capture['host']['cpu_model'])}, {capture['host']['logical_cpus']} logical CPUs, load averages {html.escape(str(capture['host']['load_average_1m_5m_15m']))}. Memory limits were not enforced.</p>
<table><thead><tr><th>Method</th><th>Measured repetitions</th><th>Method-local summary</th><th>Per-repetition duration</th><th>Exact checker</th></tr></thead><tbody>{''.join(method_rows)}</tbody></table>
<h3>Attempt details</h3><table><thead><tr><th>Method</th><th>Repetition</th><th>Warmup</th><th>Status</th><th>Duration ns</th><th>Source indices</th><th>Exact checker</th></tr></thead><tbody>{''.join(body_rows)}</tbody></table></section>
<section><h2>Scope and provenance</h2><p>Single bounded 2D synthetic fixture; this is an initial algorithm-functionality example, not a general correctness or performance claim. Source commit: <code>{html.escape(capture['source_commit'])}</code>. Report: <code>{report_id}</code>.</p>
<p><a href="https://github.com/butahlecoq/controlled-systems-lab/commit/{html.escape(capture['source_commit'])}">Exact source commit</a> · <a href="comparison-record.json">Paired comparison record</a> · <a href="fixture/square.json">Input fixture</a> · <a href="capture.json">Capture metadata</a> · <a href="trials.csv">Attempt table</a> · <a href="manifest.json">File hashes</a></p>
<h3>Reproduce</h3><pre>python3 -m pip install -r tools/legacy-ports/A29/requirements.txt
cmake -S . -B build/exp06 -DBUILD_TESTING=OFF -DCMAKE_BUILD_TYPE=Release -DCSL_ENABLE_HIGHS=OFF -DCSL_ENABLE_QHULL=OFF -DCSL_BUILD_EXP06_PILOT=ON
cmake --build build/exp06 --target csl_exp06_quickhull csl_exp06_pack_comparison --parallel 2
python3 scripts/reports/exp06/collect.py --quickhull build/exp06/csl_exp06_quickhull --packer build/exp06/csl_exp06_pack_comparison --out reports/algorithm-results/exp06-rerun
python3 scripts/reports/exp06/render_saved.py --bundle reports/algorithm-results/exp06-rerun</pre></section>
</main><footer>EXP-06 · geometry algorithm pilot · <a href="https://github.com/butahlecoq/controlled-systems-lab/issues/423">Issue #423</a></footer></body></html>'''


def render(bundle: Path):
    capture, wire, _spec, manifest, methods, rows = read_saved(bundle)
    wire_bytes = (bundle / "comparison-record.json").read_bytes()
    report_id = "exp06-" + sha256(wire_bytes)[:16]
    svg = render_svg(manifest, methods)
    html_doc = render_html(capture, wire, manifest, methods, rows, report_id)
    csv_buffer = io.StringIO(newline="")
    fields = ("method", "repetition", "warmup", "status", "duration_ns", "indices", "checker", "run_id", "run_sha256")
    writer = csv.DictWriter(csv_buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return {"index.html": html_doc.encode(), "hulls.svg": svg.encode(),
            "trials.csv": csv_buffer.getvalue().encode()}, report_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    bundle = args.bundle.resolve(strict=True)
    rendered, report_id = render(bundle)
    if args.check:
        for name, data in rendered.items():
            if (bundle / name).read_bytes() != data:
                raise SystemExit(f"saved renderer mismatch: {name}")
        manifest = strict_json(bundle / "manifest.json")
        expected = {name: sha256(data) for name, data in rendered.items()}
        expected.update({"comparison-record.json": sha256((bundle / "comparison-record.json").read_bytes()),
            "capture.json": sha256((bundle / "capture.json").read_bytes()),
            "pack-request.json": sha256((bundle / "pack-request.json").read_bytes()),
            "packer.stdout": sha256((bundle / "packer.stdout").read_bytes()),
            "packer.stderr": sha256((bundle / "packer.stderr").read_bytes())})
        for path in sorted((bundle / "raw-attempts").glob("*")):
            expected["raw-attempts/" + path.name] = sha256(path.read_bytes())
        for path in sorted((bundle / "fixture").glob("*")):
            expected["fixture/" + path.name] = sha256(path.read_bytes())
        if manifest.get("report_id") != report_id or manifest.get("files") != expected:
            raise SystemExit("manifest does not match saved bundle")
        print(f"{report_id}: saved record, checker results, render and hashes verified")
        return
    for name, data in rendered.items():
        (bundle / name).write_bytes(data)
    files = {name: sha256((bundle / name).read_bytes()) for name in
        ("comparison-record.json", "capture.json", "pack-request.json", "packer.stdout", "packer.stderr", *ARTIFACTS)}
    for directory in ("raw-attempts", "fixture"):
        for path in sorted((bundle / directory).glob("*")):
            files[directory + "/" + path.name] = sha256(path.read_bytes())
    (bundle / "manifest.json").write_text(json.dumps({"schema": "csl.exp06-report-manifest/1",
        "report_id": report_id, "files": files}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(report_id)


if __name__ == "__main__":
    main()
