"""Generate a deterministic, explicitly sampled Lotka–Volterra illustration."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import re

ROOT = Path(__file__).resolve().parents[2]
REPORT_ID = "lotka-volterra-sampled-20261023"
REPORT_DIR = ROOT / "reports/algorithm-results" / REPORT_ID
SAMPLES, SEED, HORIZON = 512, 20261023, 60
CONTROL = (-0.3, 0.3)
PARAMETERS = {"a": 0.9, "b": 0.003, "c": 0.8, "d": 0.002, "e": 0.85}
STAGES = (15, 30, 45, 60)
COLORS = ("#fb7185", "#fbbf24", "#38bdf8", "#a78bfa")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def convex_hull(points):
    points = sorted(set(map(tuple, points)))
    if len(points) < 3:
        return points

    def cross(o, a, b):
        return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])

    halves = []
    for sequence in (points, reversed(points)):
        half = []
        for point in sequence:
            while len(half) >= 2 and cross(half[-2], half[-1], point) <= 0:
                half.pop()
            half.append(point)
        halves.append(half[:-1])
    return halves[0] + halves[1]


def simulate(source_commit: str) -> dict:
    if re.fullmatch(r"[0-9a-f]{40}", source_commit) is None:
        raise ValueError("source commit must be a full lowercase Git SHA")
    a, b, c, d, e = (PARAMETERS[key] for key in ("a", "b", "c", "d", "e"))
    step = 2 * math.pi / (HORIZON * math.sqrt(a*c))
    random_source = random.Random(SEED)
    controls, states = [], []
    for _ in range(SAMPLES):
        x, y = 410.0, 300.0
        history, trace = [], [[x, y]]
        for _ in range(HORIZON):
            u = round(random_source.uniform(*CONTROL), 12)
            history.append(u)
            x, y = x + step*(a*x-b*x*y+e*u), y + step*(-c*y+d*x*y)
            trace.append([round(x, 12), round(y, 12)])
        controls.append(history)
        states.append(trace)
    return {
        "schema": "csl.lotka-volterra-sampled-illustration/1",
        "report_id": REPORT_ID,
        "source_commit": source_commit,
        "claim_scope": "512 deterministic sampled control histories; not the full reachable set, not an inner/outer certificate, and not a historical reproduction.",
        "model": {
            "recurrence": [
                "x1[k+1] = x1[k] + h*(a*x1[k] - b*x1[k]*x2[k] + e*u[k])",
                "x2[k+1] = x2[k] + h*(-c*x2[k] + d*x1[k]*x2[k])",
            ],
            "parameters": PARAMETERS,
            "step": {"formula": "h = 2*pi/(60*sqrt(a*c))", "value": step},
            "initial_state": [410.0, 300.0],
            "state_units": "not specified in the source; plotted coordinates retain the printed state units",
            "horizon": HORIZON,
            "control_interval": list(CONTROL),
            "control_sampling": {"method": "Python random.Random uniform draws, sample-major then stage-major",
                                 "seed": SEED, "samples": SAMPLES, "values_per_history": HORIZON},
        },
        "sampled_controls": controls,
        "sampled_states": states,
        "displayed_stages": list(STAGES),
    }


def project(point, bounds, rect):
    x0, y0, width, height = rect
    lo_x, hi_x, lo_y, hi_y = bounds
    return (x0+(point[0]-lo_x)*width/(hi_x-lo_x),
            y0+height-(point[1]-lo_y)*height/(hi_y-lo_y))


def draw(record: dict) -> str:
    traces = record["sampled_states"]
    points = [point for trace in traces for point in trace]
    lo_x, hi_x = min(p[0] for p in points), max(p[0] for p in points)
    lo_y, hi_y = min(p[1] for p in points), max(p[1] for p in points)
    pad_x, pad_y = (hi_x-lo_x)*.06, (hi_y-lo_y)*.06
    bounds = lo_x-pad_x, hi_x+pad_x, lo_y-pad_y, hi_y+pad_y
    rect = (80, 110, 630, 560)
    x0, y0, width, height = rect
    out = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1180" height="770" viewBox="0 0 1180 770" role="img" aria-labelledby="title desc">',
        '<title id="title">Lotka–Volterra sampled state cloud around the equilibrium</title>',
        '<desc id="desc">Seeded control-history samples form an orbit around the unforced equilibrium. Dots and convex sample hulls are illustrative, not certified reachable sets.</desc>',
        '<rect width="1180" height="770" fill="#0b1020"/>',
        '<text x="50" y="43" fill="#f8fafc" font-size="25" font-family="sans-serif" font-weight="700">A controlled orbit, seen through sampled histories</text>',
        '<text x="50" y="69" fill="#a5b4fc" font-size="14" font-family="sans-serif">60-step discrete recurrence · 512 seeded control sequences · sample geometry only</text>',
    ]
    for fraction in (0, .25, .5, .75, 1):
        x, y = x0+fraction*width, y0+fraction*height
        out += [f'<line x1="{x:.1f}" y1="{y0}" x2="{x:.1f}" y2="{y0+height}" stroke="#26324b"/>',
                f'<line x1="{x0}" y1="{y:.1f}" x2="{x0+width}" y2="{y:.1f}" stroke="#26324b"/>']
    out.append(f'<rect x="{x0}" y="{y0}" width="{width}" height="{height}" fill="none" stroke="#64748b"/>')
    equilibrium = project((400, 300), bounds, rect)
    initial = project((410, 300), bounds, rect)
    out += [f'<circle cx="{equilibrium[0]:.2f}" cy="{equilibrium[1]:.2f}" r="5" fill="#f8fafc"/>',
            f'<text x="{equilibrium[0]+8:.2f}" y="{equilibrium[1]-8:.2f}" fill="#e2e8f0" font-size="12" font-family="sans-serif">equilibrium (400, 300)</text>',
            f'<circle cx="{initial[0]:.2f}" cy="{initial[1]:.2f}" r="4" fill="#fbbf24" stroke="#0b1020"/>',
            f'<text x="{initial[0]+8:.2f}" y="{initial[1]-8:.2f}" fill="#fbbf24" font-size="12" font-family="sans-serif">initial state (410, 300)</text>']
    for band, color in enumerate(COLORS):
        first, last = band*15+1, (band+1)*15
        band_points = [p for trace in traces for stage, p in enumerate(trace[1:], 1) if first <= stage <= last]
        for point in band_points:
            x, y = project(point, bounds, rect)
            out.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="1.45" fill="{color}" fill-opacity="0.22"/>')
        lx = 90+band*155
        out += [f'<circle cx="{lx}" cy="710" r="5" fill="{color}"/>',
                f'<text x="{lx+11}" y="715" fill="#e2e8f0" font-size="13" font-family="sans-serif">steps {first}–{last}</text>']
    out += [f'<text x="{x0+width/2:.1f}" y="{y0+height+32}" text-anchor="middle" fill="#e2e8f0" font-size="14" font-family="sans-serif">prey state x₁ (source units unspecified)</text>',
            f'<text x="27" y="{y0+height/2:.1f}" transform="rotate(-90 27 {y0+height/2:.1f})" text-anchor="middle" fill="#e2e8f0" font-size="14" font-family="sans-serif">predator state x₂ (source units unspecified)</text>',
            '<text x="80" y="750" fill="#fda4af" font-size="13" font-family="sans-serif">Each dot is one evaluated state from a sampled history; missing histories are possible.</text>']
    panels = ((790, 135, 160, 150), (990, 135, 160, 150), (790, 375, 160, 150), (990, 375, 160, 150))
    for stage, panel, color in zip(STAGES, panels, COLORS):
        cloud = [trace[stage] for trace in traces]
        min_x, max_x = min(p[0] for p in cloud), max(p[0] for p in cloud)
        min_y, max_y = min(p[1] for p in cloud), max(p[1] for p in cloud)
        mx, my = max((max_x-min_x)*.12, .005), max((max_y-min_y)*.12, .005)
        zoom = min_x-mx, max_x+mx, min_y-my, max_y+my
        px, py, pw, ph = panel
        out += [f'<text x="{px}" y="{py-15}" fill="{color}" font-size="15" font-family="sans-serif" font-weight="700">Stage k={stage}</text>',
                f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" fill="#111a2e" stroke="#64748b"/>']
        for point in cloud:
            x, y = project(point, zoom, panel)
            out.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.1" fill="{color}" fill-opacity="0.55"/>')
        boundary = convex_hull(cloud)
        if len(boundary) >= 3:
            coords = [project(p, zoom, panel) for p in boundary]
            joined = " ".join(f"{x:.2f},{y:.2f}" for x, y in coords)
            out.append(f'<polygon points="{joined}" fill="{color}" fill-opacity="0.10" stroke="{color}" stroke-width="1.5" stroke-dasharray="5 4"/>')
        out.append(f'<text x="{px}" y="{py+ph+19}" fill="#cbd5e1" font-size="11" font-family="sans-serif">sample hull; local zoom</text>')
    out += ['<text x="790" y="605" fill="#e2e8f0" font-size="13" font-family="sans-serif">Dashed outlines are hulls of displayed samples only.</text>',
            '<text x="790" y="628" fill="#e2e8f0" font-size="13" font-family="sans-serif">They are not inner or outer reachability certificates.</text>',
            '<text x="790" y="658" fill="#94a3b8" font-size="12" font-family="sans-serif">Orbit view has shared axes; stage panels use local zooms.</text>', '</svg>']
    return "\n".join(out)+"\n"


def render_page(record: dict, generator_sha: str) -> str:
    commit = record["source_commit"]
    base = "https://github.com/butahlecoq/controlled-systems-lab/blob/"+commit+"/"
    step = record["model"]["step"]["value"]
    command = f"python scripts/reports/lotka_volterra_sampled.py --source-commit {commit} --out reports/algorithm-results/{REPORT_ID}"
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Lotka–Volterra reachability samples</title><style>body{{margin:0;background:#0b1020;color:#e2e8f0;font:16px/1.6 system-ui,sans-serif}}main{{max-width:1100px;margin:auto;padding:2rem}}h1{{line-height:1.1}}.scope{{border-left:4px solid #fb7185;padding:.7rem 1rem;background:#171d30}}img{{width:100%;height:auto;border-radius:12px}}a{{color:#7dd3fc}}code,pre{{color:#fde68a}}li{{margin:.4rem 0}}small{{color:#94a3b8}}</style></head><body><main><p><a href="../examples/index.html">← Visual examples</a></p><p>A deterministic geometry illustration</p><h1>Lotka–Volterra reachability samples</h1><p>This example follows a discrete controlled prey–predator recurrence for 60 stages and plots 512 seeded control histories. Their state samples trace an orbit around the unforced equilibrium; four zoomed panels show sample clouds at selected stages.</p><p class="scope"><strong>Evidence scope.</strong> These are samples, not the full reachable sets. A sampled cloud may miss feasible states, and each dashed outline is only the convex hull of the displayed samples. Neither hull is an inner or outer certificate. This authored calculation does not reproduce L05 Figure 1 or Table 1, and does not run a repository synthesis algorithm, optimizer, or benchmark.</p><img src="geometry.svg" alt="Sampled Lotka–Volterra state cloud and four stage-wise sample hulls"><h2>Recurrence and inputs</h2><pre>x1[k+1] = x1[k] + h*(a*x1[k] - b*x1[k]*x2[k] + e*u[k])
x2[k+1] = x2[k] + h*(-c*x2[k] + d*x1[k]*x2[k])</pre><ul><li>Parameters: a=0.9, b=0.003, c=0.8, d=0.002, e=0.85.</li><li>Step: h=2π/(60√(ac))={step:.15g}; this convention is explicit for this illustration.</li><li>Initial state: (410, 300); control at each stage: u∈[-0.3, 0.3].</li><li>Sampling: {SAMPLES} histories from Python random.Random, seed {SEED}; one uniform draw per stage and history.</li><li>Units are not specified in the source; axes preserve its state coordinates without assigning physical units.</li></ul><p><a href="{base}docs/research/l05-example1-source-dossier.md">L05 Example 1 source dossier</a> records the printed recurrence and the unresolved boundary between published inputs and the historical figure.</p><p><a href="records.json">Raw controls and state samples</a> · <a href="geometry.svg">Standalone SVG</a> · <a href="{base}scripts/reports/lotka_volterra_sampled.py">Generator source at {commit[:12]}</a></p><p>Regenerate with <code>{command}</code>.</p><small>Generator SHA-256: {generator_sha}</small></main></body></html>'''


def generated_files(source_commit: str) -> dict[str, bytes]:
    record = simulate(source_commit)
    raw = (json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))+"\n").encode()
    figure = draw(record).encode()
    generator_sha = sha(Path(__file__).read_bytes())
    index = render_page(record, generator_sha).encode()
    manifest = {"schema": "csl.lotka-volterra-sampled-publication/1", "report_id": REPORT_ID,
                "source_commit": source_commit, "generator_sha256": generator_sha,
                "files_sha256": {"geometry.svg": sha(figure), "index.html": sha(index), "records.json": sha(raw)}}
    meta = (json.dumps(manifest, sort_keys=True, indent=2)+"\n").encode()
    return {"geometry.svg": figure, "index.html": index, "manifest.json": meta, "records.json": raw}


def build(out: Path, source_commit: str | None, check: bool) -> None:
    if check:
        source_commit = json.loads((out/"records.json").read_text(encoding="utf-8"))["source_commit"]
    if source_commit is None:
        raise ValueError("--source-commit is required when generating a report")
    content = generated_files(source_commit)
    if check:
        if not out.is_dir() or {item.name for item in out.iterdir()} != set(content):
            raise ValueError("saved report inventory differs")
        for name, expected in content.items():
            if (out/name).read_bytes() != expected:
                raise ValueError("saved report differs: "+name)
        return
    out.mkdir(parents=True, exist_ok=True)
    for name, data in content.items():
        (out/name).write_bytes(data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=REPORT_DIR)
    parser.add_argument("--source-commit")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    build(args.out, args.source_commit, args.check)


if __name__ == "__main__":
    main()
