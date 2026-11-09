"""Save/check bounded quadratic horizon cells and endpoint-reduced native families."""
import argparse
from fractions import Fraction as Q
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time
import horizon_regions as H
import capture_exact_regions as C

SOURCE_FILES=['benchmarks/reporting/mpc08_explicit/'+name for name in
              ('capture_horizon_regions.py','horizon_regions.py','exact_regions.py','explicit_double_integrator.py','mpc08_strategy_comparison.cpp','capture_exact_regions.py')]+['scripts/reports/figure_style.py','benchmarks/reporting/review05/run_horizon_ladder.py','benchmarks/reporting/review05/highs_clock_events.py']


def queries():
    return 'id,N,p,v,zp,zv\n'+''.join(f'N{n}-p{p},{n},{p},0,0,0\n' for n in (2,4,8) for p in (0,1))


def normalized(rows,bounds,equality):
    result=set()
    for row,bound in zip(rows,bounds,strict=True):
        form=list(map(Q,row))+[Q(bound)]
        first=next((x for x in form[:-1] if x),None)
        if first is None:
            if (equality and form[-1]!=0) or (not equality and form[-1]<0):raise ValueError('contradictory native row')
            continue
        factor=first if equality else abs(first)
        result.add(tuple(x/factor for x in form))
    return result


def expected_relation(n,p):
    width=2*(n+1)+n;inequalities=[];upper=[];equalities=[];values=[]
    def eq(coefficients,value):
        row=[0]*width
        for index,coefficient in coefficients.items():row[index]=coefficient
        equalities.append(row);values.append(value)
    eq({0:1},p);eq({1:1},0);eq({2*n:1},0);eq({2*n+1:1},0)
    for t in range(n):
        eq({2*(t+1):1,2*t:-1,2*t+1:-1},0)
        eq({2*(t+1)+1:1,2*t+1:-1,2*(n+1)+t:-1},0)
        for sign in (-1,1):
            row=[0]*width;row[2*(n+1)+t]=sign;inequalities.append(row);upper.append(1)
    return normalized(inequalities,upper,False),normalized(equalities,values,True)


def check_native(rows):
    seen=set();counts={};samples={}
    for row in rows:
        n=row['horizon'];p=int(row['query_id'].split('-p')[-1]);original=row['original_quadratic'];rep=row['repetition']
        if type(n) is not int or n not in (2,4,8) or p not in (0,1) or type(original) is not bool or type(rep) is not int or rep not in range(6):raise ValueError('unsupported native query')
        key=(n,p,original,rep)
        if key in seen or row['query_id']!=f'N{n}-p{p}' or row['warmup']!=(rep==0):raise ValueError('native query/repetition binding differs')
        seen.add(key)
        if type(row['elapsed_ns']) is not int or row['elapsed_ns']<0:raise ValueError('invalid native interval')
        if original:
            if row['complete'] or row['registry_verified'] or 'exact family prepare failed' not in row['error']:raise ValueError('quadratic request not explicitly refused')
            status='unsupported-original-quadratic-profile'
        elif row['complete'] and row['registry_verified']:
            if row['termination']!=0 or row['outcome']!=0 or row['error']:raise ValueError('unsuccessful native process claims complete family')
            actual=normalized(row['inequalities'],row['upper_bounds'],False),normalized(row['equalities'],row['equality_values'],True)
            if actual!=expected_relation(n,p):raise ValueError('complete native H relation differs from full expected control/history fiber')
            status='verified-complete-reduced-linear-family'
        else:
            if row['complete'] or row['registry_verified'] or row['termination']!=3 or not row['stop']:raise ValueError('unqualified incomplete native outcome')
            status='resource-inconclusive-reduced-family'
        counts[(n,status)]=counts.get((n,status),0)+1
        if rep:samples.setdefault((n,status),[]).append(row['elapsed_ns'])
    expected={(n,p,original,rep) for n in (2,4,8) for p in (0,1) for original in (True,False) for rep in range(6)}
    if seen!=expected:raise ValueError('native attempt inventory differs')
    return dict(counts=[dict(horizon=n,status=s,count=count) for (n,s),count in sorted(counts.items())],
                measured_intervals_ns=[dict(horizon=n,status=s,samples=v) for (n,s),v in sorted(samples.items())],
                scope='exact reduced relation equality at six dyadic parameters only; quadratic profile explicitly unsupported; no general quadratic CSL verifier or timing ranking')


def figure(records,output):
    import matplotlib
    if matplotlib.__version__!='3.11.2':raise ValueError('Matplotlib3.11.2 required')
    matplotlib.use('Agg');import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon
    sys.path.insert(0,str(C.ROOT/'scripts/reports'));from figure_style import configure_numeric_axis
    fig,axes=plt.subplots(1,3,figsize=(15,5),layout='constrained')
    for ax,record in zip(axes,records,strict=True):
        for i,cell in enumerate(record['cells']):
            vs=cell['vertices'];ax.add_patch(Polygon([[float(x) for x in v] for v in vs],alpha=.5,facecolor=plt.get_cmap('tab20')(i),edgecolor='black'))
            center=[sum(v[k] for v in vs)/len(vs) for k in (0,1)];ax.text(*map(float,center),str(i+1),ha='center')
        ax.set(xlim=(-3.2,3.2),ylim=(-2.2,2.2),xlabel='initial position p',ylabel='initial velocity v',title=f"N={record['horizon']}: {len(record['cells'])} endpoint-map cells")
        ax.set_aspect('equal');configure_numeric_axis(ax)
    fig.suptitle('Matched terminal-only quadratic and terminal T; intermediate states unconstrained\nUnique optimal endpoint; full control family is a box slice, not one selected trajectory')
    for ext in ('svg','png'):fig.savefig(output/('horizon-regions.'+ext),dpi=150,metadata={'Date':None} if ext=='svg' else None)
    plt.close(fig)


