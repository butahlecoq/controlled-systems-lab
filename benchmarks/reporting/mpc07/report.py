#!/usr/bin/env python3
"""Recheck saved MPC07 data and render a separate report; no algorithm execution."""
from __future__ import annotations
import argparse
from fractions import Fraction as Q
import hashlib
import json
from pathlib import Path
import re
import statistics
import shutil
import sys
import tempfile
import time
import capture
import policy


def plain(value):return json.loads(json.dumps(value,default=capture.encode))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(root):
    if root.is_symlink() or not root.is_dir():raise ValueError('capture must be regular')
    actual={}
    for p in root.rglob('*'):
        if p.is_symlink() or not(p.is_dir() or p.is_file()):raise ValueError('unsafe capture artifact')
        if p.is_file() and p!=root/'SHA256SUMS':actual[p.relative_to(root).as_posix()]=digest(p)
    expected={}
    for line in (root/'SHA256SUMS').read_text().splitlines():
        match=re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9_./-]+)',line)
        if not match or '..' in Path(match[2]).parts or Path(match[2]).is_absolute() or match[2] in expected:
            raise ValueError('invalid checksum path/inventory')
        expected[match[2]]=match[1]
    if actual!=expected:raise ValueError('capture checksum inventory mismatch')
    return actual


def checked_records(root):
    hashes=inventory(root);environment=json.loads((root/'environment.json').read_text())
    if environment['bridge_sha256']!=capture.BRIDGE_SHA or environment['source_status']:
        raise ValueError('capture source/native identity differs')
    for name,checksum in environment['source_sha256'].items():
        if not re.fullmatch('[A-Za-z0-9_.-]+',name) or digest(root/'source'/name)!=checksum:
            raise ValueError('capture source snapshot binding differs')
    records=[];policies={};rechecks={}
    for parent in ('attempts','probes'):
        for folder in sorted((root/parent).iterdir()):
            saved=json.loads((folder/'check.json').read_text());receipt=json.loads((folder/'receipt.json').read_text())
            for name,checksum in saved['bindings'].items():
                if not re.fullmatch('[A-Za-z0-9_.-]+',name) or digest(folder/name)!=checksum:
                    raise ValueError('saved check input binding differs')
            checked=capture.recheck(folder)
            if checked['status']!=saved['status']:raise ValueError('current saved-data check disposition differs')
            if 'purpose' in receipt:
                records.append(dict(path=str(folder.relative_to(root)),receipt=receipt,current_check=plain(checked)));continue
            for key,value in plain(checked).items():
                if saved.get(key)!=value:raise ValueError('saved exact policy check differs: '+key)
            native=json.loads((folder/'stdout.json').read_text()) if receipt['status']=='completed' else {}
            records.append(dict(path=str(folder.relative_to(root)),receipt=receipt,current_check=plain(checked),
                native_setup_ns=native.get('setup_ns'),native_port_run_ns=native.get('solve_ns')))
            if receipt['horizon']==2 and receipt['sigma']=='5/4' and receipt['policy_class']=='response' and checked['status']=='verified-rational-reconstruction':
                policies['filtered_t2']=checked
    seen=set()
    for row in records:
        r=row['receipt']
        if 'purpose' in r:continue
        key=(r['repetition'],r['horizon'],r['sigma'],r['policy_class'])
        if key in seen:raise ValueError('duplicate scheduled attempt')
        seen.add(key)
        payload=json.loads((root/row['path']/'program.json').read_text())
        profile=payload['profile']
        if (r['horizon'],r['sigma'],r['policy_class'])!=(profile['horizon'],profile['sigma'],profile['policy_class']) or \
                (r['variables'],r['rows'],r['nonzeros'])!=(len(payload['variables']),len(payload['rows']),len(payload['constraints']['values'])):
            raise ValueError('reported profile/size differs from actual native input')
    plan={(rep,n,str(sigma),kind) for rep in range(-1,environment['repetitions']) for n in policy.HORIZONS for sigma in policy.SIGMAS for kind in policy.KINDS}
    if seen!=plan:raise ValueError('scheduled profile inventory differs')
    expected=(environment['repetitions']+1)*24
    if sum('purpose' not in row['receipt'] for row in records)!=expected:raise ValueError('planned primary attempt inventory differs')
    return environment,records,policies,hashes


