"""Pinned shared-style publication figures and reading layer over checked data."""
from __future__ import annotations
import argparse
from fractions import Fraction as Q
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
if str(ROOT/'scripts/reports') not in sys.path:sys.path.insert(0,str(ROOT/'scripts/reports'))
from scripts.reports.mpc06_delivery import records
from figure_style import configure_numeric_axis,STYLE_ID
from plot import normalize_owned_svg

COLORS={'finite-reference':'#89b4fa','polytope':'#a6e3a1','inflated-zonotope':'#f9e2af','ellipsoid-certified':'#f38ba8'}


def figure_data(record,online):
    methods=tuple(COLORS)
    paths=[]
    for method in methods:
        attempt=next(a for a in online['attempts'] if a['method']==method and a['status']=='completed')
        worst=max(attempt['actual']['paths'],key=lambda row:Q(row['cost']))
        paths.append(dict(method=method,repetition=attempt['repetition'],initial=attempt['initial'],
            disturbances=worst['disturbances'],states=worst['states'],cost=worst['cost']))
    return dict(geometry=record['geometry'],actual_paths=paths,
        initial_grid=[dict(anchor=row['anchor'],method=row['method'],feasible=row['qp']['feasible']) for row in online['grid']['rows']],
        scopes=dict(invariant='analytical illustration of checked stored-model sets; not algorithm replay',
            paths='actual saved three-step receding-controller worst histories for the first initial state',
            grid='finite 17x17 initial-state feasibility samples under the same prescribed-K planning semantics; not a winning-set area'))


def save(fig,output,stem):
    owned=io.StringIO();fig.savefig(owned,format='svg',metadata={'Date':None,'Format':None,'Type':None,'Creator':None})
    (output/(stem+'.svg')).write_bytes(normalize_owned_svg(owned.getvalue()))
    fig.savefig(output/(stem+'.png'),dpi=150,metadata={'Software':'CSL MPC06 publication'})


def plot(data,output):
    os.environ.setdefault('MPLCONFIGDIR',str(output.parent/'mpc06-mpl-cache'))
    import matplotlib
    if matplotlib.__version__!='3.11.2':raise ValueError('Matplotlib 3.11.2 is required')
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon,Rectangle
    import math
    style={'font.family':'DejaVu Sans','font.size':10,'svg.hashsalt':'csl-mpc06-delivery-v1','svg.fonttype':'path',
        'figure.facecolor':'#1e1e2e','axes.facecolor':'#1e1e2e','text.color':'#cdd6f4','axes.labelcolor':'#cdd6f4',
        'axes.edgecolor':'#cdd6f4','xtick.color':'#cdd6f4','ytick.color':'#cdd6f4','legend.facecolor':'#1e1e2e','legend.labelcolor':'#cdd6f4'}
    with matplotlib.rc_context(style):
        fig,axes=plt.subplots(1,2,figsize=(11,5),layout='constrained')
        try:
            vertices=[[float(Q(x)) for x in row] for row in data['geometry']['exact_Z_vertices']]
            axes[0].add_patch(Polygon(vertices,closed=True,facecolor=COLORS['polytope'],alpha=.3,edgecolor=COLORS['polytope'],label='exact invariant Z'))
            radii=data['geometry']['native_APP04']['radii'];circle=[]
            for k in range(257):
                theta=2*math.pi*k/256;s=radii[0]*math.cos(theta);t=radii[1]*math.sin(theta);circle.append((s,t-s))
            axes[0].plot([p[0] for p in circle],[p[1] for p in circle],color='#f38ba8',linestyle='--',label='APP-04 outer; rejected for RPI')
            axes[0].set(xlabel='error position e[0]',ylabel='error velocity e[1]',title='Invariant error tube / unsafe RPI inference')
            axes[0].legend(fontsize=8);axes[0].set_aspect('equal',adjustable='box')
            axes[1].add_patch(Rectangle((-1,-1),2,2,fill=False,edgecolor='#cdd6f4',label='original X'))
            for method,bounds in data['geometry']['tightened_state_halfwidths'].items():
                hp,hq=map(lambda x:float(Q(x)),bounds)
                axes[1].add_patch(Rectangle((-hp,-hq),2*hp,2*hq,fill=False,edgecolor=COLORS[method],label=method))
            axes[1].set(xlim=(-1.1,1.1),ylim=(-1.1,1.1),xlabel='nominal position z[0]',ylabel='nominal velocity z[1]',title='Sound state tightenings X minus error set')
            axes[1].legend(fontsize=8);axes[1].set_aspect('equal',adjustable='box')
            for axis in axes:configure_numeric_axis(axis)
            fig.suptitle('Two-state LTI fixture; analytical set illustration from checked stored-model inputs')
            save(fig,output,'invariant-tightenings')
        finally:plt.close(fig)
        fig,axis=plt.subplots(figsize=(7,5),layout='constrained')
        try:
            for item in data['actual_paths']:
                points=[[float(Q(x)) for x in row] for row in item['states']]
                axis.plot([p[0] for p in points],[p[1] for p in points],marker='o',color=COLORS[item['method']],label=item['method'],alpha=.8)
            axis.set(xlabel='actual position x[0]',ylabel='actual velocity x[1]',title='Saved actual receding-controller worst paths: n=2, three steps')
            configure_numeric_axis(axis);axis.legend(fontsize=8);axis.set_aspect('equal',adjustable='box')
            fig.supxlabel('First initial state; overlapping curves do not establish equal policies. Original X=[-1,1]².',fontsize=8)
            save(fig,output,'actual-state-paths')
        finally:plt.close(fig)
        fig,axes=plt.subplots(2,2,figsize=(10,9),layout='constrained')
        try:
            for axis,method in zip(axes.flat,COLORS):
                rows=[row for row in data['initial_grid'] if row['method']==method]
                for feasible,marker,color,label in ((False,'x','#6c7086','infeasible'),(True,'o',COLORS[method],'feasible')):
                    values=[row['anchor'] for row in rows if row['feasible']==feasible]
                    axis.scatter([float(Q(p[0])) for p in values],[float(Q(p[1])) for p in values],s=15,marker=marker,color=color,label=label)
                axis.set(xlim=(-1.08,1.08),ylim=(-1.08,1.08),xlabel='initial position p',ylabel='initial velocity q',title=method+': '+str(sum(r['feasible'] for r in rows))+'/289 feasible')
                configure_numeric_axis(axis);axis.set_aspect('equal',adjustable='box')
            fig.suptitle('Same prescribed-K / nominal-terminal-zero planning; finite initial-state grid')
            fig.supxlabel('Circles: feasible (panel color); crosses: infeasible. Samples are not a complete winning set or a volume certificate.',fontsize=9)
            save(fig,output,'feasibility-grid')
        finally:plt.close(fig)


