"""Initial bounded saved-data/native capture for #604; no performance ranking."""
import argparse
from collections import Counter,defaultdict
import csv
from fractions import Fraction as Q
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
import exact_regions as R

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'benchmarks/reporting/review05'))
from run_horizon_ladder import run_with_resource_receipt


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def plain(value):
    def encode(x):
        if isinstance(x,Q):return str(x)
        raise TypeError(type(x).__name__)
    return json.loads(json.dumps(value,default=encode))
def write(path,value):path.write_text(json.dumps(plain(value),indent=2)+'\n')


def queries(record,output):
    points=set(map(tuple,record['regions']['feasible_vertices']))|{(Q(0),Q(0))}
    for region in record['regions']['regions']:
        vs=region['vertices'];points.add(tuple(sum(p[j] for p in vs)/len(vs) for j in (0,1)))
    lookup={}
    with (output/'unique.csv').open('w') as stream:
        writer=csv.writer(stream);writer.writerow(['id','p_exact','v_exact','u_exact','value_exact','p','v'])
        for i,(p,v) in enumerate(sorted(points)):
            lo=max(-Q(1),-1-p-2*v,(-1-p-3*v)/2);hi=min(Q(1),1-p-2*v,(1-p-3*v)/2)
            u=min(hi,max(lo,-v));value=(p+v)**2+(v+u)**2;key=f'U{i:03}'
            writer.writerow([key,str(p),str(v),str(u),str(value),format(float(p),'.17g'),format(float(v),'.17g')])
            lookup[key]=dict(p=p,v=v,u=u,value=value)
    with (output/'nonunique.csv').open('w') as stream:
        writer=csv.writer(stream);writer.writerow(['id','p_exact','v_exact','u_exact','u1_exact','value_exact','p','v','u','u1'])
        for i,(p,v) in enumerate([(Q(0),Q(-2)),(Q(0),Q(-1)),(Q(0),Q(0)),(Q(0),Q(1)),(Q(0),Q(2))]):
            u=-v/2;key=f'N{i:03}';writer.writerow([key,str(p),str(v),str(u),str(u),'0',float(p),float(v),float(u),float(u)])
            lookup[key]=dict(p=p,v=v,u=u,value=Q(0))
    return lookup


def check_native(rows,lookup):
    counts=Counter();groups=defaultdict(list);tol=Q(1,500000)
    expected={key:0 for key in lookup};seen=set()
    for row in rows:
        q=lookup[row['query_id']];expected[row['query_id']]+=1
        key=(row['query_id'],row['strategy'],row['repetition'])
        if key in seen or row['repetition'] not in range(6) or row['warmup']!=(row['repetition']==0):raise ValueError('native method/repetition duplicated or changed')
        if row['strategy'] not in ('csl.synthesis.reach-back','csl.synthesis.strategy-b','online-condensed-qp'):raise ValueError('unexpected native method')
        seen.add(key)
        counts[(row['strategy'],row['status'])]+=1
        if type(row['elapsed_ns']) is not int or row['elapsed_ns']<0:raise ValueError('invalid measured native interval')
        if row['strategy']=='online-condensed-qp' and row['termination_optimal']:
            u=Q(str(row['input_value']));p,v=q['p'],q['v']
            if row['fixture']=='unique_horizon_1':
                value=(p+v)**2+(v+u)**2
                if abs(u-q['u'])>tol:raise ValueError('actual native first action differs from exact reference')
            else:
                u1=Q(str(row['second_input_value']));value=(v+u+u1)**2
                if abs(u)>1+tol or abs(u1)>1+tol or abs(v+u+u1)>tol:raise ValueError('actual native nonunique history fails')
            if abs(value-Q(str(row['objective_at_primal'])))>tol or abs(value-q['value'])>tol:
                raise ValueError('actual native objective fails independent numerical replay')
        if not row['warmup']:groups[(row['fixture'],row['strategy'],row['status'])].append(row['elapsed_ns'])
    if any(n!=18 for n in expected.values()):raise ValueError('native query/repetition/method inventory differs')
    return dict(status_counts=[dict(strategy=k[0],status=k[1],count=v) for k,v in sorted(counts.items())],
        timings=[dict(fixture=k[0],method=k[1],status=k[2],n=len(v),median_ns=statistics.median(v),min_ns=min(v),max_ns=max(v)) for k,v in sorted(groups.items())],
        assurance='online results are independently replayed numerical witnesses; strategy rows are candidate samples/refusals, not complete-family equality',
        timing_scope='existing C++ client interval includes per-query resolve/prepare/workspace/run and candidate or primal checks; not isolated solver time')


