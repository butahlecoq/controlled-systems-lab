"""Independent rational physical/policy replay and strict captured-source binding."""
import argparse
from collections import Counter
from fractions import Fraction as Q
import hashlib
import json
import math
from pathlib import Path,PurePosixPath
import re
import statistics
import subprocess
from benchmarks.reporting.mpc07 import policy,joint_filter
from benchmarks.reporting.mpc07.online.inputs import select,encoded,digest

ROOT=Path(__file__).resolve().parents[4]
ONLINE_PREFIX='benchmarks/reporting/mpc07/online/'
# Schema1's actual0524 capture includes all five algorithms/readers plus profiles.
MINIMUM_ONLINE_SOURCES=frozenset(ONLINE_PREFIX+name for name in
    ('controller.py','capture.py','check.py','inputs.py','figures.py','profiles.json'))


def load(path):
    def reject(value):raise ValueError('nonfinite JSON evidence')
    return json.loads(path.read_text(),parse_constant=reject)


def inventory(folder):
    result={}
    for p in sorted(folder.rglob('*')):
        if p.is_symlink():raise ValueError('capture symlink')
        if p.is_file() and p!=folder/'SHA256SUMS':result[p.relative_to(folder).as_posix()]=digest(p.read_bytes())
    return result


def authenticated(folder):
    actual=inventory(folder);expected={}
    for line in (folder/'SHA256SUMS').read_text().splitlines():
        m=re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9_./-]+)',line)
        if not m or m[2] in expected or '..' in PurePosixPath(m[2]).parts or PurePosixPath(m[2]).is_absolute():raise ValueError('capture checksum syntax')
        expected[m[2]]=m[1]
    if actual!=expected:raise ValueError('capture inventory differs')
    env=load(folder/'environment.json');revision=env['source_revision']
    if not isinstance(revision,str) or not re.fullmatch('[0-9a-f]{40}',revision):raise ValueError('full source revision required')
    prefix='benchmarks/reporting/mpc07/'
    names=subprocess.check_output(['git','ls-tree','-r','--name-only',revision,'--',prefix],cwd=ROOT,text=True).splitlines()
    required={n for n in names if (n.startswith(prefix+'online/') and n.endswith(('.py','/profiles.json'))) or (n.startswith(prefix) and n.count('/')==3 and n.endswith('.py'))}
    required.add('scripts/reports/stage_mpc07_comparison.py')
    if not MINIMUM_ONLINE_SOURCES<=required:raise ValueError('capture revision lacks mandatory online source profile')
    if set(env['source_sha256'])!=required:raise ValueError('mandatory captured source inventory differs')
    if {n.removeprefix('source/') for n in actual if n.startswith('source/')}!=required:raise ValueError('copied source inventory differs')
    for name,checksum in env['source_sha256'].items():
        data=(folder/'source'/name).read_bytes()
        if digest(data)!=checksum or data!=subprocess.check_output(['git','show','--end-of-options',revision+':'+name],cwd=ROOT):raise ValueError('source differs from recorded commit')
    if (folder/'inputs.json').read_bytes()!=(folder/'source'/ONLINE_PREFIX/'profiles.json').read_bytes():raise ValueError('captured committed input bytes differ')
    inputs=load(folder/'inputs.json')
    if digest((folder/'inputs.json').read_bytes())!=env['input_sha256'] or inputs!=select():raise ValueError('selected policy/source input binding differs')
    return env,inputs,actual


def close(value,exact,tolerance):
    return type(value) in (int,float) and math.isfinite(value) and math.isclose(value,float(exact),abs_tol=tolerance['absolute'],rel_tol=tolerance['relative'])


def same_vector(value,exact,tolerance):
    return isinstance(value,(list,tuple)) and len(value)==len(exact) and all(close(x,y,tolerance) for x,y in zip(value,exact))


def verify_policy(profile):
    p=profile['policy'];n=profile['horizon']
    if profile['encoding']=='past-eta':
        checked=policy.check_policy(n,Q(profile['sigma']),profile['policy_class'],p['policy_v'],p['policy_M'])
        if Q(p['worst_terminal_squared'])!=checked['worst_terminal_squared']:raise ValueError('original exact policy bound differs')
        return checked['worst_terminal_squared']
    checked=joint_filter.check_policy(n,profile['policy_class'],p['filter'],p['normalized_policy'])
    if Q(p['virtual_terminal_squared'])!=checked['virtual_terminal_squared']:raise ValueError('joint exact policy bound differs')
    return checked['virtual_terminal_squared']


