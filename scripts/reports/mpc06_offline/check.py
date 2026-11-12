"""Strong saved-only source, certificate, native-input and clock verification."""
import argparse
from fractions import Fraction as Q
import json
import math
from pathlib import Path,PurePosixPath
import re
import statistics
import subprocess
from scripts.reports.mpc06_offline import builder,study

ROOT=Path(__file__).resolve().parents[3]

def load(path):
    def reject(value):raise ValueError('nonfinite JSON evidence')
    return json.loads(path.read_bytes(),parse_constant=reject)
def inventory(folder):
    if folder.is_symlink() or not folder.is_dir():raise ValueError('regular capture directory required')
    values={}
    for p in sorted(folder.rglob('*')):
        if p.is_symlink() or not(p.is_file() or p.is_dir()):raise ValueError('unsafe capture file')
        if p.is_file() and p!=folder/'SHA256SUMS':values[p.relative_to(folder).as_posix()]=study.sha(p.read_bytes())
    return values

def authenticated(folder):
    hashes=inventory(folder);expected={}
    for line in (folder/'SHA256SUMS').read_text().splitlines():
        m=re.fullmatch(r'([0-9a-f]{64})  (.+)',line)
        if not m or m[2] in expected or PurePosixPath(m[2]).is_absolute() or '..' in PurePosixPath(m[2]).parts:raise ValueError('invalid capture checksum inventory')
        expected[m[2]]=m[1]
    builder.require(expected==hashes,'capture inventory differs');env=load(folder/'environment.json');revision=env.get('source_revision')
    builder.require(env['schema']=='csl.mpc06.offline-capture/1' and isinstance(revision,str) and re.fullmatch('[0-9a-f]{40}',revision),'invalid capture source identity')
    captured_sources=set(env['source_sha256'])
    builder.require(captured_sources in (set(study.FILES),set(study.HISTORICAL_FILES)),'mandatory captured source inventory differs')
    builder.require({n[7:] for n in hashes if n.startswith('source/')}==captured_sources,'copied source inventory differs')
    for name,checksum in env['source_sha256'].items():
        data=(folder/'source'/name).read_bytes();committed=subprocess.check_output(['git','show','--end-of-options',revision+':'+name],cwd=ROOT)
        builder.require(study.sha(data)==checksum and data==committed,'captured source differs from Git')
    inputs=(folder/'inputs.json').read_bytes();builder.require(study.sha(inputs)==env['input_sha256'] and inputs==(folder/'source/scripts/reports/mpc06_offline/inputs.json').read_bytes(),'committed input bytes differ')
    builder.require(load(folder/'inputs.json')==builder.input_record(),'actual consumed-input ledger differs')
    builder.require(env['limits']==study.LIMITS and type(env['measured_repetitions'])is int and env['measured_repetitions']==5 and type(env['warmup_repetitions'])is int and env['warmup_repetitions']==1,'capture profile differs')
    return env,json.loads(inputs),hashes

def statistics_ns(values):return dict(count=len(values),minimum_ns=min(values),median_ns=statistics.median(values),maximum_ns=max(values),sum_ns=sum(values)) if values else None

def coherent_process(process):
    if process.get('limits')!=study.LIMITS or type(process.get('whole_process_ns'))is not int or not 0<=process['whole_process_ns']<=31*10**9:raise ValueError('process limits/duration differ')
    if type(process.get('timed_out'))is not bool:raise ValueError('missing timeout disposition')
    if process['status']=='completed' and (type(process.get('return_code'))is not int or process['return_code']!=0 or process['timed_out']):raise ValueError('contradictory completed process')
    for name in ('user_cpu_seconds','system_cpu_seconds','peak_rss_kib'):
        value=process.get(name)
        if process['status']=='completed' and (type(value)not in(int,float) or not math.isfinite(value) or value<0):raise ValueError('process resource observation invalid')

def replay_episode(data,row):
    builder.require(type(row['repetition'])is int and type(row['warmup'])is bool and row['warmup']==(row['repetition']==-1),'episode repetition/warmup differs')
    builder.require(type(row['episode_ns'])is int and row['episode_ns']>=0,'invalid episode clock')
    names=('construction_ns','certificate_and_consumer_check_ns','artifact_serialization_ns')
    values=[row.get(name) for name in names]
    builder.require(all(v is None or type(v)is int and v>=0 for v in values),'invalid phase clock')
    builder.require(sum(v for v in values if v is not None)<=row['episode_ns'],'phase clocks exceed episode')
    if row['status']!='completed':return dict(status='retained-failed-construction',failed_phase=row.get('failed_phase'))
    builder.require(all(v is not None for v in values),'missing completed phase')
    body=row['artifact_json'].encode();builder.require(study.sha(body)==row['artifact_sha256'],'serialized artifact binding differs')
    # Decode numeric arrays explicitly; no arbitrary result is regenerated/blessed.
    artifact=json.loads(body)
    for name in ('K','center','h','state_support','terminal'):artifact[name]=list(map(Q,artifact[name]))
    for name in ('F','generators','tightenings'):artifact[name]=[list(map(Q,r)) if name!='tightenings' else tuple(map(Q,r)) for r in artifact[name]]
    artifact['input_support']=Q(artifact['input_support'])
    checked=builder.verify(data,artifact);builder.require(row['verification']==checked,'independent certificate differs')
    builder.require(builder.encoded(artifact)==body,'artifact serialization differs')
    return dict(status='verified',native_input_matches=checked['native_input_matches'])

