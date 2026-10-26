#!/usr/bin/env python3
"""Check and render the saved-data SimpleControlProblem pilot."""

from __future__ import annotations

import html
import hashlib
import itertools
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path


def verify(record: dict) -> None:
    adaptation = record["adaptation"]
    step = adaptation["terminal_time_seconds"] / adaptation["horizon_steps"]
    initial = adaptation["initial_x"]
    actions = adaptation["action_catalogue"]
    expected: dict[tuple[float, ...], list[float]] = {}
    for controls in itertools.product(actions, repeat=adaptation["horizon_steps"]):
        states = [initial]
        for control in controls:
            states.append(states[-1] + step * control)
        expected[controls] = states

    assert len(expected) == record["plan_count"] == 81
    saved: dict[tuple[float, ...], dict] = {}
    for plan in record["plans"]:
        controls = tuple(plan["controls"])
        assert controls in expected and controls not in saved
        states = expected[controls]
        assert len(plan["states"]) == len(states)
        assert all(math.isclose(a, b, abs_tol=1e-14, rel_tol=0.0)
                   for a, b in zip(plan["states"], states))
        assert math.isclose(plan["terminal_squared_error"], states[-1] ** 2,
                            abs_tol=1e-14, rel_tol=0.0)
        saved[controls] = plan
    assert set(saved) == set(expected)
    minimum = min(states[-1] ** 2 for states in expected.values())
    expected_winners = {controls for controls, states in expected.items()
                        if math.isclose(states[-1] ** 2, minimum, abs_tol=1e-14, rel_tol=0.0)}
    actual_winners = {tuple(record["plans"][index]["controls"])
                      for index in record["minimizing_plan_indices"]}
    assert math.isclose(record["objective_value"], minimum, abs_tol=1e-14, rel_tol=0.0)
    assert actual_winners == expected_winners
    assert len(expected_winners) == 10
    timing = record["timing"]
    assert timing["warmup_calls"] == 1 and timing["measured_calls"] == 7
    samples = timing["measured_wall_ns"]
    assert len(samples) == 7 and all(type(sample) is int and sample > 0 for sample in samples)
    ordered = sorted(samples)
    assert timing["median_wall_ns"] == ordered[3]
    assert timing["min_wall_ns"] == ordered[0] and timing["max_wall_ns"] == ordered[-1]


