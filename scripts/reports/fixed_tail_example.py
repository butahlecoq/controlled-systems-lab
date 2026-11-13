"""Render a checked native fixed-tail fixture; never execute a controller."""
from __future__ import annotations

import hashlib
import itertools
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = 'fixed-tail-tiny-a6'
PAGE = 'native-fixed-tail-2d.html'
FIGURE = 'native-fixed-tail-2d.svg'
ANCHOR = 'native-fixed-tail-2d'
FAMILIES = ('polytope', 'box', 'zonotope', 'parallelotope', 'ellipsoid')
COLORS = ('#ae81ff', '#66d9ef', '#f92672', '#fd971f', '#a6e22e')


def convex_boundary(points):
    points = sorted(set(points))
    def cross(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    lower, upper = [], []
    for row, chain in ((points, lower), (list(reversed(points)), upper)):
        for point in row:
            while len(chain) > 1 and cross(chain[-2], chain[-1], point) <= 0:
                chain.pop()
            chain.append(point)
    return lower[:-1] + upper[:-1]


def boundary(region):
    if region['family'] == 'polytope':
        lo, hi = region['carrier_lower'], region['carrier_upper']
        polygon = [(lo[0], lo[1]), (hi[0], lo[1]), (hi[0], hi[1]), (lo[0], hi[1])]
        for row, bound in zip(region['reference']['inequalities'], region['reference']['upper_bounds']):
            clipped = []
            for a, b in zip(polygon, polygon[1:] + polygon[:1]):
                da, db = sum(x*y for x, y in zip(row, a))-bound, sum(x*y for x, y in zip(row, b))-bound
                if da <= 1e-12:
                    clipped.append(a)
                if da < 0 < db or db < 0 < da:
                    clipped.append(tuple(x+(y-x)*(-da)/(db-da) for x, y in zip(a, b)))
            polygon = clipped
        return polygon
    member = region['membership']
    center, factor = member['center'], member['factor']
    if member['factor_domain_norm'] == 'l2':
        factors = [(math.cos(k*math.tau/128), math.sin(k*math.tau/128)) for k in range(128)]
    else:
        factors = itertools.product((-1, 1), repeat=len(factor[0]))
    points = [tuple(center[i] + sum(a*b for a, b in zip(factor[i], value)) for i in range(2)) for value in factors]
    return convex_boundary(points) if member['factor_domain_norm'] != 'l2' else points


def audit(responses):
    target = (1.8, 1.3)
    difference = (target[0]-target[1])/1.02
    expected = {'polytope': (1, 1), 'box': (1, 1),
        'parallelotope': ((1+difference)/2, (1-difference)/2),
        'zonotope': ((math.sqrt(2)+difference)/2, (math.sqrt(2)-difference)/2),
        'ellipsoid': tuple(value/math.hypot(*target) for value in target)}
    checks = {}
    for family, response in responses.items():
        if response['status'] != 'accepted' or len(response['regions']) != 2:
            raise ValueError('fixture must retain both physical stages and an accepted native query')
        control = response['control']
        cost = sum((x-y)**2 for x, y in zip(control, target)) + .02*sum(x*x for x in control)
        if (max(abs(a-b) for a, b in zip(control, expected[family])) > 1e-7
                or abs(cost-response['source_cost']['total']) > 1e-9
                or max(abs(a-b) for a, b in zip(response['history'], [0, 0, *control, *control])) > 1e-9):
            raise ValueError('native fixture differs from its independent mathematical answer')
        checks[family] = {'control': control, 'closed_form_control': expected[family],
                          'source_cost': cost, 'accepted': True}
    return checks


def figure(responses):
    def xy(point):
        return 100+(point[0]+1.2)*235, 560-(point[1]+1.2)*165
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="650" viewBox="0 0 1000 650" role="img" aria-labelledby="title description">',
        '<title id="title">Five native physical families produce different controls</title>',
        '<desc id="description">A square, octagon, diamond and circle share the origin. Native optimized endpoints differ when the physical inner family changes. Box and polytope coincide.</desc>',
        '<rect width="1000" height="650" fill="#272822"/>',
        '<g font-family="system-ui,sans-serif" fill="#f8f8f2" font-size="18">']
    for value in (-1, 0, 1, 2):
        x, _ = xy((value, 0))
        parts.append(f'<path d="M{x} 65V560" stroke="#504945"/><text x="{x}" y="590" text-anchor="middle">{value}</text>')
    for value in (-1, 0, 1):
        _, y = xy((0, value))
        parts.append(f'<path d="M100 {y}H880" stroke="#504945"/><text x="83" y="{y+6}" text-anchor="end">{value}</text>')
    for family, color in zip(FAMILIES, COLORS):
        points = boundary(responses[family]['regions'][1])
        values = ' '.join(f'{xy(point)[0]:.3f},{xy(point)[1]:.3f}' for point in points)
        dash = ' stroke-dasharray="8 5"' if family == 'polytope' else ''
        parts.append(f'<polygon points="{values}" fill="none" stroke="{color}" stroke-width="3"{dash}/>')
        end = xy(responses[family]['control']); origin = xy((0, 0))
        parts.append(f'<path d="M{origin[0]} {origin[1]}L{end[0]} {end[1]}" stroke="{color}" stroke-width="1.5" opacity=".6"/><circle cx="{end[0]}" cy="{end[1]}" r="5" fill="{color}"/>')
    for i, (family, color) in enumerate(zip(FAMILIES, COLORS)):
        parts.append(f'<path d="M{100+i*175} 35h22" stroke="{color}" stroke-width="3"/><text x="{129+i*175}" y="41" font-size="15">{family}</text>')
    x, y = xy((1.8, 1.3))
    parts.append(f'<path d="M{x-7} {y-7}l14 14m-14 0l14-14" stroke="#f8f8f2" stroke-width="2"/><text x="{x-4}" y="{y-15}" text-anchor="end">soft target (1.8, 1.3)</text>')
    x, y = xy((0, 0))
    parts.append(f'<circle cx="{x}" cy="{y}" r="6" fill="#f8f8f2"/><text x="{x-10}" y="{y+25}" text-anchor="end">initial point</text>')
    parts.append('<text x="900" y="590">x₁</text><text x="70" y="65">x₂</text><text x="100" y="630" font-size="16">Solid points: native minimizers of the complete stated cost. Polytopes and boxes coincide in this fixture.</text></g></svg>')
    return ''.join(parts).encode()


