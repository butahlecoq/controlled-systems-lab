#!/usr/bin/env python3
"""Render the saved native Buryatia 2D recursive approximation record."""

import argparse
import hashlib
import html
import json
from pathlib import Path


FAMILIES = [
    ("exact_affine_polytope", "Exact affine polytope", "#f8f8f2"),
    ("unreduced_zonotope", "Unreduced zonotope", "#66d9ef"),
    ("reduced_zonotope", "Reduced zonotope", "#a6e22e"),
    ("parallelotope", "Parallelotope", "#fd971f"),
    ("box", "Box", "#ae81ff"),
    ("ellipsoid", "Factor ellipsoid", "#f92672"),
]


def bounds(records):
    points = [p for row in records for p in row["rendering_vertices"]]
    if not points:
        return (-1.0, 1.0, -1.0, 1.0)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1e-12)
    pad = 0.08 * span
    return min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad


def svg_path(points, extents, width=760, height=520):
    x0, x1, y0, y1 = extents
    margin = 42
    scale = min((width - 2 * margin) / max(x1 - x0, 1e-12),
                (height - 2 * margin) / max(y1 - y0, 1e-12))
    dx = (width - scale * (x1 - x0)) / 2
    dy = (height - scale * (y1 - y0)) / 2
    coords = [(dx + (x - x0) * scale, height - dy - (y - y0) * scale)
              for x, y in points]
    return " ".join(("M" if i == 0 else "L") + f"{x:.2f},{y:.2f}"
                    for i, (x, y) in enumerate(coords)) + (" Z" if len(points) > 2 else "")


def make_svg(records, stage, title):
    selected = [row for row in records if row["stage"] == stage]
    extents = bounds(records)
    paths = []
    for row in selected:
        points = row["rendering_vertices"]
        if not points:
            continue
        key = row["family"]
        label, color = next((label, color) for family, label, color in FAMILIES if family == key)
        opacity = "0.16" if key == "exact_affine_polytope" else "0.20"
        paths.append(f'<path d="{svg_path(points, extents)}" fill="{color}" fill-opacity="{opacity}" '
                     f'stroke="{color}" stroke-width="2"><title>{html.escape(label)}</title></path>')
    xmin, xmax, ymin, ymax = extents
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 520" role="img" '
            f'aria-label="{html.escape(title)}"><rect width="760" height="520" fill="#303129"/>'
            + "".join(paths)
            + '<path d="M42 478H718M42 42V478" stroke="#b7b7af" fill="none"/>'
            + '<text x="380" y="510" fill="#f8f8f2" text-anchor="middle">deviation x₁</text>'
            + '<text x="17" y="260" fill="#f8f8f2" text-anchor="middle" transform="rotate(-90 17 260)">deviation x₂</text>'
            + f'<text x="50" y="30" fill="#d5c4a1">x₁ [{xmin:.4g}, {xmax:.4g}] · x₂ [{ymin:.4g}, {ymax:.4g}]</text></svg>')


