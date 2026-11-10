#!/usr/bin/env python3
"""Recheck saved MPC07 data and render a separate report; no algorithm execution."""
from __future__ import annotations
import argparse
from fractions import Fraction as Q
import hashlib
import html
import json
from pathlib import Path
import re
import statistics
import shutil
import sys
import subprocess
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


SOURCE_PATHS={
    'PLAN.md':'benchmarks/reporting/mpc07/PLAN.md',
    'README.md':'benchmarks/reporting/mpc07/README.md',
    'capture.py':'benchmarks/reporting/mpc07/capture.py',
    'policy.py':'benchmarks/reporting/mpc07/policy.py',
    'report.py':'benchmarks/reporting/mpc07/report.py',
    'native-build-receipt.json':'benchmarks/reporting/mpc07/native-build-receipt.json',
    'test_mpc07_policy.py':'tests/reporting/test_mpc07_policy.py',
    'native-affine_bridge.cpp':'benchmarks/reporting/mpc11/affine_bridge.cpp',
    'native-CMakeLists.txt':'benchmarks/reporting/mpc11/CMakeLists.txt',
}
NATIVE_REVISION='b3978a98a8bfb30e21841466244ed7f78e987886'


def authenticate_sources(root,environment,repository):
    revision=environment.get('source_commit');native=environment.get('native_source_commit')
    if not isinstance(revision,str) or not re.fullmatch('[0-9a-f]{40}',revision) or native!=NATIVE_REVISION:
        raise ValueError('source revisions must be full pinned hexadecimal commits')
    if set(environment['source_sha256'])!=set(SOURCE_PATHS):raise ValueError('mandatory source snapshot inventory differs')
    for name,relative in SOURCE_PATHS.items():
        content=(root/'source'/name).read_bytes()
        if hashlib.sha256(content).hexdigest()!=environment['source_sha256'][name]:raise ValueError('source snapshot hash differs')
        commit=NATIVE_REVISION if name in ('native-affine_bridge.cpp','native-CMakeLists.txt') else revision
        committed=subprocess.check_output(['git','show','--end-of-options',commit+':'+relative],cwd=repository)
        if content!=committed:raise ValueError('source snapshot differs from recorded Git commit: '+name)
    native_receipt=json.loads((root/'source/native-build-receipt.json').read_text())
    if native_receipt['source_revision']!=NATIVE_REVISION or native_receipt['bridge_sha256']!=capture.BRIDGE_SHA:
        raise ValueError('reused native source/build receipt differs')


def checked_records(root,repository=capture.ROOT):
    hashes=inventory(root);environment=json.loads((root/'environment.json').read_text())
    if environment.get('schema')=='csl.mpc07.joint-filter.capture/1':
        import joint_capture
        return joint_capture.checked_records(root,repository,hashes)
    if environment.get('schema')!='csl.mpc07.capture/1':raise ValueError('unsupported MPC07 capture schema')
    if environment['bridge_sha256']!=capture.BRIDGE_SHA or environment.get('source_status')!='':
        raise ValueError('capture source/native identity differs')
    authenticate_sources(root,environment,repository)
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
        if status not in ('verified-rational-reconstruction','verified-joint-rational-policy'):continue
        group['verified']+=1;group['exact_virtual_worst_squared']=row['current_check'].get('worst_terminal_squared',row['current_check'].get('virtual_terminal_squared'))
        group.setdefault('virtual_policy_bounds',[]).append(group['exact_virtual_worst_squared'])
        values=dict(python_prepare_ns=r['python_prepare_ns'],whole_process_ns=r['whole_process_ns'],
            native_setup_ns=row['native_setup_ns'],native_port_run_ns=row['native_port_run_ns'])
        if type(values['native_setup_ns']) is not int or type(values['native_port_run_ns']) is not int or values['native_setup_ns']+values['native_port_run_ns']>values['whole_process_ns']:
            raise ValueError('native inclusive spans exceed supervised process duration')
        for name,value in values.items():
            if type(value) is not int or value<0:raise ValueError('invalid measured clock')
            group['samples'].setdefault(name,[]).append(value)
    for group in groups.values():
        bounds=sorted(set(map(Q,group.pop('virtual_policy_bounds',[]))))
        group['virtual_policy_bound_range']=dict(minimum=str(bounds[0]),maximum=str(bounds[-1])) if bounds else None
        group['exact_virtual_worst_squared']=str(bounds[0]) if len(bounds)==1 else None
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