def page(responses, source):
    def column(values):
        cells = ''.join(f'<mtr><mtd><mn>{value:.6g}</mn></mtd></mtr>' for value in values)
        return ('<span class="math-matrix"><span class="math-bracket math-bracket-left" aria-hidden="true"></span>'
            '<math xmlns="http://www.w3.org/1998/Math/MathML"><mtable>' + cells + '</mtable></math>'
            '<span class="math-bracket math-bracket-right" aria-hidden="true"></span></span>')
    rows = ''.join(f'<tr><th scope="row">{family}</th><td>{column(response["control"])}</td><td>{response["source_cost"]["total"]:.6g}</td></tr>' for family, response in responses.items())
    links = ' · '.join(f'<a href="{DATA}/{family}/request.jsonl">{family} input</a> / <a href="{DATA}/{family}/response.jsonl">output</a>' for family in FAMILIES)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Native fixed-tail control in two dimensions</title><link rel="stylesheet" href="examples.css"></head>
<body><a class="skip" href="#main">Skip to example</a><main id="main" class="page-content"><nav class="breadcrumbs" aria-label="Breadcrumb"><ol><li><a href="../index.html">Learn</a></li><li><a href="index.html">Examples</a></li><li aria-current="page">Native fixed-tail control</li></ol></nav>
<p class="eyebrow">Native C++ · supported 2D functional example</p><h1>Change the physical set, change the control</h1>
<p>Start at the origin, apply one continuous two-component input, and observe the terminal state. All five calls use the same model, source cost, IPOPT provider and input square. Only the selected inner physical family changes.</p>
<div class="math-input"><div class="math-expression"><span>x(0) =</span><span class="math-matrix"><span class="math-bracket math-bracket-left" aria-hidden="true"></span><math xmlns="http://www.w3.org/1998/Math/MathML" aria-label="column vector zero, zero"><mtable><mtr><mtd><mn>0</mn></mtd></mtr><mtr><mtd><mn>0</mn></mtd></mtr></mtable></math><span class="math-bracket math-bracket-right" aria-hidden="true"></span></span><span>, x(1) = x(0) + u,</span><span>u ∈ [−1, 1]².</span></div>
<p>J(u) = ‖x(1) − (1.8, 1.3)ᵀ‖²₂ + 0.02 ‖u‖²₂. State bounds at both stages are [−3, 3]². The target is a soft cost reference.</p></div>
<div class="scroll" role="region" aria-label="Five physical families and native optimized controls" tabindex="0"><img src="{FIGURE}" style="min-width:640px" alt="The five native physical inner sets and their different optimizing terminal states"></div><p><a href="{FIGURE}">Open the full-size figure</a></p><p class="note">At stage 0 every family is the initial point. At stage 1 the full reachable square and all-control carrier coincide. The polytope and box coincide too; the other selected templates occupy different parts of that square.</p>
<h2>Read the native answer</h2><div class="scroll" role="region" aria-label="Native controls and complete cost" tabindex="0"><table><thead><tr><th>Family</th><th>u = x(1)</th><th>J</th></tr></thead><tbody>{rows}</tbody></table></div><p class="note">Display: six significant digits. Linked native records retain the binary64 values.</p>
<p>For the box, minimizing each coordinate gives (1, 1)ᵀ. For the circle, normalize the target vector. For the diamond, u₁ + u₂ = 1 and u₁ − u₂ = (1.8 − 1.3)/1.02. The octagon instead has u₁ + u₂ = √2 on the active face. The independent audit checks these closed-form answers against the saved native results.</p>
<h2>Use the same controller for longer horizons</h2><p>The native algorithm first finds a feasible full history with a constant auxiliary objective, freezes its future controls, and constructs every selected physical stage region. It then minimizes the complete original source cost over the current continuous action. Future states and the full history follow typed affine lifts. The source running-stage schedule, original horizon and terminal objective remain intact.</p>
<p>For a factor set x = c + Gξ, boxes, parallelotopes and zonotopes use ‖ξ‖∞ ≤ 1 with ℓ₁ row-support bounds. Ellipsoids use ‖ξ‖₂ ≤ 1 with ℓ₂ row support. The output names the factor-domain norm and support norm separately. Canonical shifted histories and supplied zero duals are prepared in C++.</p>
<p class="limits">Longer-horizon regions are conditional on the frozen feasible tail and intersect an all-control axis carrier. They are not global backward reachable sets. The final solve frees only the current input; it is distinct from optimizing the entire remaining control history. These are local numerical functional results, without a global-optimum, recursive-feasibility, nonlinear-safety or performance claim.</p>
<h2>Reproduce and inspect</h2><details><summary>Build the native optional profile and run one saved input</summary><pre><code>cmake -S . -B build/fixed-tail -DCMAKE_BUILD_TYPE=Release \\
  -DCSL_ENABLE_HIGHS=OFF -DCSL_ENABLE_QHULL=OFF \\
  -DCSL_ENABLE_CASADI=ON -Dcasadi_DIR=&lt;matching-native-CasADi-prefix&gt;/cmake