def support_queries(record,output):
    lookup={}
    with (output/'support.csv').open('w') as stream:
        writer=csv.writer(stream);writer.writerow(['query_id','dx','dy','then H row triples'])
        for name,item in record['geometry']['sets'].items():
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,-1),(1,2),(-1,-2)):
                key=f'S{len(lookup):03}';expected=min(dx*p+dy*v for p,v in item['vertices'])
                writer.writerow([key,dx,dy,*[format(float(q),'.17g') for row in item['rows'] for q in row]])
                lookup[key]=dict(set=name,direction=[dx,dy],rows=item['rows'],minimum=expected)
    return lookup


def check_support(rows,lookup):
    counts=Counter();seen=Counter();keys=set();tol=Q(1,500000)
    for row in rows:
        q=lookup[row['query_id']];seen[row['query_id']]+=1
        key=(row['query_id'],row['repetition'])
        if key in keys or row['repetition'] not in range(6) or row['warmup']!=(row['repetition']==0):raise ValueError('support repetition duplicated or changed')
        keys.add(key)
        if row['optimal']:
            p,v=map(lambda x:Q(str(x)),row['primal'])
            if any(a*p+b*v>c+tol for a,b,c in q['rows']) or abs(q['direction'][0]*p+q['direction'][1]*v-q['minimum'])>tol:
                raise ValueError('public LP support differs from exact whole-set reference')
            counts['numerical-support-witness']+=1
        else:counts['inconclusive-native-support']+=1
    if set(seen)!=set(lookup) or any(n!=6 for n in seen.values()):raise ValueError('support query inventory differs')
    return dict(counts=counts,queries=len(lookup),scope='actual registered LPPort; exact H/V reference plus independent numerical primal/support checks; no sampled containment proof',
        timings='prepare includes program/provider/workspace; run includes backend setup/solve/result construction; separate raw intervals, no ranking')


def figures(record,output):
    import matplotlib
    if matplotlib.__version__!='3.11.2':raise ValueError('Matplotlib3.11.2 required')
    matplotlib.use('Agg');import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon
    sys.path.insert(0,str(ROOT/'scripts/reports'));from figure_style import configure_numeric_axis
    fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    for i,region in enumerate(record['regions']['regions']):
        vs=region['vertices']
        axes[0].add_patch(Polygon([[float(x) for x in p] for p in vs],facecolor=plt.get_cmap('tab20')(i),edgecolor='gray',alpha=.5,label=f'R{i+1}'))
        axes[0].text(float(sum(p[0] for p in vs)/len(vs)),float(sum(p[1] for p in vs)/len(vs)),f'R{i+1}',fontsize=7)
    for name,color in [('nominal_pre_T','black'),('T','green')]:
        vs=record['geometry']['sets'][name]['vertices'];vs=vs+vs[:1]
        axes[0].plot([float(p[0]) for p in vs],[float(p[1]) for p in vs],color=color,label=name)
    for name in ['robust_pre_outer','nominal_pre_T','robust_pre_T_robust','robust_pre_inner','T_robust']:
        vs=record['geometry']['sets'][name]['vertices'];vs=vs+vs[:1]
        axes[1].plot([float(p[0]) for p in vs],[float(p[1]) for p in vs],label=name)
    for ax in axes:
        ax.plot([-3,3,3,-3,-3],[-2,-2,2,2,-2],':',color='gray',label='X initial domain')
        ax.set(xlim=(-3.2,3.2),ylim=(-2.2,2.2),xlabel='position p',ylabel='velocity v');ax.set_aspect('equal');configure_numeric_axis(ax);ax.legend(fontsize=7)
    axes[0].set_title('N=1 exact value/action critical regions; terminal-only objective')
    axes[1].set_title('Matched predecessors: exists u, forall w for robust curves')
    fig.suptitle('Initial-state parameter sets; no reachable-set / general winning-set equality')
    fig.savefig(output/'critical-regions.svg',metadata={'Date':None});fig.savefig(output/'critical-regions.png',dpi=150);plt.close(fig)


