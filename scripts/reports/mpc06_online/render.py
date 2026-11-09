#!/usr/bin/env python3
"""Render saved MPC-06 anchored-controller records; never execute a solver."""
import argparse
from collections import Counter,defaultdict
from fractions import Fraction as Q
import hashlib
import html
import json
from pathlib import Path
import statistics


def render(bundle):
    record=json.loads((bundle/'result.json').read_text());verified=json.loads((bundle/'verification.json').read_text())
    if verified['status'] not in ('verified','inconclusive'):raise ValueError('missing independent check')
    grid=record['grid']['rows'];counts=Counter(row['method'] for row in grid if row['qp']['feasible'])
    rows=[];metrics=defaultdict(list)
    for attempt in record['attempts']:
        if attempt['status']!='completed':continue
        for step in attempt['steps']:
            for name in ('prepare_ns','setup_ns','solve_ns'):metrics[attempt['method'],name].append(step['native'][name])
            for name in ('checker_ns','exact_construction_ns','native_roundtrip_ns'):metrics[attempt['method'],name].append(step[name])
    methods=('finite-reference','polytope','inflated-zonotope','ellipsoid-certified')
    for method in methods:
        row=dict(method=method,grid_feasible=counts[method],feasibility_loss=counts['finite-reference']-counts[method])
        for metric in ('prepare_ns','setup_ns','solve_ns','checker_ns','exact_construction_ns','native_roundtrip_ns'):
            values=metrics[method,metric]
            row[metric]=dict(median=statistics.median(values),min=min(values),max=max(values)) if values else None
        row['actual_worst_costs']=[str(Q(a['actual']['worst'])) for a in record['attempts'] if a['status']=='completed' and a['method']==method]
        rows.append(row)
    summary=dict(schema='csl.mpc06-online-summary/1',rows=rows,verification=verified,
        offline_grid_construction_and_check_ns=record['grid']['elapsed_ns'],
        offline_native_approximation_ns=[p['approximation']['construction_ns'] for p in record['processes'] if 'approximation' in p],
        offline_approximation_check_ns=[p['independent_approximation']['checker_ns'] for p in record['processes'] if 'independent_approximation' in p],
        verdict='descriptive restricted-policy study; no universal winner or real-time claim')
    (bundle/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    # A genuine two-state phase plot from saved actual disturbance histories.
    colors={'finite-reference':'#89b4fa','polytope':'#a6e3a1','inflated-zonotope':'#f9e2af','ellipsoid-certified':'#f38ba8'}
    parts=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 600" role="img" aria-labelledby="title desc">',
        '<title id="title">Saved actual worst-disturbance state paths, state dimension two</title>',
        '<desc id="desc">Position versus velocity, three executed stages; original state constraint square, one stored maximizing path for each admitted restricted controller.</desc>',
        '<rect width="760" height="600" fill="#1e1e2e"/>',
        '<text x="380" y="26" text-anchor="middle" fill="#cdd6f4" font-family="sans-serif">n=2 state phase plane; three executed receding steps</text>',
        '<rect x="70" y="60" width="480" height="480" fill="none" stroke="#6c7086"/>']
    def xy(state):return (310+240*float(Q(state[0])),300-240*float(Q(state[1])))
    for v in (-1,-.5,0,.5,1):
        x=310+240*v;y=300-240*v
        parts.extend([f'<path d="M{x} 60V540 M70 {y}H550" stroke="#45475a"/>',f'<text x="{x}" y="560" text-anchor="middle" fill="#cdd6f4">{v:g}</text>',f'<text x="60" y="{y+5}" text-anchor="end" fill="#cdd6f4">{v:g}</text>'])
    for i,method in enumerate(methods):
        attempt=next((a for a in record['attempts'] if a['method']==method and a['status']=='completed'),None)
        if attempt is None:continue
        path=max(attempt['actual']['paths'],key=lambda p:Q(p['cost']))
        points=' '.join(f'{x:.6f},{y:.6f}' for x,y in map(xy,path['states']))
        parts.append(f'<polyline points="{points}" fill="none" stroke="{colors[method]}" stroke-width="{2+i}" opacity=".8"/>')
        for x,y in map(xy,path['states']):parts.append(f'<circle cx="{x}" cy="{y}" r="{3+i}" fill="none" stroke="{colors[method]}"/>')
        parts.append(f'<text x="565" y="{80+i*35}" fill="{colors[method]}" font-size="11">{html.escape(method)}</text>')
    parts+=['<text x="310" y="590" text-anchor="middle" fill="#cdd6f4">position x[0] (dimensionless)</text>',
        '<text x="20" y="300" transform="rotate(-90 20 300)" text-anchor="middle" fill="#cdd6f4">velocity x[1] (dimensionless)</text></svg>']
    (bundle/'online-state-paths.svg').write_text('\n'.join(parts)+'\n')
    text=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MPC-06 propagated-anchor study</title>',
        '<style>body{font:16px/1.6 system-ui;max-width:1100px;margin:2rem auto;padding:1rem;background:#1e1e2e;color:#cdd6f4}a{color:#89b4fa}table{border-collapse:collapse;width:100%}td,th{padding:.5rem;text-align:left;border-bottom:1px solid #45475a}img{max-width:100%;height:auto}</style>',
        '<h1>Tube MPC with a retained nominal anchor</h1>',
        '<p>This bounded two-state LTI study solves actual CSL/HiGHS nominal QPs, compares matched fixed-K robust feasibility, and independently checks all continuous-box disturbance costs for the recorded deterministic nominal schedules. It does not compute fixed-plan minimax or general causal optimum.</p>',
        f'<p>Source <code>{html.escape(record["source_commit"])}</code>. Independent replay: {html.escape(verified["status"])}; {verified["completed_native_qps"]} completed native QPs. <a href="result.json">Raw mathematical/process records</a>, <a href="verification.json">checker receipt</a>, <a href="summary.json">cost/timing distributions</a>.</p>',
        '<p>At each step u=v+K(x-z), K=(-1,-2); z propagates with the applied nominal v. Full-state measurements affect only the fixed ancillary feedback. The nominal N=3 objective is sum(z²+v²), with terminal z3=0. The finite-error reference uses the same policy and global disturbance clock; invariant tubes are conservative restrictions. All original state/control bounds are checked without clipping. The actual reported objective is sum(x²+u²)+x3² over the three executed steps.</p>',
        '<h2>Matched feasible intervals and online cost</h2><p>The 17 by 17 initial grid is finite and is not a complete feedback-winning-set characterization. Times are medians [minimum, maximum] in microseconds over completed steps; process/IPC timing is separate from native solve. No performance ranking is claimed.</p>',
        '<table><tr><th>Method</th><th>Grid feasible / lost</th><th>Native setup</th><th>Native solve</th><th>Exact QP construction</th><th>Independent QP check</th></tr>']
    def duration(d):return 'unavailable' if d is None else f'{d["median"]/1000:.2f} [{d["min"]/1000:.2f}, {d["max"]/1000:.2f}]'
    for row in rows:text.append(f'<tr><td>{row["method"]}</td><td>{row["grid_feasible"]} / {row["feasibility_loss"]}</td><td>{duration(row["setup_ns"])}</td><td>{duration(row["solve_ns"])}</td><td>{duration(row["exact_construction_ns"])}</td><td>{duration(row["checker_ns"])}</td></tr>')
    text+=['</table><h2>Sound enclosure is separate from invariance</h2><p>Equivalent polytope/parallelotope/zonotope descriptions preserve Z. The inflated zonotope and separately certified ellipsoid pass exact RPI and support bounds. The outer coordinate box and the actual APP-04 outer ellipse fail RPI with rational successor witnesses and are rejected for recursive control. Their enclosure direction remains outer; rejection is not an incorrect approximation claim.</p>',
        '<h2>Saved actual state paths</h2><p>State dimension two, position/velocity coordinates. One saved maximizing disturbance path per admitted method is shown for the first initial state. Overlapping curves are valid; they do not establish equal policies on other states.</p><img src="online-state-paths.svg" alt="Two-state position-velocity plot from saved actual maximizing disturbance paths">',
        '<p>The original required <a href="https://butahlecoq.github.io/controlled-systems-lab/mpc06-tube-405a8ac4eb2bea7ebec8/index.html">invariant/tightening figure</a> remains unchanged. These trajectories add online evidence; rendering executes no solver.</p>',
        '<h2>Scope and delivery</h2><p>Actual cost is checked with exact dyadic controls over all eight disturbance vertices; convexity proves the continuous-box maximum for this deterministic-anchor policy. Native optimum agreement is numerical with an independent exact scalar optimum, not a solver certificate. Initial error is zero, actuators are continuous and disturbances are independent stagewise additive intervals. LTV, correlated/model uncertainty, finite actuators, state-reset policies and general stable-tail construction are unsupported.</p>',
        '<p>Offline construction, online preparation/setup/solve and checker costs are retained separately. This Linux capture does not establish other-platform performance, native thread enforcement, memory caps or hard deadlines. HiGHS is the existing optional MIT integration; no acados or new required dependency is introduced. Compiler/platform/install checks, independent review and versioned Pages publication remain integration gates; no release is needed for the research tool. Issue #602 remains open until all evidence gates pass.</p></html>']
    (bundle/'index.html').write_text('\n'.join(text)+'\n')
    paths=sorted(p for p in bundle.rglob('*') if p.is_file() and p.name!='SHA256SUMS')
    (bundle/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(bundle)}\n' for p in paths))
    return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('bundle',type=Path);args=parser.parse_args();render(args.bundle)