cmake --build build/fixed-tail --target csl_closed_loop_native_policy --parallel 1
build/fixed-tail/csl_closed_loop_native_policy \\
  &lt; examples/{DATA}/box/request.jsonl</code></pre><p>Provide matching native CasADi C++ headers and libraries. Configuration checks the C++ ABI/link boundary. Python is used externally for reporting and fixture verification; the policy decision pipeline runs in C++.</p></details>
<p>{links}</p><p><a href="{DATA}/task.json">Complete mathematical fixture</a> · <a href="{DATA}/source-expanded.json">Source and binary provenance</a> · <a href="{DATA}/files.sha256">Raw file hashes</a> · <a href="native-fixed-tail-2d-audit.json">Independent audit</a> · <a href="https://github.com/butahlecoq/controlled-systems-lab/commit/{source['native_cpp_source_commit']}">Exact native implementation</a>.</p>
<p class="provenance">Native fixture source {source['fixture_source_commit']}; C++ binary compiled at {source['native_cpp_source_commit']}. Each fixture retains its direct raw stderr file. This page renders saved results and executes no controller.</p></main></body></html>'''.encode()


def build(root: Path = ROOT):
    source = root / 'examples' / DATA
    if source.is_symlink() or not source.is_dir():
        raise ValueError('native fixed-tail fixture directory is missing or symlinked')
    assets = {}
    names = set()
    for line in (source / 'files.sha256').read_text().splitlines():
        digest, name = line.split('  ', 1)
        path = source / name
        if (name in names or '..' in Path(name).parts or Path(name).is_absolute()
                or not path.resolve().is_relative_to(source.resolve()) or path.is_symlink()
                or any(source.joinpath(*Path(name).parts[:i]).is_symlink() for i in range(1, len(Path(name).parts)+1))
                or hashlib.sha256(path.read_bytes()).hexdigest() != digest):
            raise ValueError('native fixed-tail fixture hash/path mismatch')
        names.add(name); assets[f'{DATA}/{name}'] = path.read_bytes()
    if names != {p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file() and p.name != 'files.sha256'}:
        raise ValueError('native fixed-tail fixture inventory differs')
    assets[f'{DATA}/files.sha256'] = (source / 'files.sha256').read_bytes()
    responses = {family: json.loads(assets[f'{DATA}/{family}/response.jsonl']) for family in FAMILIES}
    checks = audit(responses)
    provenance = json.loads(assets[f'{DATA}/source-expanded.json'])
    assets[FIGURE] = figure(responses); assets[PAGE] = page(responses, provenance)
    assets['native-fixed-tail-2d-audit.json'] = (json.dumps(checks, indent=2)+'\n').encode()
    entry = {'family': 'Native set-based control', 'title': 'Five physical families change the continuous action',
        'status': 'saved-data-companion', 'anchor': ANCHOR, 'page': PAGE, 'figure': FIGURE,
        'source_page': f'https://github.com/butahlecoq/controlled-systems-lab/commit/{provenance["native_cpp_source_commit"]}',
        'raw_record': 'native-fixed-tail-2d-audit.json'}
    card = f'<article class="saved-figure" id="{ANCHOR}"><h3>Native fixed-tail control in 2D</h3><a href="{PAGE}"><img src="{FIGURE}" alt="Five physical inner families and their continuous optimized actions"></a><p>Change one physical family while retaining the same original cost and native solver.</p><p><a href="{PAGE}">Open the mathematical example →</a></p></article>'
    return assets, entry, card