def capture(driver,receipt,output):
    if output.exists():raise ValueError('new output directory required')
    status=subprocess.check_output(['git','status','--porcelain'],cwd=C.ROOT,text=True)
    if status:raise ValueError('clean committed source required')
    build=json.loads(receipt.read_text())
    if C.sha(driver)!=build['binary_sha256'] or C.sha(C.ROOT/SOURCE_FILES[4])!=build['client_source_sha256']:raise ValueError('native binary/client mismatch')
    output.mkdir(parents=True);records=[H.produce(n) for n in (2,4,8)];checks=[H.check(record) for record in records]
    C.write(output/'reference.json',dict(records=records,checks=checks));(output/'queries.csv').write_text(queries());(output/'native-build-receipt.json').write_bytes(receipt.read_bytes())
    command=[str(driver.resolve()),'--horizon-family',str((output/'queries.csv').resolve())]
    environment=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    start=time.perf_counter_ns();rc,stopped,stdout,stderr,resources=C.run_with_resource_receipt(command,300,environment)
    (output/'stdout.jsonl').write_bytes(stdout);(output/'stderr.txt').write_bytes(stderr)
    native=check_native([json.loads(line) for line in stdout.splitlines()]) if rc==0 and not stopped else dict(status='inconclusive-process')
    C.write(output/'summary.json',dict(exact=checks,native=native,performance='inconclusive; descriptive whole per-request native intervals, no ranking'))
    manifest=dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=C.ROOT,text=True).strip(),source_status=status,
        source_sha256={name:C.sha(C.ROOT/name) for name in SOURCE_FILES},binary_sha256=C.sha(driver),
        process=dict(command=command,return_code=rc,timed_out=stopped,whole_process_ns=time.perf_counter_ns()-start,resources=resources),
        boundary='native widths8/14/26 below32; row/operation limits may still refuse; static libraries reused with actual receipt')
    C.write(output/'manifest.json',manifest);figure(records,output)
    (output/'SHA256SUMS').write_text(''.join(C.sha(p)+'  '+p.name+'\n' for p in sorted(output.iterdir()) if p.is_file() and p.name!='SHA256SUMS'))
    return manifest


def recheck(output):
    if output.is_symlink() or any(p.is_symlink() for p in output.rglob('*')):raise ValueError('symlink artifact')
    files={p.name:p.read_bytes() for p in output.iterdir() if p.is_file()}
    expected={}
    for line in files['SHA256SUMS'].decode().splitlines():
        checksum,name=line.split('  ',1)
        if not re.fullmatch('[0-9a-f]{64}',checksum) or not re.fullmatch('[A-Za-z0-9_.-]+',name) or name in expected:raise ValueError('unsafe/duplicate inventory')
        expected[name]=checksum
    if expected!={n:hashlib.sha256(b).hexdigest() for n,b in files.items() if n!='SHA256SUMS'}:raise ValueError('inventory differs')
    manifest=json.loads(files['manifest.json']);revision=manifest['source_commit']
    if not re.fullmatch('[0-9a-f]{40}',revision) or manifest['source_status']!='' or set(manifest['source_sha256'])!=set(SOURCE_FILES):raise ValueError('source identity/inventory differs')
    for name,checksum in manifest['source_sha256'].items():
        data=subprocess.check_output(['git','show','--end-of-options',revision+':'+name],cwd=C.ROOT)
        if hashlib.sha256(data).hexdigest()!=checksum:raise ValueError('source differs from committed capture')
    build=json.loads(files['native-build-receipt.json'])
    if build['binary_sha256']!=manifest['binary_sha256'] or build['client_source_sha256']!=manifest['source_sha256'][SOURCE_FILES[4]]:raise ValueError('native client/source binding differs')
    if files['queries.csv'].decode()!=queries():raise ValueError('native inputs differ from exact dyadic reference')
    def decode(value):
        if isinstance(value,str) and re.fullmatch(r'-?[0-9]+(?:/[0-9]+)?',value):return Q(value)
        if isinstance(value,list):return list(map(decode,value))
        if isinstance(value,dict):return {k:decode(v) for k,v in value.items()}
        return value
    reference=decode(json.loads(files['reference.json']))
    if [record['horizon'] for record in reference['records']]!=[2,4,8]:raise ValueError('reference horizon inventory differs')
    checks=[H.check(record) for record in reference['records']]
    if C.plain(checks)!=C.plain(reference['checks']):raise ValueError('saved exact checks differ')
    process=manifest['process']
    if process['return_code']!=0 or process['timed_out'] is not False:return dict(status='inconclusive-process',exact=C.plain(checks))
    native=check_native([json.loads(line) for line in files['stdout.jsonl'].splitlines()])
    summary=json.loads(files['summary.json'])
    if C.plain(checks)!=summary['exact'] or native!=summary['native']:raise ValueError('saved native/reference summary differs')
    return dict(status='checked',exact=C.plain(checks),native=native)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--driver',type=Path);p.add_argument('--build-receipt',type=Path);p.add_argument('--output',type=Path);p.add_argument('--recheck',type=Path);a=p.parse_args()
    if a.recheck:print(json.dumps(recheck(a.recheck)))
    elif a.driver and a.build_receipt and a.output:print(json.dumps(capture(a.driver,a.build_receipt,a.output)))
    else:p.error('supply --recheck or all capture arguments')
