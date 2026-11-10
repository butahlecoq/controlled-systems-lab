#!/usr/bin/env python3
"""Joint-filter saved captures; existing bridge only, no author code or rebuild."""
import argparse
import cProfile
import hashlib
import io
import json
import os
from pathlib import Path
import pstats
import re
import subprocess
import sys
import time
import capture
import joint_filter as J

ROOT=Path(__file__).resolve().parents[3]
NATIVE='b3978a98a8bfb30e21841466244ed7f78e987886'
SOURCE_PATHS={name:'benchmarks/reporting/mpc07/'+name for name in
              ('PLAN.md','README.md','JOINT-FILTER.md','policy.py','capture.py','report.py','joint_filter.py','joint_capture.py','native-build-receipt.json')}
SOURCE_PATHS.update({'test_mpc07_policy.py':'tests/reporting/test_mpc07_policy.py',
    'test_mpc07_joint_filter.py':'tests/reporting/test_mpc07_joint_filter.py',
    'joint-gain-fixture.json':'tests/reporting/fixtures/mpc07-joint-gain-t08.json',
    'figure_style.py':'scripts/reports/figure_style.py',
    'native-affine_bridge.cpp':'benchmarks/reporting/mpc11/affine_bridge.cpp',
    'native-CMakeLists.txt':'benchmarks/reporting/mpc11/CMakeLists.txt'})


def recheck(folder):
    r=json.loads((folder/'receipt.json').read_text())
    if not capture.coherent_receipt(r):return dict(status='inconclusive-invalid-process-receipt')
    if r['status']!='completed' or r['returncode']!=0:return dict(status='inconclusive-process-outcome')
    return J.check_result(json.loads((folder/'program.json').read_text()),json.loads((folder/'stdout.json').read_text()))


def checked_records(root,repository,hashes):
    env=json.loads((root/'environment.json').read_text())
    revision=env['source_commit']
    if not isinstance(revision,str) or not re.fullmatch('[0-9a-f]{40}',revision) or env['source_status']!='' or \
            env['native_source_commit']!=NATIVE or env['bridge_sha256']!=capture.BRIDGE_SHA:
        raise ValueError('joint source/native identities differ')
    if set(env['source_sha256'])!=set(SOURCE_PATHS):raise ValueError('joint mandatory source inventory differs')
    for name,relative in SOURCE_PATHS.items():
        content=(root/'source'/name).read_bytes();commit=NATIVE if name.startswith('native-') and name!='native-build-receipt.json' else revision
        if hashlib.sha256(content).hexdigest()!=env['source_sha256'][name] or content!=subprocess.check_output(
                ['git','show','--end-of-options',commit+':'+relative],cwd=repository):
            raise ValueError('joint source differs from recorded Git commit: '+name)
    rows=[];policies={};seen=set()
    for folder in sorted((root/'attempts').iterdir()):
        receipt=json.loads((folder/'receipt.json').read_text());saved=json.loads((folder/'check.json').read_text())
        for name,h in saved['bindings'].items():
            if not re.fullmatch('[A-Za-z0-9_.-]+',name) or capture.sha(folder/name)!=h:raise ValueError('joint saved check binding differs')
        try:current=recheck(folder)
        except Exception as error:current=dict(status='incorrect-or-unverified',error_type=type(error).__name__,reason=str(error))
        for key,value in json.loads(json.dumps(current,default=capture.encode)).items():
            if saved.get(key)!=value:raise ValueError('joint current exact disposition differs')
        expected_sigma='fixed5over4' if receipt['policy_class']=='fixed-filter' else 'optimized-diagonal'
        if receipt['sigma']!=expected_sigma or type(receipt['repetition']) is not int:raise ValueError('joint profile label/repetition type differs')
        key=(receipt['repetition'],receipt['horizon'],receipt['policy_class'])
        if key in seen or receipt['warmup']!=(receipt['repetition']==-1):raise ValueError('joint repetition coverage differs')
        seen.add(key);p=json.loads((folder/'program.json').read_text())
        if (receipt['horizon'],receipt['policy_class'])!=(p['profile']['horizon'],p['profile']['policy_class']) or \
                (receipt['variables'],receipt['rows'],receipt['nonzeros'])!=(len(p['variables']),len(p['rows']),len(p['constraints']['values'])):
            raise ValueError('joint actual profile/size association differs')
        native=json.loads((folder/'stdout.json').read_text()) if current['status']=='verified-joint-rational-policy' else {}
        rows.append(dict(path=str(folder.relative_to(root)),receipt=receipt,current_check=json.loads(json.dumps(current,default=capture.encode)),
            native_setup_ns=native.get('setup_ns'),native_port_run_ns=native.get('solve_ns')))
        if receipt['horizon']==2 and current['status']=='verified-joint-rational-policy':policies[receipt['policy_class']]=current
    plan={(rep,n,kind) for rep in range(-1,env['repetitions']) for n in (2,4,8) for kind in J.KINDS}
    if seen!=plan:raise ValueError('joint planned attempt inventory differs')
    return env,rows,policies,hashes