def svg_plot(record: dict) -> str:
    width, height = 1000, 620
    left, top, plot_width, plot_height = 100, 92, 820, 410
    tmax = record["adaptation"]["terminal_time_seconds"]
    ymin, ymax = -0.12, 0.32

    def px(t: float) -> float:
        return left + t / tmax * plot_width

    def py(x: float) -> float:
        return top + (ymax - x) / (ymax - ymin) * plot_height

    winners = set(record["minimizing_plan_indices"])
    pieces = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
              '<title id="title">Simple control pilot: time-state trajectories</title>',
              '<desc id="desc">All 81 four-step trajectories are shown. Ten near-optimal terminal-only plans finish at zero within the declared tolerance.</desc>',
              '<rect width="100%" height="100%" fill="#111820"/>',
              '<text x="100" y="38" fill="#f4f1e8" font-size="25" font-family="sans-serif" font-weight="700">Simple control · finite-action pilot</text>',
              '<text x="100" y="66" fill="#bac6ce" font-size="14" font-family="sans-serif">4 steps · dt = 0.05 s · x₀ = 0.1 · actions {−1, 0, 1} · minimize terminal x²</text>']
    for tick in range(-1, 4):
        xvalue = tick / 10
        y = py(xvalue)
        stroke = "#60717d" if xvalue == 0 else "#293640"
        dash = ' stroke-dasharray="7 6"' if xvalue == 0 else ""
        pieces.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_width}" y2="{y:.2f}" stroke="{stroke}"{dash}/>')
        pieces.append(f'<text x="{left - 15}" y="{y + 5:.2f}" text-anchor="end" fill="#d2dce1" font-size="13" font-family="sans-serif">{xvalue:.1f}</text>')
    for i in range(5):
        t = i * tmax / 4
        x = px(t)
        pieces.append(f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{top + plot_height}" stroke="#293640"/>')
        pieces.append(f'<text x="{x:.2f}" y="{top + plot_height + 24}" text-anchor="middle" fill="#d2dce1" font-size="13" font-family="sans-serif">{t:.2f}</text>')
    pieces.append(f'<rect x="{left}" y="{top}" width="{plot_width}" height="{plot_height}" fill="none" stroke="#81909a"/>')
    for index, plan in enumerate(record["plans"]):
        coords = " ".join(f'{px(i * tmax / 4):.2f},{py(x):.2f}' for i, x in enumerate(plan["states"]))
        if index in winners:
            pieces.append(f'<polyline points="{coords}" fill="none" stroke="#f4a261" stroke-width="2.6" stroke-opacity="0.88"/>')
        else:
            pieces.append(f'<polyline points="{coords}" fill="none" stroke="#56b4e9" stroke-width="1.2" stroke-opacity="0.14"/>')
    pieces.extend([
        f'<text x="{left + plot_width / 2}" y="{top + plot_height + 57}" text-anchor="middle" fill="#f4f1e8" font-size="16" font-family="sans-serif">time (s)</text>',
        f'<text x="27" y="{top + plot_height / 2}" transform="rotate(-90 27 {top + plot_height / 2})" text-anchor="middle" fill="#f4f1e8" font-size="16" font-family="sans-serif">state x</text>',
        f'<line x1="695" y1="{top + plot_height + 52}" x2="725" y2="{top + plot_height + 52}" stroke="#56b4e9" stroke-width="2" stroke-opacity="0.6"/>',
        f'<text x="733" y="{top + plot_height + 57}" fill="#d2dce1" font-size="13" font-family="sans-serif">other 72 plans</text>',
        f'<line x1="825" y1="{top + plot_height + 52}" x2="855" y2="{top + plot_height + 52}" stroke="#f4a261" stroke-width="3"/>',
        f'<text x="863" y="{top + plot_height + 57}" fill="#d2dce1" font-size="13" font-family="sans-serif">10 minimizers</text>',
        '<text x="100" y="590" fill="#93a4ae" font-size="12" font-family="sans-serif">Illustrative finite-action adaptation; running reward omitted. The projection shows time and scalar state.</text>',
        '</svg>'])
    return "\n".join(pieces)


def render(executable: Path, output: Path | None) -> None:
    processor = platform.processor()
    if not processor and Path("/proc/cpuinfo").is_file():
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("model name") and ":" in line:
                processor = line.split(":", 1)[1].strip()
                break
    host = {"os": platform.platform(), "processor": processor,
            "logical_cpus": os.cpu_count(),
            "load_average_before_run": list(os.getloadavg()) if hasattr(os, "getloadavg") else None,
            "capture_started_unix_ns": time.time_ns()}
    record = json.loads(subprocess.check_output([str(executable)], text=True))
    verify(record)
    if output is None:
        return
    record["capture_environment"] = host
    record["renderer_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    output.mkdir(parents=True, exist_ok=True)
    (output / "result.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    (output / "environment.json").write_text(json.dumps(host, indent=2) + "\n", encoding="utf-8")
    svg = svg_plot(record)
    (output / "projection.svg").write_text(svg + "\n", encoding="utf-8")
    converter = shutil.which("rsvg-convert")
    if converter:
        subprocess.run([converter, "--output", str(output / "projection.png"),
                        str(output / "projection.svg")], check=True)
    png_link = ' · <a href="projection.png">PNG</a>' if converter else ""
    page = f'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Simple control pilot</title>
<style>body{{margin:0;background:#111820;color:#f4f1e8;font:16px/1.55 system-ui,sans-serif}}main{{max-width:1100px;margin:auto;padding:2rem}}a{{color:#8bd3f7}}.plot{{width:100%;height:auto}}.note{{border-left:4px solid #f4a261;padding:.7rem 1rem;background:#1a252e}}</style>
<main><h1>Simple control: finite-action pilot</h1>
<p>This first source-attributed slice adapts the discrete SimpleControlProblem to a four-step terminal minimax problem. The solver exhausts all 81 action sequences; an independent Python enumeration checks every saved trajectory and the ten near-optimal plans under absolute tolerance 1e-14. One warmup and seven measured solver calls are recorded; setup and JSON output are excluded.</p>
<div class="plot">{svg}</div>
<p class="note"><strong>Scope:</strong> the source defaults to initial state [0, 1] and terminal time 2 s. This pilot uses x₀ = 0.1 and 0.2 s to keep exhaustive enumeration small. It minimizes terminal x² and omits the source running reward. The source also has different running-reward coefficients in cost() and step(); the source step() execution rule is the reference for the environment. This is not a reproduction of the original reward objective.</p>
<p>Source repository commit: <code>{html.escape(record['source_repository_commit'])}</code>. CSL source commit: <code>{html.escape(record['source_commit'])}</code>. Assurance: numerical, exhaustive over the declared finite action catalogue.</p>
<p>Timing: median {record['timing']['median_wall_ns']} ns (range {record['timing']['min_wall_ns']}–{record['timing']['max_wall_ns']} ns; seven calls after one warmup). Compiler: {html.escape(record['environment']['compiler_id'])} {html.escape(record['environment']['compiler_version'])}; build: {html.escape(record['environment']['build_type'])}; host: {html.escape(record['capture_environment']['os'])}; CPU: {html.escape(record['capture_environment']['processor'])}; logical CPUs: {record['capture_environment']['logical_cpus']}; load average before capture: {html.escape(str(record['capture_environment']['load_average_before_run']))}.</p>
<p><a href="result.json">Saved result JSON</a> · <a href="projection.svg">Standalone SVG</a>{png_link}</p></main></html>
'''
    (output / "index.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) not in (2, 4):
        raise SystemExit("usage: check_smoke.py EXECUTABLE [--output DIRECTORY]")
    if len(sys.argv) == 2:
        render(Path(sys.argv[1]).resolve(), None)
    else:
        if sys.argv[2] != "--output":
            raise SystemExit("expected --output")
        render(Path(sys.argv[1]).resolve(), Path(sys.argv[3]))