def capture(driver,receipt,output):
    if output.exists():raise ValueError('new output directory required')
    build=json.loads(receipt.read_text())
    if build['binary_sha256']!=sha(driver) or build['client_source_sha256']!=sha(ROOT/'benchmarks/reporting/mpc08_explicit/mpc08_strategy_comparison.cpp'):
        raise ValueError('native client/build receipt binding differs')
    status=subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True)
    if status:raise ValueError('commit source before capture')
    output.mkdir(parents=True);record=R.build();write(output/'exact-reference.json',record);lookup=queries(record,output);supports=support_queries(record,output)
    environment=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',CSL_HIGHS_INTERNAL_CLOCKS='0')
    manifest=dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),source_status=status,
        platform=platform.platform(),python=sys.version,cpu_info=subprocess.check_output(['lscpu'],text=True),logical_cpus=os.cpu_count(),load_before=os.getloadavg(),binary_sha256=sha(driver),
        source_sha256={n:sha(ROOT/n) for n in ['benchmarks/reporting/mpc08_explicit/exact_regions.py','benchmarks/reporting/mpc08_explicit/capture_exact_regions.py',
            'benchmarks/reporting/mpc08_explicit/explicit_double_integrator.py','benchmarks/reporting/mpc08_explicit/mpc08_strategy_comparison.cpp','benchmarks/reporting/review05/run_horizon_ladder.py']},
        limits=dict(wall_seconds=300,cpu_seconds=300,address_space_bytes=8*1024**3,requested_native_threads=1,
            observation='LP support rows retain actual backend widths; QP/strategy rows do not collect them'),processes=[],claim='initial descriptive capture only; no timing ranking or clean rebuilt-library claim')
    shutil.copy2(receipt,output/'native-build-receipt.json');all_rows=[]
    for name in ('unique','nonunique'):
        command=[str(driver),str((output/(name+'.csv')).resolve())];start=time.perf_counter_ns()
        code,timed_out,stdout,stderr,resources=run_with_resource_receipt(command,300,environment)
        (output/(name+'.stdout.jsonl')).write_bytes(stdout);(output/(name+'.stderr.txt')).write_bytes(stderr)
        process=dict(profile=name,command=command,return_code=code,timed_out=timed_out,whole_process_ns=time.perf_counter_ns()-start,resources=resources,
            stdout_sha256=hashlib.sha256(stdout).hexdigest(),stderr_sha256=hashlib.sha256(stderr).hexdigest())
        manifest['processes'].append(process)
        if code==0 and not timed_out:all_rows.extend(json.loads(line) for line in stdout.splitlines())
    manifest['load_after']=os.getloadavg();write(output/'manifest.json',manifest)
    if all(p['return_code']==0 and not p['timed_out'] for p in manifest['processes']):summary=check_native(all_rows,lookup)
    else:summary=dict(status='inconclusive-process',scope='retained partial stdout/stderr; no complete capture inference')
    command=[str(driver),'--support',str((output/'support.csv').resolve())];start=time.perf_counter_ns()
    code,timed_out,stdout,stderr,resources=run_with_resource_receipt(command,300,environment)
    (output/'support.stdout.jsonl').write_bytes(stdout);(output/'support.stderr.txt').write_bytes(stderr)
    manifest['processes'].append(dict(profile='set-support-LP',command=command,return_code=code,timed_out=timed_out,
        whole_process_ns=time.perf_counter_ns()-start,resources=resources,stdout_sha256=hashlib.sha256(stdout).hexdigest(),stderr_sha256=hashlib.sha256(stderr).hexdigest()))
    write(output/'manifest.json',manifest)
    summary['lp_support']=check_support([json.loads(line) for line in stdout.splitlines()],supports) if code==0 and not timed_out else dict(status='inconclusive-process')
    write(output/'native-summary.json',summary);figures(record,output)
    summary_html=html.escape(json.dumps(plain(dict(exact_checks=record['checks'],fiber_growth=record['fibers']['rows'],native=summary)),indent=2))
    (output/'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>MPC08 exact region/predecessor first capture</title><body><h1>Exact regions, matched predecessor quantifiers and optimizer fibers</h1><p>Performance verdict: inconclusive. Fixture-specific exact reference proofs are separate from numerical public solver observations and candidate samples. No MPT3 execution, general winning-set or original-quadratic registered complete-family claim.</p><img src="critical-regions.svg" style="max-width:100%" alt="Exact critical regions, terminal sets and matched nominal/robust predecessors"><p><a href="exact-reference.json">Exact H/V rows and certificates</a> · <a href="manifest.json">Capture provenance/resources</a> · <a href="native-build-receipt.json">Reused-library/native client provenance</a></p><details><summary>Checks, output-growth refusals and native outcomes</summary><pre>'+summary_html+'</pre></details></body></html>')
    (output/'SHA256SUMS').write_text(''.join(sha(p)+'  '+p.relative_to(output).as_posix()+'\n' for p in sorted(output.rglob('*')) if p.is_file()))
    print(json.dumps(dict(output=str(output),exact=plain(record['checks']),native=summary['status_counts'] if 'status_counts' in summary else summary)))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--driver',type=Path,required=True);parser.add_argument('--build-receipt',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();capture(args.driver.resolve(),args.build_receipt.resolve(),args.output)