def replay(profile,record,tolerance):
    n=profile['horizon'];p=profile['policy'];state=[Q(0),Q(0)];previous=None;last=None;eta=[];zeta=[]
    if record['status']!='completed':return dict(status='retained-failed-episode',completed_stages=sum('next_state'in r for r in record.get('steps',[])))
    if len(record['steps'])!=n or record['warmup']!=(record['repetition']==-1):raise ValueError('episode inventory/warmup differs')
    bound=verify_policy(profile);maximum=0.
    durations=[]
    for t,row in enumerate(record['steps']):
        if row['stage']!=t or not same_vector(row['observation'],state,tolerance):raise ValueError('observed physical state differs from exact replay')
        residual=None;innovation=None
        if previous is not None:
            residual=[state[0]-previous[0]-previous[1]-last/2,state[1]-previous[1]-last]
            if profile['encoding']=='past-eta':eta.append(residual[1])
            else:
                innovation=[residual[k]/Q(p['filter'][t-1][k]) for k in range(2)];zeta.extend(innovation)
        for field,values in [('past_residual',residual),('past_innovation',innovation)]:
            if (row[field] is None)!=(values is None) or (values is not None and not same_vector(row[field],values,tolerance)):raise ValueError('past residual/innovation reconstruction differs')
        control=(Q(p['policy_v'][t])+sum(Q(p['policy_M'][t][j])*v for j,v in enumerate(eta))) if profile['encoding']=='past-eta' else sum(Q(p['normalized_policy'][t][j])*v for j,v in enumerate(zeta))
        if not close(row['control'],control,tolerance):raise ValueError('action differs from exact causal policy')
        sign=1 if record['family']=='positive' or t%2==0 else -1;delta=Q(profile['epsilon']);w=Q(sign)
        if row['delta']!=float(delta) or row['w']!=float(w):raise ValueError('physical uncertainty trace differs')
        previous=list(state);last=control;state=[state[0]+state[1]+control/2,(1+delta)*state[1]+control+w]
        if not same_vector(row['next_state'],state,tolerance):raise ValueError('returned action was not consumed by original plant')
        # Also replay the actual binary64 action/state through the literal plant equation.
        observed=row['observation'];used=row['control']
        actual=[observed[0]+observed[1]+used/2,(1+row['delta'])*observed[1]+used+row['w']]
        if row['next_state']!=actual:raise ValueError('binary64 plant/action association differs')
        if abs(control)>1 or abs(state[0])>64 or abs(state[1])>16:raise ValueError('exact physical policy bound violated')
        if abs(used)>1+tolerance['absolute'] or any(abs(x)>b+tolerance['absolute'] for x,b in zip(row['next_state'],(64,16))):raise ValueError('binary64 bound violated')
        maximum=max(maximum,max(abs(x-float(y)) for x,y in zip(row['next_state'],state)),abs(used-float(control)))
        for key in ('query_ns','residual_update_ns'):
            if type(row[key])is not int or row[key]<0:raise ValueError('invalid integer phase clock')
            durations.append(row[key])
    if not close(record['terminal_cost'],state[1]**2,tolerance) or state[1]**2>bound:raise ValueError('original terminal cost/bound differs')
    if type(record['preparation_ns'])is not int or record['preparation_ns']<0 or type(record['episode_ns'])is not int or sum(durations)+record['preparation_ns']>record['episode_ns']:raise ValueError('nested phase clocks exceed episode')
    return dict(status='verified-numerical-evaluation',stages=n,exact_terminal_cost=str(state[1]**2),exact_policy_upper_bound=str(bound),maximum_absolute_action_state_error=maximum)


def reader_identity():
    from benchmarks.reporting.mpc07.online.capture import source_files
    files=source_files();revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if not re.fullmatch('[0-9a-f]{40}',revision):raise ValueError('full checker revision required')
    for name,data in files.items():
        if data!=subprocess.check_output(['git','show','--end-of-options',revision+':'+name],cwd=ROOT):raise ValueError('uncommitted checking source')
    return revision,{name:digest(data) for name,data in files.items()}