def render(raw_path, html_path, terminal_svg_path, manifest_path):
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    records = raw["records"]
    stages = sorted({row["stage"] for row in records})
    expected = {key for key, _, _ in FAMILIES}
    if len(stages) != 61 or {row["family"] for row in records} != expected:
        raise SystemExit("record must contain all six 2D tracks at stages 0 through 60")
    if any(not row["rendering_vertices"] for row in records):
        raise SystemExit("a stage is missing renderable geometry")

    terminal_svg = make_svg(records, 60, "Terminal approximation overlays at stage 60")
    terminal_svg_path.parent.mkdir(parents=True, exist_ok=True)
    terminal_svg_path.write_text(terminal_svg, encoding="utf-8")

    payload = json.dumps(records, separators=(",", ":"), ensure_ascii=False)
    legend = "".join(f'<li><span style="color:{color}">●</span> {label}</li>'
                     for _, label, color in FAMILIES)
    escaped_payload = payload.replace("</", "<\\/")
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Buryatia Lotka–Volterra affine reachability | 2D</title><link rel="stylesheet" href="examples.css">
<style>
body{{background:var(--page);color:var(--text)}} .page-content{{max-width:78rem}}
.controls{{display:flex;align-items:center;gap:1rem;flex-wrap:wrap;padding:1rem;background:var(--surface)}}
.controls input{{flex:1;min-width:14rem}} .plot{{width:100%;height:auto;background:var(--surface)}}
.legend{{display:flex;flex-wrap:wrap;gap:.5rem 1.3rem;list-style:none;padding:0}}
.legend li{{white-space:nowrap}} .grid{{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(18rem,.8fr);gap:1.2rem}}
@media(max-width:780px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><a class="skip" href="#main">Skip to content</a>
<main class="page-content" id="main"><p class="eyebrow">New comparison · source-qualified literal affine variant</p>
<h1>Lotka–Volterra reachable sets, stage by stage</h1>
<p>This example compares six native C++ tracks on the affine deviation recurrence transcribed from the local <code>Volterra.m</code> source identity. It is not the canonical controlled Lotka–Volterra task and makes no nonlinear, feedback, minimax, or timing claim.</p>
<section><h2>Model and source</h2>
<div class="math-input"><p><strong>Deviation state:</strong> z₀ = (1, 2), around nominal physical state (410, 300).</p>
<p><strong>Parameters:</strong> a = 0.9, b = 0.003, c = 0.8, d = 0.002, e = 0.85; h = 2π / (60√(ac)) = {raw['step']:.15g}; uₖ ∈ [−0.3, 0.3] independently.</p>
<p>zₖ₊₁ = Aₖ zₖ + B uₖ, B = (he, 0)ᵀ. The literal script evaluates Aₖ at the next Euler nominal point. Each set is propagated at all 60 stages.</p></div>
<p class="provenance">Private source is not included. SHA-256: <code>{html.escape(raw['source_sha256'])}</code>. Reference values from the independent affine reconstruction: 120 terminal vertices and area 4.619042908487405 (published table rounds to 120 and 4.62). This corrected capture supersedes the earlier ellipse drawing record; the prior bytes remain available under the superseded filename.</p>
</section>
<section><h2>Explore every time slice</h2><p>Use the stage control to inspect the complete stored slice for each family. The factor ellipsoid is sampled only to draw its boundary; the raw record retains the factor matrix and reported support diagnostics.</p>
<div class="controls"><label for="stage">Stage <output id="stage-value">0</output> / 60</label><input id="stage" type="range" min="0" max="60" value="0"><label><input id="all-stages" type="checkbox"> Overlay every stage faintly</label></div>
<div class="grid"><figure><svg id="plot" class="plot" viewBox="0 0 760 520" role="img" aria-label="Reachable set slice"></svg><figcaption id="caption">Stage 0 · deviation coordinates</figcaption></figure>
<aside><h3>Tracks</h3><ul class="legend">{legend}</ul><p>All areas and support diagnostics are computed on the affine deviation sets. Rendering projections are not used as correctness checks.</p></aside></div></section>
<section><h2>Terminal detail</h2><figure>{terminal_svg}<figcaption>Stage 60 overlay. Polygon fills are translucent to distinguish overlapping families.</figcaption></figure>
<div class="scroll"><table><thead><tr><th>Family</th><th>Area</th><th>Excess area</th><th>Vertices</th><th>Generators</th><th>Constraints</th><th>Support diagnostic</th></tr></thead><tbody id="terminal-table"></tbody></table></div></section>
<section><h2>Reproduce</h2><pre><code>cmake -S . -B build -DCSL_BUILD_BURYATIA_REPORT=ON
cmake --build build --target csl_buryatia_approximation_report
python3 scripts/reports/buryatia/check_2d.py --exe build/csl_buryatia_approximation_report --cmake-cache build/CMakeCache.txt --record-out docs/examples/buryatia-volterra-affine-2d-records.json
python3 scripts/reports/buryatia/render_2d.py --raw docs/examples/buryatia-volterra-affine-2d-records.json</code></pre>
<p><a href="{html.escape(raw_path.name)}">Download corrected raw stage records</a> · <a href="{html.escape(manifest_path.name)}">Artifact checksums and scope</a> · <a href="buryatia-volterra-affine-2d-records-superseded-v1.json">Download superseded v1 records</a></p>
<p>Native executable SHA-256: <code>{html.escape(raw['native_build']['executable_sha256'])}</code>; source hashes and build configuration are included in the raw record.</p>
<p>The native driver uses the registered source-index affine-sum operation, native generator operations, axis-cover reduction, registered box and parallelotope producers, a factor ellipsoid recursion, and the existing directional V-to-ellipsoid provider as a separately labeled per-stage candidate.</p>
</section><footer><p>Numerical binary64 record; no validated global rounding certificate. No nonlinear outer-reachability claim.</p></footer></main>
<script id="data" type="application/json">{escaped_payload}</script>
<script>
const rows=JSON.parse(document.getElementById('data').textContent), families={json.dumps(FAMILIES)}, slider=document.getElementById('stage'), all=document.getElementById('all-stages');
const svg=document.getElementById('plot'),NS='http://www.w3.org/2000/svg';
function el(tag,attrs={{}},text=''){{const n=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);if(text)n.textContent=text;return n}}
function path(points,color,opacity,ext){{if(!points.length)return null;const [x0,x1,y0,y1]=ext,w=760,h=520,m=42,s=Math.min((w-2*m)/(x1-x0),(h-2*m)/(y1-y0)),dx=(w-s*(x1-x0))/2,dy=(h-s*(y1-y0))/2;const d=points.map((p,i)=>`${{i?'L':'M'}}${{(dx+(p[0]-x0)*s).toFixed(2)}},${{(h-dy-(p[1]-y0)*s).toFixed(2)}}`).join(' ')+(points.length>2?' Z':'');return el('path',{{d,fill:color,'fill-opacity':opacity,stroke:color,'stroke-width':2}})}}
function draw(){{const stage=+slider.value, selected=rows.filter(r=>all.checked||r.stage===stage),pts=rows.flatMap(r=>r.rendering_vertices),xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]),span=Math.max(Math.max(...xs)-Math.min(...xs),Math.max(...ys)-Math.min(...ys),1e-12),pad=.08*span,ext=[Math.min(...xs)-pad,Math.max(...xs)+pad,Math.min(...ys)-pad,Math.max(...ys)+pad];svg.replaceChildren(el('rect',{{width:760,height:520,fill:'#303129'}}));for(const r of selected){{const f=families.find(x=>x[0]===r.family),p=path(r.rendering_vertices,f[2],r.stage===stage?.22:.035,ext);if(p)svg.append(p)}}svg.append(el('path',{{d:'M42 478H718M42 42V478',stroke:'#b7b7af',fill:'none'}}));svg.append(el('text',{{x:380,y:510,fill:'#f8f8f2','text-anchor':'middle'}},'deviation x₁'));svg.append(el('text',{{x:17,y:260,fill:'#f8f8f2','text-anchor':'middle',transform:'rotate(-90 17 260)'}},'deviation x₂'));document.getElementById('stage-value').value=stage;document.getElementById('caption').textContent=`Stage ${{stage}} · deviation coordinates`}}
slider.addEventListener('input',draw);all.addEventListener('change',draw);draw();
const terminal=rows.filter(r=>r.stage===60);document.getElementById('terminal-table').innerHTML=terminal.map(r=>`<tr><td>${{r.family}}</td><td>${{r.area.toPrecision(7)}}</td><td>${{r.excess_area_vs_affine_reference.toPrecision(5)}}</td><td>${{r.vertex_count}}</td><td>${{r.generator_count}}</td><td>${{r.constraint_count}}</td><td>${{r.max_abs_support_error_8_directions.toPrecision(5)}}</td></tr>`).join('');
</script></body></html>'''
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(page, encoding="utf-8")
    artifacts = [raw_path, html_path, terminal_svg_path]
    manifest = {
        "schema": "csl.buryatia.2d-artifact-manifest/2",
        "case_id": raw["case_id"],
        "source_variant_id": raw["source_variant_id"],
        "source_sha256": raw["source_sha256"],
        "assurance": "numerical binary64; no validated rounding certificate",
        "native_build": raw["native_build"],
        "artifacts": [
            {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in artifacts
        ],
        "superseded_artifacts": [
            {"path": f"docs/examples/{name}",
             "sha256": hashlib.sha256((manifest_path.parent / name).read_bytes()).hexdigest()}
            for name in (
                "buryatia-volterra-affine-2d-records-superseded-v1.json",
                "buryatia-volterra-affine-2d-superseded-v1.html",
                "buryatia-volterra-affine-2d-terminal-superseded-v1.svg",
                "buryatia-volterra-affine-2d-manifest-superseded-v1.json",
            )
        ],
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--html", type=Path, default=Path("docs/examples/buryatia-volterra-affine-2d.html"))
    parser.add_argument("--terminal-svg", type=Path, default=Path("docs/examples/buryatia-volterra-affine-2d-terminal.svg"))
    parser.add_argument("--manifest", type=Path, default=Path("docs/examples/buryatia-volterra-affine-2d-manifest.json"))
    args = parser.parse_args()
    render(args.raw, args.html, args.terminal_svg, args.manifest)


if __name__ == "__main__":
    main()