def run(bridge,output):
    if output.exists():raise ValueError('new joint capture required')
    if capture.sha(bridge)!=capture.BRIDGE_SHA:raise ValueError('joint reused native binary differs')
    status=subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True)
    if status:raise ValueError('commit joint source before capture')
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    output.mkdir(parents=True);(output/'attempts').mkdir();(output/'source').mkdir()
    for name,relative in SOURCE_PATHS.items():
        commit=NATIVE if name.startswith('native-') and name!='native-build-receipt.json' else revision
        (output/'source'/name).write_bytes(subprocess.check_output(['git','show','--end-of-options',commit+':'+relative],cwd=ROOT))
    (output/'native-CMakeCache.txt').write_bytes((bridge.parent/'CMakeCache.txt').read_bytes())
    env=dict(schema='csl.mpc07.joint-filter.capture/1',source_commit=revision,source_status=status,native_source_commit=NATIVE,
        source_sha256={p.name:capture.sha(p) for p in (output/'source').iterdir()},bridge_sha256=capture.sha(bridge),
        repetitions=5,python=sys.version,logical_cpus=os.cpu_count(),load_start=os.getloadavg(),
        physical=dict(A_nominal=[[1,1],[0,1]],B=[.5,1],delta_q_bound='1/64',W=[[0,0],[-1,1]],X=[[-64,64],[-16,16]],U=[-1,1],x0=[0,0],u0=0),
        filter='optimized diagonal2x2 positive blocks, positionfloor1/1024; fixed-filter comparator q5/4',
        scope='Chen v3 joint diagonal-filter sufficient counterpart; terminal-only authored cost; no full-filter/uncertainB/recursive-feasibility claim')
    capture.write(output/'environment.json',env)
    index=0
    for rep in range(-1,5):
        for n in (2,4,8):
            order=list(J.KINDS)
            if rep%2:order.reverse()
            for kind in order:
                folder=output/'attempts'/f'{index:04d}';folder.mkdir();index+=1
                start=time.monotonic_ns();p=J.program(n,kind);prepared=time.monotonic_ns()-start
                receipt=capture.attempt(folder,bridge,p);receipt.update(repetition=rep,warmup=rep==-1,horizon=n,policy_class=kind,
                    sigma='fixed5over4' if kind=='fixed-filter' else 'optimized-diagonal',python_prepare_ns=prepared,
                    variables=len(p['variables']),rows=len(p['rows']),nonzeros=len(p['constraints']['values']))
                capture.write(folder/'receipt.json',receipt);start=time.monotonic_ns()
                try:checked=recheck(folder)
                except Exception as error:checked=dict(status='incorrect-or-unverified',error_type=type(error).__name__,reason=str(error))
                checked['independent_check_ns']=time.monotonic_ns()-start
                checked['bindings']={name:capture.sha(folder/name) for name in ('program.json','receipt.json','stdout.json','stderr.txt','process-resource.txt')}
                capture.write(folder/'check.json',checked)
    env['load_end']=os.getloadavg();capture.write(output/'environment.json',env)
    def diagnostic():
        for n in (2,4,8):J.program(n,'joint')
        for folder in sorted((output/'attempts').iterdir())[:12]:recheck(folder)
    profile=cProfile.Profile();profile.runcall(diagnostic);profile.dump_stats(output/'python-diagnostic.prof')
    text=io.StringIO();pstats.Stats(profile,stream=text).sort_stats('cumulative').print_stats(25);(output/'python-diagnostic.txt').write_text(text.getvalue())
    capture.write(output/'profile-scope.json',dict(scope='separate Python joint LP construction/exact filter checking only; native limiter unestablished',performance='inconclusive; no tuning study or ranking'))
    (output/'SHA256SUMS').write_text(''.join(f'{capture.sha(p)}  {p.relative_to(output).as_posix()}\n' for p in sorted(output.rglob('*')) if p.is_file()))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bridge',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();run(a.bridge.resolve(),a.output.resolve())
