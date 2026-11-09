#!/usr/bin/env python3
"""Bounded actual Strategy B build-phase observations; no strategy ranking."""
import argparse
from collections import defaultdict,Counter
import hashlib
import html
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import time
from run_horizon_ladder import run_with_resource_receipt
from check_build_phases import check_phases
from render_family_query import bound_receipt

SIDE='csl.synthesis.strategy-b'
FILES=[f'{name}-t{t:02}.json' for name in ('horizon01','family-query-flat') for t in (2,4,8)]

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def summarize(bundle):
    checks=json.loads((bundle/'checks.json').read_text());checked={x['attempt']:x for x in checks['attempts']};rows=[];groups=defaultdict(list)
    for path in sorted((bundle/'attempts').glob('*/receipt.json')):
        key=str(path.parent.relative_to(bundle));check=checked[key];receipt=bound_receipt(bundle,path,check)
        phase={'status':'inconclusive-process-stop'};record=None
        if receipt['returncode']==0 and not receipt['timed_out']:
            try:
                record=json.loads((path.parent/'stdout.txt').read_bytes());phase=check_phases(record)
            except (KeyError,ValueError,TypeError) as error:phase={'status':'incorrect','reason':str(error)}
        rows.append({'attempt':key,'mathematical_check':check['status'],'phase_check':phase})
        if check['status']!='verified' or phase['status']=='incorrect' or receipt['warmup'] or receipt.get('refusal_probe'):continue
        groups[(record['fixture'],record['horizon'],receipt['mode'])].append((record,receipt,phase))
    summaries=[]
    for key,values in sorted(groups.items()):
        row={'fixture':key[0],'horizon':key[1],'collector':key[2],'n':len(values)}
        for field in ('registered_synthesis_ns','selector_ns'):
            data=[x[0][field] for x in values];row[field]={'median':statistics.median(data),'min':min(data),'max':max(data)}
        wall=[x[1]['process_wall_ns'] for x in values];row['process_wall_ns']={'median':statistics.median(wall),'min':min(wall),'max':max(wall)}
        if key[2]=='on':
            for field in ('build_ticks','joint_h_assembly_ticks','objective_lift_ticks','program_freeze_ticks','build_residual_ticks'):
                data=[x[2][field]*x[0]['synthesis_timing']['period_numerator']/x[0]['synthesis_timing']['period_denominator']*1e9 for x in values]
                row[field.replace('_ticks','_ns')]={'median':statistics.median(data),'min':min(data),'max':max(data)}
        summaries.append(row)
    result={'schema':'csl.review05.build-phases/1','attempts':rows,'groups':summaries,
        'mathematical_statuses':dict(Counter(x['mathematical_check'] for x in rows)),
        'phase_statuses':dict(Counter(x['phase_check']['status'] for x in rows)),
        'claim':'initial descriptive bounded observations only; no ranking, isolated verifier time or universal scaling claim',
        'residual_scope':'admission/capacity checks, identity/map/result construction, observer lookup/closure overhead and other unmeasured build gaps'}
    (bundle/'phase-summary.json').write_text(json.dumps(result,indent=2)+'\n')
    environment=json.loads((bundle/'environment.json').read_text())
    page=['<!doctype html><html lang="en"><meta charset="utf-8"><title>REVIEW-05 actual Strategy B build phases</title>',
        '<style>body{font:16px/1.6 system-ui;background:#1e1e2e;color:#cdd6f4;max-width:1100px;margin:3rem auto;padding:0 1.5rem}h1{color:#a6e3a1}a{color:#89b4fa}table{border-collapse:collapse}td,th{padding:.6rem;border-bottom:1px solid #45475a;text-align:left}</style>',
        '<h1>Actual sparse assembly and program construction</h1>',
        '<p>These bounded initial observations split actual Strategy B sparse H-row assembly, objective lifting and make_linear_program/make_convex_program input copying, validation and immutable snapshots. They introduce no public API or mathematical profile change. No strategy ranking, unique limiter, asymptotic complexity or real-time guarantee is claimed.</p>',
        f'<p>Clean source <a href="https://github.com/butahlecoq/controlled-systems-lab/commit/{environment["source_commit"]}">{environment["source_commit"]}</a>. <a href="phase-summary.json">Full distributions and statuses</a>; <a href="checks.json">independent family/query replay</a>; <a href="environment.json">provenance and resources</a>; <a href="attempts/">all raw attempts</a>. Mathematical statuses: {html.escape(str(result["mathematical_statuses"]))}.</p>',
        '<p>Scalar plants remain x[t+1]=x[t]+u[t], x[0]=0, 0≤u[t]≤1 at T=2/4/8. HORIZON01 minimizes x[T]; flat-family variants minimize constant zero. The exact fixture-specific checker verifies both optimizer-family inclusions and each retained direction optimum/history. Instrumentation off/on groups use six repetitions plus warmups, fresh processes, one requested backend thread, 300-second CPU/150-second wall/8 GiB address-space limits and a 120-second library deadline. Failure/resource paths stay retained.</p>',
        '<p>Table entries are median [min,max] microseconds from actual planned library scopes. Sparse assembly includes row/bound/lineage construction. Program freeze includes the actual public constructor call and its input copies, validation and immutable snapshots; it is not an isolated numeric::snapshot or native solver timer. Objective lifting is separate. The residual is admission/capacity, identity/map/result, observer overhead and other gaps; child times are not silently assigned to it. Isolated verifier timing and native-clock overhead remain separate issue95 gates. Unit tests cover both LP and convex constructors; these scalar linear-objective captures exercise the LP constructor.</p>',
        '<table><tr><th>Fixture / T</th><th>n</th><th>Whole build µs</th><th>H assembly µs</th><th>Objective lift µs</th><th>Program freeze µs</th><th>Residual µs</th></tr>']
    def fmt(value):return f'{value["median"]/1000:.2f} [{value["min"]/1000:.2f},{value["max"]/1000:.2f}]'
    for row in summaries:
        if row['collector']!='on':continue
        page.append(f'<tr><td>{row["fixture"]} / {row["horizon"]}</td><td>{row["n"]}</td>'+''.join(f'<td>{fmt(row[key])}</td>' for key in ('build_ns','joint_h_assembly_ns','objective_lift_ns','program_freeze_ns','build_residual_ns'))+'</tr>')
    page.append('<p>Collector-mode distributions and process-wall times remain separate in the summary; host load/observer costs prevent interpreting every mode difference as pure overhead. Hard native heap enforcement remains unsupported. Build and reproduce using <a href="source/BUILD-PHASES.md">the saved phase contract</a>. The independently reviewed scalar 2D illustration remains in the preceding <a href="../review05-family-query-20261110-3b98f5b0/index.html">family-query report</a>. This follow-up is not a new control algorithm or Pages deployment; #95 remains open.</p></html>')
    (bundle/'index.html').write_text('\n'.join(page)+'\n')
    files=sorted(p for p in bundle.rglob('*') if p.is_file() and p.name!='SHA256SUMS')
    (bundle/'SHA256SUMS').write_text(''.join(f'{sha(p)}  {p.relative_to(bundle).as_posix()}\n' for p in files))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--driver',required=True,type=Path);parser.add_argument('--build-cache',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    root=Path(__file__).resolve().parents[3];source=Path(__file__).resolve().parent;driver=args.driver.resolve(strict=True)
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    status=subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True)
    if status:parser.error('clean source required')
    if args.output.exists():parser.error('new output path required')
    if 'CMAKE_BUILD_TYPE:STRING=Release' not in args.build_cache.read_text():parser.error('Release build required')
    bundle=args.output;bundle.mkdir(parents=True);(bundle/'attempts').mkdir();(bundle/'scenarios').mkdir();(bundle/'source').mkdir()
    for name in FILES:shutil.copy2(source/'scenarios'/name,bundle/'scenarios'/name)
    for name in ('family_query_ladder.cpp','check_family_query.py','check_build_phases.py','run_build_phases.py','run_horizon_ladder.py','render_family_query.py','scalar_query_oracle.py','BUILD-PHASES.md','build_phase_probe.cmake'):
        shutil.copy2(source/name,bundle/'source'/name)
    shutil.copy2(root/'src/synthesis/strategy_b/direct_joint.cpp',bundle/'source/direct_joint.cpp')
    shutil.copy2(args.build_cache,bundle/'CMakeCache.txt')
    environment={'schema':'csl.review05.build-phase-environment/1','source_commit':revision,'source_status':status,'binary_sha256':sha(driver),
        'platform':platform.platform(),'host':platform.node(),'logical_cpus':os.cpu_count(),'load_before':os.getloadavg(),
        'compiler':subprocess.check_output(['c++','--version'],text=True),'source_sha256':{p.name:sha(p) for p in (bundle/'source').iterdir()},
        'limits':{'cpu_seconds':300,'wall_seconds':150,'address_space_bytes':8*1024**3,'context_deadline_seconds':120,'total_threads':1,'native_heap_enforcement':False}}
    (bundle/'environment.json').write_text(json.dumps(environment,indent=2)+'\n');index=0
    for repetition in range(-1,6):
        for name in FILES[repetition%6:]+FILES[:repetition%6]:
            for mode in (('off','on') if repetition%2==0 else ('on','off')):
                folder=bundle/'attempts'/f'{index:04d}';folder.mkdir();index+=1
                command=[str(driver),str((bundle/'scenarios'/name).resolve()),SIDE,mode];load=os.getloadavg();start=time.perf_counter_ns()
                code,timeout,stdout,stderr,resources=run_with_resource_receipt(command,150)
                wall_ns=time.perf_counter_ns()-start
                (folder/'stdout.txt').write_bytes(stdout);(folder/'stderr.txt').write_bytes(stderr)
                (folder/'receipt.json').write_text(json.dumps({'scenario':name,'strategy':SIDE,'mode':mode,'repetition':repetition,'warmup':repetition==-1,
                    'command':command,'returncode':code,'timed_out':timeout,'process_wall_ns':wall_ns,'load_at_start':load,
                    'resources':resources,'stdout_sha256':sha(folder/'stdout.txt'),'stderr_sha256':sha(folder/'stderr.txt')},indent=2)+'\n')
    for name in (FILES[0],FILES[3]):
        folder=bundle/'attempts'/f'{index:04d}';folder.mkdir();index+=1
        command=[str(driver),str((bundle/'scenarios'/name).resolve()),SIDE,'on','1']
        code,timeout,stdout,stderr,resources=run_with_resource_receipt(command,150)
        (folder/'stdout.txt').write_bytes(stdout);(folder/'stderr.txt').write_bytes(stderr)
        (folder/'receipt.json').write_text(json.dumps({'scenario':name,'strategy':SIDE,'mode':'on','repetition':None,'warmup':False,'refusal_probe':True,
            'command':command,'returncode':code,'timed_out':timeout,'resources':resources,'stdout_sha256':sha(folder/'stdout.txt'),'stderr_sha256':sha(folder/'stderr.txt')},indent=2)+'\n')
    environment['load_after']=os.getloadavg();(bundle/'environment.json').write_text(json.dumps(environment,indent=2)+'\n')
    subprocess.run([sys.executable,str(source/'check_family_query.py'),str(bundle)],check=True)
    result=summarize(bundle);print(json.dumps({'attempts':index,'mathematical_statuses':result['mathematical_statuses'],'phase_statuses':result['phase_statuses']}))
    return int(any(x['phase_check']['status']=='incorrect' or x['mathematical_check']=='incorrect' for x in result['attempts']))

if __name__=='__main__':raise SystemExit(main())