def reader_identity():
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();builder.require(re.fullmatch('[0-9a-f]{40}',revision),'invalid checking revision')
    values={name:study.sha((ROOT/name).read_bytes()) for name in study.FILES}
    for name,checksum in values.items():builder.require(study.sha(subprocess.check_output(['git','show','--end-of-options',revision+':'+name],cwd=ROOT))==checksum,'uncommitted checking source')
    return revision,values

def check(folder):
    env,data,hashes=authenticated(folder);reports=[];groups={}
    for arm in ('measured','profiled'):
        receipt=load(folder/arm/'process.json');coherent_process(receipt)
        for name,key in [('stdout.jsonl','stdout_sha256'),('stderr.txt','stderr_sha256')]:builder.require(study.sha((folder/arm/name).read_bytes())==receipt[key],'worker stream binding differs')
        lines=(folder/arm/'stdout.jsonl').read_text().splitlines()
        if receipt['status']!='completed':reports.append(dict(arm=arm,status='inconclusive-process',retained_lines=len(lines)));continue
        rows=[json.loads(line) for line in lines];builder.require(len(rows)==7 and rows[0]['kind']=='empty-counter-control','worker record inventory differs')
        control=rows.pop(0);builder.require(control['subtraction_applied']is False,'timer subtraction differs');controls=control['samples_ns'];builder.require(len(controls)==1000 and all(type(v)is int and v>=0 for v in controls),'empty timer control differs')
        builder.require([r['repetition'] for r in rows]==list(range(-1,5)) and all(r['kind']=='episode' for r in rows),'scheduled work differs')
        checked=[replay_episode(data,r) for r in rows];builder.require(sum(r['episode_ns'] for r in rows)<=receipt['whole_process_ns'],'episodes exceed process')
        reports.append(dict(arm=arm,status='verified' if all(r['status']=='verified' for r in checked) else 'inconclusive-episode',attempts=len(rows),verified=sum(r['status']=='verified' for r in checked),counter_control=statistics_ns(controls)))
        if arm=='measured':
            completed=[r for r in rows if not r['warmup'] and r['status']=='completed']
            groups={name:statistics_ns([r[name] for r in completed]) for name in ('construction_ns','certificate_and_consumer_check_ns','artifact_serialization_ns','episode_ns')}
    builder.require(inventory(folder)==hashes,'capture changed while checking');revision,sources=reader_identity()
    return dict(schema='csl.mpc06.offline-check/1',status='verified' if len(reports)==2 and all(r['status']=='verified' for r in reports) else 'inconclusive',source_revision=env['source_revision'],checking_revision=revision,checking_sources=sources,input_files=hashes,reports=reports,measured=groups,
        work='fresh prescribed K/F/nilpotent Z/terminal/support construction; independent exact certificate plus3actual nominal-QP request identities; artifact JSON serialization',
        exclusions='no gain optimization, native solve, old180QP/trajectory rerun or retrospective old timing; profiled arm excluded; no timer subtraction/ranking')

def checked_receipt(folder,path):
    saved=load(path);revision=saved.get('checking_revision');builder.require(isinstance(revision,str) and re.fullmatch('[0-9a-f]{40}',revision),'full checking revision required')
    sources=saved.get('checking_sources')
    builder.require(isinstance(sources,dict) and set(sources) in (set(study.FILES),set(study.HISTORICAL_FILES)),'mandatory checking source inventory differs')
    for name,checksum in sources.items():builder.require(study.sha(subprocess.check_output(['git','show','--end-of-options',revision+':'+name],cwd=ROOT))==checksum,'checking source differs from recorded Git')
    current=check(folder);current['checking_revision']=revision;current['checking_sources']=sources
    builder.require(current==saved,'receipt differs from actual saved replay');return saved

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--capture',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('new receipt required')
    a.output.write_bytes(study.encoded(check(a.capture.resolve())))