def metrics(records):
    groups={}
    for row in records:
        r=row['receipt']
        if 'purpose' in r or r['warmup']:continue
        key=f"T{r['horizon']}-sigma{r['sigma']}-{r['policy_class']}"
        group=groups.setdefault(key,dict(attempts=0,verified=0,outcomes={},variables=r['variables'],rows=r['rows'],nonzeros=r['nonzeros'],samples={}))
        group['attempts']+=1;status=row['current_check']['status'];group['outcomes'][status]=group['outcomes'].get(status,0)+1
        if status!='verified-rational-reconstruction':continue
        group['verified']+=1;group['exact_virtual_worst_squared']=row['current_check']['worst_terminal_squared']
        values=dict(python_prepare_ns=r['python_prepare_ns'],whole_process_ns=r['whole_process_ns'],
            native_setup_ns=row['native_setup_ns'],native_port_run_ns=row['native_port_run_ns'])
        for name,value in values.items():
            if type(value) is not int or value<0:raise ValueError('invalid measured clock')
            group['samples'].setdefault(name,[]).append(value)
    for group in groups.values():
        group['times_ns']={name:dict(median=statistics.median(values),minimum=min(values),maximum=max(values)) for name,values in group.pop('samples').items()}
    return groups


def plot(checked,output):
    import matplotlib
    if matplotlib.__version__!='3.11.2':raise ValueError('Matplotlib3.11.2 required for saved figure')
    matplotlib.use('Agg');import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle,Polygon
    sys.path.insert(0,str(capture.ROOT/'scripts/reports'))
    from figure_style import configure_numeric_axis,STYLE_ID
    from itertools import product
    v=checked['policy_v'];m=checked['policy_M'];physical=policy.physical_vertices_two_step(v,m)
    terminal=checked['terminal_response'];offset=checked['terminal_offset'];sigma=Q(5,4)
    virtual=[[offset[k]+sum(terminal[k][j]*w[j] for j in range(2)) for k in range(2)] for w in product((-sigma,sigma),repeat=2)]
    # Order by angle only for the exact affine-box parallelogram.
    import math
    virtual.sort(key=lambda p:math.atan2(float(p[1]-offset[1]),float(p[0]-offset[0])))
    style={'font.family':'DejaVu Sans','svg.hashsalt':'mpc07-fixed-filter-v1','figure.facecolor':'#1e1e2e',
           'axes.facecolor':'#1e1e2e','text.color':'#cdd6f4','axes.labelcolor':'#cdd6f4','axes.edgecolor':'#cdd6f4',
           'xtick.color':'#cdd6f4','ytick.color':'#cdd6f4','legend.labelcolor':'#cdd6f4','legend.facecolor':'#1e1e2e'}
    with plt.rc_context(style):
        fig,axes=plt.subplots(1,2,figsize=(12,5),layout='constrained')
        q=[-16.,0.,16.];upper=[1.25,1.,1.25];lower=[-1.25,-1.,-1.25]
        axes[0].add_patch(Rectangle((-16,-1.25),32,2.5,facecolor='#89b4fa',alpha=.2,label='fixed filter |eta|≤5/4'))
        axes[0].fill_between(q,lower,upper,color='#a6e3a1',alpha=.5,label='physical delta*q+w strip')
        axes[0].axvspan(-1,1,color='#f9e2af',alpha=.3,label='actual stage-1 q range, T=2')
        axes[0].set(xlabel='observed velocity q (state coordinate 1)',ylabel='lumped eta=delta*q+w',title='Sound conservative filter, |delta|≤1/64, |w|≤1',xlim=(-17,17),ylim=(-1.5,1.5))
        axes[1].add_patch(Polygon([[float(x) for x in p] for p in virtual],facecolor='#89b4fa',alpha=.3,label='exact virtual-box terminal set'))
        axes[1].scatter([float(p['terminal'][0]) for p in physical],[float(p['terminal'][1]) for p in physical],color='#a6e3a1',label='physical T2 uncertainty vertices')
        axes[1].set(xlabel='terminal position p2',ylabel='terminal velocity q2',title='Saved response policy u1=−4/5*eta0; scalar disturbance')
        axes[1].set_aspect('equal',adjustable='box')
        for axis in axes:configure_numeric_axis(axis);axis.legend(fontsize=7)
        fig.suptitle('Two-state model: fixed-filter response illustration; not the full jointly optimized SLS-MPC algorithm',fontsize=10)
        for extension in ('svg','png'):
            path=output/('fixed-filter-policy.'+extension)
            fig.savefig(path,dpi=160,metadata={'Date':None} if extension=='svg' else None)
            if extension=='svg':path.write_text('\n'.join(line.rstrip() for line in path.read_text().splitlines())+'\n')
        plt.close(fig)
    return dict(schema='csl.mpc07.figure/1',matplotlib=matplotlib.__version__,quantitative_axis_policy=STYLE_ID,
        virtual_terminal_vertices=virtual,physical_vertices=physical,source_policy=checked,
        exact_physical_t2_worst=max(row['cost'] for row in physical),true_physical_t2_optimum=Q(65,64)**2,
        scope='exact virtual affine-box set; physical points are vertices only, not a general winning set/continuous-safety proof')