def joint_attainment(records):
    gaps=[]
    for row in records:
        if row['receipt']['policy_class']!='joint' or row['current_check']['status']!='verified-joint-rational-policy':continue
        checked=row['current_check']
        gap=Q(checked['virtual_terminal_squared'])-Q(checked['physical_unrestricted_lower_squared'])
        if gap<0 or gap!=Q(checked['upper_minus_physical_lower_squared']):raise ValueError('incoherent exact physical upper/lower gap')
        gaps.append(gap)
    if not gaps:raise ValueError('no verified joint policies for attainment statement')
    minimum,maximum=min(gaps),max(gaps)
    if maximum==0:
        statement=f'The exact reconstructed physical upper/lower gaps are zero for all {len(gaps)} verified joint policies in this toy. Policy-level attainment follows from the independent lower bound; no general SLS minimax equality is inferred.'
    else:
        statement=f'Verified joint policies include a positive exact gap. Their physical worst-cost upper/lower gaps range from {minimum} to {maximum}. A feasible policy with a positive gap supplies an upper bound; its physical minimax attainment is not established.'
    return dict(verified_policies=len(gaps),minimum_gap=str(minimum),maximum_gap=str(maximum),all_attain_lower=maximum==0,statement=statement)


def render_joint(root,output):
    if output.exists():raise ValueError('joint report must be new')
    env,records,policies,hashes=checked_records(root);groups=metrics(records);attainment=joint_attainment(records)
    if 'joint' not in policies or 'fixed-filter' not in policies:raise ValueError('no exact joint/fixed policies for figure')
    output.mkdir(parents=True);shutil.copytree(root,output/'RAW')
    import matplotlib
    if matplotlib.__version__!='3.11.2':raise ValueError('Matplotlib3.11.2 required')
    matplotlib.use('Agg');import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    sys.path.insert(0,str(capture.ROOT/'scripts/reports'));from figure_style import configure_numeric_axis,STYLE_ID
    joint=policies['joint'];fixed=policies['fixed-filter']
    s=[[Q(v) for v in row] for row in joint['filter']]
    bounds_joint=[Q(v) for v in joint['state_supports'][-1]];bounds_fixed=[Q(v) for v in fixed['state_supports'][-1]]
    effective_M=Q(joint['normalized_policy'][1][1])/s[0][1]
    physical=policy.physical_vertices_two_step([Q(0),Q(0)],[[Q(0),Q(0)],[effective_M,Q(0)]])
    if any(abs(row['terminal'][k])>bounds_joint[k] for row in physical for k in range(2)):raise ValueError('physical plotted vertex escapes joint support box')
    style={'font.family':'DejaVu Sans','svg.hashsalt':'mpc07-joint-filter-v1','figure.facecolor':'#1e1e2e','axes.facecolor':'#1e1e2e',
           'text.color':'#cdd6f4','axes.labelcolor':'#cdd6f4','axes.edgecolor':'#cdd6f4','xtick.color':'#cdd6f4','ytick.color':'#cdd6f4',
           'legend.labelcolor':'#cdd6f4','legend.facecolor':'#1e1e2e'}
    with plt.rc_context(style):
        fig,axes=plt.subplots(1,2,figsize=(12,5),layout='constrained')
        q=[-1.,0.,1.];upper=[65/64,1.,65/64];lower=[-65/64,-1.,-65/64]
        axes[0].add_patch(Rectangle((-1,-1.25),2,2.5,facecolor='#89b4fa',alpha=.25,label='previous fixed filter5/4'))
        height=float(s[1][1]);axes[0].add_patch(Rectangle((-1,-height),2,2*height,fill=False,edgecolor='#f9e2af',linewidth=2,label='selected s1,q='+str(s[1][1])))
        axes[0].fill_between(q,lower,upper,color='#a6e3a1',alpha=.55,label='physical eta1=delta*q1+w1')
        axes[0].set(xlabel='observed stage1 velocity q1',ylabel='lumped disturbance eta1',title='Joint controller-dependent enclosure, T2',xlim=(-1.1,1.1),ylim=(-1.35,1.35))
        for bounds,color,label in [(bounds_fixed,'#89b4fa','fixed-filter support box'),(bounds_joint,'#f9e2af','joint-filter support box')]:
            px,qx=map(float,bounds);axes[1].add_patch(Rectangle((-px,-qx),2*px,2*qx,fill=False,edgecolor=color,linewidth=2,label=label))
        axes[1].scatter([float(row['terminal'][0]) for row in physical],[float(row['terminal'][1]) for row in physical],color='#a6e3a1',label='physical T2 uncertainty vertices')
        axes[1].set(xlabel='terminal position p2',ylabel='terminal velocity q2',title='Actual saved normalized-feedback policies',xlim=(-.9,.9),ylim=(-1.65,1.65));axes[1].set_aspect('equal',adjustable='box')
        for ax in axes:configure_numeric_axis(ax);ax.legend(fontsize=7)
        fig.suptitle('Two-state uncertain-A model; Chen v3 diagonal-filter restriction, not the full-filter author implementation',fontsize=10)
        for extension in ('svg','png'):
            path=output/('joint-filter-policy.'+extension);fig.savefig(path,dpi=160,metadata={'Date':None} if extension=='svg' else None)
            if extension=='svg':path.write_text('\n'.join(line.rstrip() for line in path.read_text().splitlines())+'\n')
        plt.close(fig)
    capture.write(output/'current-rechecks.json',records);capture.write(output/'summary.json',dict(environment=env,groups=groups,
        capture_manifest_sha256=digest(root/'SHA256SUMS'),joint_attainment=attainment,performance='inconclusive; descriptive source scopes and no native limiter/tuning claim'))
    capture.write(output/'figure-data.json',dict(joint_policy=joint,fixed_policy=fixed,position_filter_floor='1/1024',
        physical_T2_optimum='4225/4096',physical_vertices=physical,axis_policy=STYLE_ID,scope='support boxes, not asserted full reachable/winning sets; physical points are extreme samples only'))
    for name in ('JOINT-FILTER.md','README.md'):(output/name).write_bytes((root/'source'/name).read_bytes())
    table=[]
    for key,g in groups.items():
        bounds=g['virtual_policy_bound_range']
        display='unavailable' if bounds is None else (bounds['minimum'] if bounds['minimum']==bounds['maximum'] else bounds['minimum']+' to '+bounds['maximum'])
        table.append(f'<tr><td>{html.escape(key)}</td><td>{g["verified"]}/{g["attempts"]}</td><td>{display}</td><td>{g["variables"]}/{g["rows"]}/{g["nonzeros"]}</td><td>{g["times_ns"].get("native_port_run_ns",{}).get("median","unavailable")}</td></tr>')
    page='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MPC07 joint-filter specialization</title><style>body{font:16px/1.6 system-ui;background:#1e1e2e;color:#cdd6f4;max-width:1200px;margin:2rem auto;padding:1rem}a{color:#89b4fa}img{max-width:100%;height:auto}table{display:block;overflow:auto}td,th{padding:.4rem;text-align:left}</style><h1>Joint diagonal-filter SLS specialization</h1><p>This independently authored profile implements the jointly affine scaled-response identity and controller-dependent uncertainty-overapproximation constraints from Chen v3(24),(26),(36), restricted to block-diagonal positive filters and one uncertain A entry. No author code, full-filter/uncertain-B capability, recursive-feasibility or general causal minimax claim. Physical position disturbance is zero; the virtual position-filter floor1/1024 makes the two-state filter invertible and conservatively enlarges its response set.</p><p>The native LP minimizes a virtual worst-terminal-absolute upper bound, squared for the original toy cost. Exact rational reconstruction checks source, causality, every filter/support row and the physical cost lower bound. $JOINT_ATTAINMENT$ Prescribed-gain and symmetry-optimal zero fixed-plan baselines use the same physical controls/uncertainty. The previous fixed5/4 filter is a separate conservative comparison.</p><img src="joint-filter-policy.svg" alt="Two-state optimized disturbance filter and terminal support-box comparison"><p><a href="JOINT-FILTER.md">Complete equations, proof and information order</a> · <a href="figure-data.json">Exact saved figure inputs</a> · <a href="summary.json">Source, counts and all timing ranges</a> · <a href="current-rechecks.json">Independent checks</a> · <a href="RAW/">Complete raw records/source/CPU/RSS</a>.</p><table><tr><th>Profile</th><th>Verified/attempts</th><th>Exact virtual qT² upper bound</th><th>LP vars/rows/nnz</th><th>Median native port-run ns</th></tr>'+''.join(table)+'</table><p>Performance verdict: inconclusive. One warmup plus five alternating repeats are descriptive; native setup and ConvexPort run include documented parse/registry/adapter checks and are not isolated LP time or MPC-update latency. A separate Python diagnostic does not establish the native limiter. Failed/resource/reconstruction outcomes stay in denominators. No core API, required dependency, native rebuild or library release. Existing HiGHS/Matplotlib qualifications remain. Independent review and root-owned checked publication remain required; this unit does not close603.</p></html>'
    (output/'index.html').write_text(page.replace('$JOINT_ATTAINMENT$',html.escape(attainment['statement'])))
    capture.write(output/'figure-export.json',dict(input_manifest_sha256=digest(root/'SHA256SUMS'),figure_data_sha256=digest(output/'figure-data.json'),
        images={name:digest(output/name) for name in ('joint-filter-policy.svg','joint-filter-policy.png')}))
    (output/'SHA256SUMS').write_text(''.join(f'{digest(p)}  {p.relative_to(output).as_posix()}\n' for p in sorted(output.rglob('*')) if p.is_file()))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capture',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();
    environment=json.loads((a.capture/'environment.json').read_text())
    if environment.get('schema')=='csl.mpc07.joint-filter.capture/1':render_joint(a.capture.resolve(),a.output.resolve())
    else:render(a.capture.resolve(),a.output.resolve())