def checked_verification(folder,path):
    receipt=load(path);revision=receipt.get('checking_revision')
    if not isinstance(revision,str) or not re.fullmatch('[0-9a-f]{40}',revision):raise ValueError('full checking revision required')
    _,current=reader_identity()
    if receipt.get('checking_sources')!=current:raise ValueError('mandatory checking source binding differs')
    for name,checksum in current.items():
        if digest(subprocess.check_output(['git','show','--end-of-options',revision+':'+name],cwd=ROOT))!=checksum:raise ValueError('checker differs from recorded Git source')
    rebuilt=check(folder)
    if {k:v for k,v in rebuilt.items() if k!='checking_revision'}!={k:v for k,v in receipt.items() if k!='checking_revision'}:raise ValueError('verification differs from independent saved replay')
    return receipt


def check(folder):
    env,inputs,hashes=authenticated(folder);profiles={p['id']:p for p in inputs['profiles']};reports=[];expected=[]
    for rep in range(-1,inputs['measured_repetitions']):
        order=[(p['id'],f) for p in inputs['profiles'] for f in inputs['trace_families']]
        if rep%2:order.reverse()
        expected.extend((name,f,rep) for name,f in order)
    for arm in ('measured','profiled'):
        process=load(folder/arm/'process.json')
        for name,key in [('stdout.jsonl','stdout_sha256'),('stderr.txt','stderr_sha256')]:
            if digest((folder/arm/name).read_bytes())!=process[key]:raise ValueError('worker stream binding differs')
        lines=(folder/arm/'stdout.jsonl').read_text().splitlines()
        if process['status']!='completed' or process['return_code']!=0:
            reports.append(dict(arm=arm,status='inconclusive-process',process=process,retained_lines=len(lines)));continue
        records=[json.loads(line) for line in lines]
        if [(r['profile'],r['family'],r['repetition']) for r in records]!=expected:raise ValueError('complete scheduled episode inventory differs')
        checks=[replay(profiles[r['profile']],r,inputs['tolerance']) for r in records]
        if sum(r['episode_ns'] for r in records)>process['whole_process_ns']:raise ValueError('episode clocks exceed process')
        reports.append(dict(arm=arm,status='checked',episodes=len(records),stages=sum(c.get('stages',0) for c in checks),outcomes=dict(Counter(c['status'] for c in checks)),maximum_absolute_action_state_error=max((c.get('maximum_absolute_action_state_error',0) for c in checks),default=0)))
    process=load(folder/'measured/process.json')
    measured=[json.loads(line) for line in (folder/'measured/stdout.jsonl').read_text().splitlines()] if process['status']=='completed' and process['return_code']==0 else []
    groups=[]
    def stats(values):return dict(count=len(values),minimum_ns=min(values),median_ns=statistics.median(values),maximum_ns=max(values),sum_ns=sum(values)) if values else None
    for name,p in profiles.items():
        for family in inputs['trace_families']:
            rows=[r for r in measured if r['profile']==name and r['family']==family and not r['warmup']];completed=[r for r in rows if r['status']=='completed']
            groups.append(dict(profile=name,family=family,attempts=len(rows),completed=len(completed),preparation=stats([r['preparation_ns'] for r in completed]),episode=stats([r['episode_ns'] for r in completed]),query=stats([s['query_ns'] for r in completed for s in r['steps']]),initial_observation=stats([r['steps'][0]['residual_update_ns'] for r in completed]),past_residual_update=stats([s['residual_update_ns'] for r in completed for s in r['steps'][1:]])))
    if inventory(folder)!=hashes:raise ValueError('capture changed during check')
    checking_revision,checking_sources=reader_identity()
    return dict(schema='csl.mpc07.online-check/1',checking_revision=checking_revision,checking_sources=checking_sources,status='checked' if all(r['status']=='checked' and set(r.get('outcomes',{}))=={'verified-numerical-evaluation'} for r in reports) else 'inconclusive',input_files=hashes,source_revision=env['source_revision'],profiles=len(profiles),scheduled_episodes=len(expected),scheduled_stages=sum(profiles[n]['horizon'] for n,f,r in expected),reports=reports,groups=groups,tolerance=inputs['tolerance'],verdict='initial configured Python feedback evaluation costs; no comparative winner, real-time bound or LP/MPC-replanning latency',scope='exact stored rational policy/source/bound replay compared to binary64 observations/actions; physical traces are samples, not new robustness proofs')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--capture',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('new reading receipt required')
    a.output.write_bytes(encoded(check(a.capture.resolve())))