def reading_page(record,verification):
    parts=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MPC-06 matched tube and fixed-plan references</title>',
        '<style>body{font:16px/1.6 system-ui;max-width:1150px;margin:2rem auto;padding:1rem;background:#1e1e2e;color:#cdd6f4}a{color:#89b4fa}img{max-width:100%;height:auto}table{display:block;overflow-x:auto;border-collapse:collapse}td,th{padding:.5rem;text-align:left;border-bottom:1px solid #45475a}code{color:#f9e2af}</style>',
        '<h1>Tube MPC, matched robust checks and exact tiny minimax references</h1>',
        '<p>Affine LTI A=[[1,1],[0,1]], B=E=(0,1), X=[-1,1]², U=[-1,1], W=[-1/8,1/8]. State dimension two; exact full-state feedback and continuous actuators. The prescribed K=(-1,-2) makes F²=0. Initial states are (1/8,0), (3/8,-1/8), (-1/4,1/8), with initial error zero. LTV, model/correlated uncertainty and finite actuators remain unsupported.</p>',
        f'<p>Native capture source <code>{record["native_source_commit"]}</code>; reference/reading source <code>{record["source_commit"]}</code>. Independent verification: {verification["exact_reference_cases"]} exact class minima and {verification["held_native_plans"]} matched held native plans. <a href="input/result.json">Exact results and certificates</a>; <a href="input/verification.json">verification</a>; <a href="input/online/verification-v2.json">bound native-capture receipt</a>; <a href="publication-manifest.json">publication manifest</a>.</p>',
        '<h2>Policy and objective boundaries</h2><p>M0 chooses one fixed actual open-loop plan. The fixed-K reference chooses one nominal plan and applies u=v+K(x-z), retaining that plan for three steps. Both require nominal z3=0, so v=(a,-p-3q-2a,p+2q+a). They minimize the actual continuous-disturbance worst cost sum(x_t²+u_t²)+x3², computed from all eight disturbance vertices. Each path cost has common positive quadratic coefficient 9 in a. Exact rational envelope candidates and an independent active-subgradient/endpoint certificate prove each reported class minimum. These are distinct restricted policy classes; no cross-class bound ordering or general causal optimum is asserted.</p>',
        '<p>The native MPC minimizes a nominal surrogate and reoptimizes a propagated anchor each step. To compare with the frozen-plan K reference, we hold its FIRST predicted native plan for three steps. Those matched gaps are nonnegative. Its actual three executed receding steps have different terminal/tail semantics and are reported separately, never treated as a minimax optimality gap.</p>',
        '<table><tr><th>Initial (p,q)</th><th>M0 optimum a / worst J</th><th>Fixed-K optimum a / worst J</th><th>Held native worst J range</th><th>Matched K gap range</th><th>Actual receding-prefix J range</th></tr>']
    def span(values):return f'[{float(min(values)):.6g}, {float(max(values)):.6g}]'
    for case in record['cases']:
        m0,k=case['references'];held=case['held_first_native_plans'];receding=case['actual_receding_prefix_costs']
        parts.append(f'<tr><td>{case["initial"]}</td><td>{m0["a"]} / {m0["worst_cost"]}</td><td>{k["a"]} / {k["worst_cost"]}</td><td>{span([Q(x["worst_cost"]) for x in held])}</td><td>{span([Q(x["fixed_K_minimax_gap"]) for x in held])}</td><td>{span([Q(x["worst_cost"]) for x in receding])}</td></tr>')
    parts+=['</table><h2>Invariant tube and sound tightenings</h2><p>Exact polytope/parallelotope/zonotope descriptions preserve the same Z. The inflated zonotope and independently certified ellipse are outer invariant tubes. The coordinate box and actual APP-04 outer ellipse contain Z but fail RPI and are rejected with rational successor witnesses. Set volume alone is not evidence. The original pilot and its fixed-policy 3/8 result remain immutable.</p><img src="invariant-tightenings.svg" alt="Two-state invariant error tube and sound tightened state rectangles">',
        '<h2>Recorded actual paths</h2><p>These are actual saved three-step receding-controller worst histories for the first initial state, not the frozen-plan references. Renderers execute no optimization.</p><img src="actual-state-paths.svg" alt="Saved position and velocity trajectories under stagewise disturbances">',
        '<h2>Matched finite-grid feasibility</h2><p>Finite-error and invariant-tube intervals retain identical prescribed-K and nominal-terminal-zero semantics. The 17x17 grid reports conservatism, not a complete state-feedback winning set. Unsafe disturbance paths are rejected rather than clipped.</p><img src="feasibility-grid.svg" alt="Four finite initial-state feasibility grids under matched planning semantics">',
        '<h2>Cost accounting, dependencies and reproduction</h2><p>The saved native record separates APP-04 offline construction, online preparation/setup/solve, exact construction/checking and process observations. K is prescribed, not optimized. The historical nilpotent Z/terminal proof has no isolated construction timing; unavailable values are not zero-cost claims. <a href="input/online/summary.json">Native distributions</a> remain descriptive and inconclusive for performance ranking; no universal winner or hard real-time claim is made.</p>',
        '<p>Build/recheck the source at the recorded revision using <code>python scripts/reports/mpc06_delivery/records.py --check &lt;saved-input&gt;</code>. Pinned Matplotlib 3.11.2 and the shared quantitative axis policy generate these figures from checked saved inputs. Full sources, prior raw stdout/stderr and exact certificates are in <a href="input/">the input bundle</a>. No native solve is run during checking, plotting or staging.</p>',
        '<p>HiGHS 1.11.0 remains the existing optional MIT QP integration; no acados or new solver is installed. This source/report delivery adds no public API, package layout or installed binary. Existing GCC/Clang/MSVC native smoke qualifications remain those actually exercised by PR #899; no new binary-distribution or license approval is inferred. The project distribution-license decision remains separate. Numerical optimum evidence is distinct from exact stored-value safety/reference proof. Publication requires independent review, main-only stale-head checks and live URL verification; #602 remains open until the completion audit.</p></html>']
    return '\n'.join(parts)+'\n'