def render(root,output):
    if output.exists():raise ValueError('report output must be new')
    env,records,policies,hashes=checked_records(root);groups=metrics(records)
    output.mkdir(parents=True)
    shutil.copytree(root,output/'RAW')
    for name in ('README.md','PLAN.md'):(output/name).write_bytes((root/'source'/name).read_bytes())
    capture.write(output/'current-rechecks.json',records)
    capture.write(output/'summary.json',dict(environment=env,groups=groups,primary_attempts=sum('purpose' not in r['receipt'] for r in records),
        scope='descriptive/inconclusive performance; actual native setup/ConvexPort-run spans, not isolated LP or end-to-end MPC latency',
        input_inventory_sha256=digest(root/'SHA256SUMS')))
    if 'filtered_t2' not in policies:raise ValueError('no independently verified policy available for figure')
    data=plot(policies['filtered_t2'],output);capture.write(output/'figure-data.json',data)
    capture.write(output/'figure-export.json',dict(figure_data_sha256=digest(output/'figure-data.json'),input_manifest_sha256=digest(root/'SHA256SUMS'),
        images={name:digest(output/name) for name in ('fixed-filter-policy.svg','fixed-filter-policy.png')}))
    rows=[]
    for key,g in groups.items():
        times=g['times_ns'];rows.append(f'<tr><td>{key}</td><td>{g["verified"]}/{g["attempts"]}</td><td>{g.get("exact_virtual_worst_squared","unavailable")}</td><td>{g["variables"]}/{g["rows"]}/{g["nonzeros"]}</td><td>{times.get("native_port_run_ns",{}).get("median","unavailable")}</td></tr>')
    page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MPC07 bounded policy intersection</title><style>body{background:#1e1e2e;color:#cdd6f4;font:16px/1.6 system-ui;max-width:1200px;margin:2rem auto;padding:1rem}a{color:#89b4fa}img{max-width:100%;height:auto}table{display:block;overflow:auto}td,th{padding:.4rem;text-align:left}</style><h1>Bounded causal policy / response intersection</h1><p>Performance verdict: <strong>inconclusive</strong>. These are authored two-state T2/4/8 examples, not author-code reproduction or the full jointly optimized SLS-MPC algorithm. Native HiGHS returns numerical LP witnesses; separate rational reconstruction and exact support replay verify the reported policies. Native LP objective is worst terminal absolute velocity; the original toy quadratic is its square.</p><p>Full-state observation reconstructs only PAST lumped disturbances. Fixed plans, prescribed feedback, ADF and explicit response formulations share continuous controls and the same stated model within each profile. The sigma5/4 problem is a conservative fixed-filter virtual box: its optimum is an upper bound for the physical uncertain-A problem. The physical T2 optimum, physical returned-policy cost and virtual optimum are distinct.</p><img src="fixed-filter-policy.svg" alt="Two-state velocity/lumped-disturbance enclosure and terminal position/velocity set from saved policy"><p>Physical points are uncertainty vertices; no full winning set, recursive feasibility or continuous safety is inferred. <a href="figure-data.json">Exact figure inputs and original physical T2 reference</a>.</p><table><tr><th>Profile</th><th>Verified/attempts</th><th>Exact virtual worst qT²</th><th>LP vars/rows/nnz</th><th>Median native port run (ns)</th></tr>'''+''.join(rows)+'''</table><p>Five alternating repetitions are descriptive. Setup includes parsing/program/registry; port run includes adapter checks. Neither is an isolated LP solve, and batch policy synthesis is not an MPC update latency. A separate Python diagnostic profile does not establish the native limiter. All warmups, native admission/infeasibility probes and process/check outcomes are retained.</p><p><a href="summary.json">Full timings/counts/source identity</a> · <a href="current-rechecks.json">Current independent saved-data checks</a> · <a href="RAW/">Complete raw capture, sources and offline checksum manifest</a>. Read the bundled README for complete matrices, bounds, causal law, oracle proof, fixed-filter induction, solver/license/platform/release limits and residual603 criteria. No API/required dependency/library release or publication claim.</p></html>'''
    (output/'index.html').write_text(page)
    capture.write(output/'input-binding.json',dict(capture_manifest_sha256=digest(root/'SHA256SUMS'),files=hashes,
        current_checker_sha256={name:digest(Path(__file__).with_name(name)) for name in ('report.py','policy.py','capture.py')}))
    files=sorted(p for p in output.rglob('*') if p.is_file())
    (output/'SHA256SUMS').write_text(''.join(f'{digest(p)}  {p.relative_to(output).as_posix()}\n' for p in files))
    return groups


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capture',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();render(a.capture.resolve(),a.output.resolve())