def render(source,output):
    record,online,verification,contents=records.validate(source)
    if output.exists() or output.resolve().is_relative_to(source.resolve()):raise ValueError('publication output must be new and separate')
    output.mkdir(parents=True);shutil.copytree(source,output/'input')
    data=figure_data(record,online)
    (output/'figure-data.json').write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    plot(data,output)
    (output/'index.html').write_text(reading_page(record,verification),encoding='utf-8')
    (output/'README.md').write_text('''# MPC-06 complete source/report delivery

This reading layer preserves the existing native capture and adds exact finite-horizon fixed-policy references. The source commit and source-file digests are in input/result.json. The complete native archive, bound receipt and raw streams are under input/online/. No native experiment is rerun for publication.

Check with python scripts/reports/mpc06_delivery/records.py --check <saved-report>/input from the recorded source checkout. Regenerate the reading layer with the pinned scripts/reports/requirements.txt environment and python scripts/reports/mpc06_delivery/figures.py --source <saved-report>/input --output <new-directory>. Staging independently rechecks mathematics, upstream bindings, all hashes and deterministic renderer output before producing an immutable route and ZIP.

M0 and prescribed-K references have distinct policy classes and nominal z3=0. Only a first predicted native plan HELD for three steps has a matched fixed-K minimax gap. The actual receding prefix is separate. All prior finite-grid, unsupported-model, numerical/native-evidence and no-performance-winner limits remain. This is a source/report artifact, not an installed binary or new API; no standalone library release is needed. Main-only publication, independent completion review and live URL verification remain gates for issue closure.
''',encoding='utf-8')
    export=dict(schema='csl.mpc06-publication-figures/1',matplotlib='3.11.2',quantitative_axis_policy=STYLE_ID,
        source_result_sha256=hashlib.sha256(contents['result.json']).hexdigest(),
        native_capture_receipt_sha256=hashlib.sha256((source/'online/verification-v2.json').read_bytes()).hexdigest(),
        figure_data_sha256=hashlib.sha256((output/'figure-data.json').read_bytes()).hexdigest(),
        files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir()) if p.suffix in ('.svg','.png')})
    (output/'figure-export.json').write_text(json.dumps(export,indent=2)+'\n',encoding='utf-8')
    paths=sorted(p for p in output.rglob('*') if p.is_file())
    (output/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(output).as_posix()}\n' for p in paths),encoding='utf-8')
    return export


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    print(json.dumps(render(args.source,args.output)))
