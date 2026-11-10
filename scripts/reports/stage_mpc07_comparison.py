"""Stage reviewed MPC07 fixed/joint saved policies; never run an algorithm."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import importlib.util
import io
import json
from pathlib import Path,PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
import zipfile
import zlib

ROOT=Path(__file__).resolve().parents[2]
FIXED='bounded-policy-0e821c2a';FIXED_CURRENT=FIXED+'-recheck-v2'
JOINT='joint-filter-04369201';JOINT_CURRENT=JOINT+'-recheck-v2'
ANCHORS={FIXED:'5c50928b1650a5f665df415d7b9cd7750cafd81d8d12e28956b74bc7413b4afe',
 FIXED_CURRENT:'d03f44424e7df6bf5caf7caf0650ae1a7a69da2da12d3954a22f3d2e9a4c88d9',
 JOINT:'f7ee7214ac3a9f3ca963fce474e1e8688a7e739156a416d3d8cf879709202169',
 JOINT_CURRENT:'37d34a5095825831eb6e8e8e9bba607a304a8d75a77c27a1115b26e36aaaf6ed'}
SOURCES={name:ROOT/'benchmarks/reporting/mpc07/evidence'/name for name in ANCHORS}
ONLINE='online-evaluation-0524f7e4';ONLINE_CURRENT=ONLINE+'-recheck-aed7a98b'
ONLINE_ANCHORS={ONLINE:'540a04309384a32fb7e51861f78d0361d5d0cb50af1d6acd680ec01a4453373a',ONLINE_CURRENT:'3fe4006cf6d9513e9f94250d3d3cbdb369aa44f6838ca1649de03514db0b02b3'}
ONLINE_SOURCES={name:ROOT/'benchmarks/reporting/mpc07/evidence'/name for name in ONLINE_ANCHORS}
HELPERS=['benchmarks/reporting/mpc07/'+name for name in ('capture.py','policy.py','report.py','joint_filter.py','joint_capture.py')]+['scripts/reports/stage_mpc07_comparison.py','docs/research/mpc07-delivery-disposition-2026-11-10.md']
ONLINE_HELPERS=[n for n in HELPERS if n.endswith('.py')]+['benchmarks/reporting/mpc07/online/'+n for n in ('capture.py','check.py','controller.py','figures.py','inputs.py','profiles.json')]
HELPERS+= [n for n in ONLINE_HELPERS if n not in HELPERS]
HELPERS+=['scripts/reports/figure_style.py']

def require(condition,message):
    if not condition:raise ValueError(message)
def digest(data):return hashlib.sha256(data).hexdigest()
def encoded(value):return (json.dumps(value,indent=2,sort_keys=True)+'\n').encode()
def safe_name(name):
    p=PurePosixPath(name)
    require(bool(name) and not p.is_absolute() and p.as_posix()==name and all(re.fullmatch('[A-Za-z0-9_.-]+',v) and v not in ('.','..') for v in p.parts),'unsafe artifact path')
    return p

def sums(data):
    result={}
    for line in data.decode('ascii').splitlines():
        m=re.fullmatch(r'([0-9a-f]{64})  (.+)',line);require(m is not None,'invalid checksum line');safe_name(m[2]);require(m[2] not in result,'duplicate checksum path');result[m[2]]=m[1]
    require(result,'empty checksum inventory');return result

def frozen(source,identity):
    source=Path(source);require(source.name==identity and source.is_dir() and not source.is_symlink(),'unexpected frozen source path')
    entries=list(source.iterdir());require(all(p.is_file() and not p.is_symlink() for p in entries),'frozen inputs must be regular flat files')
    files={p.name:p.read_bytes() for p in entries};require(digest(files['SHA256SUMS'])=={**ANCHORS,**ONLINE_ANCHORS}[identity],'not the reviewed frozen manifest')
    require(sums(files['SHA256SUMS'])=={n:digest(v) for n,v in files.items() if n!='SHA256SUMS'},'frozen file hash/inventory differs');return files

def checked_zip(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            entries=z.infolist();names=[e.filename for e in entries]
            require(len(entries)<=2500 and len(names)==len(set(names)),'ZIP inventory differs')
            require(sum(e.file_size for e in entries)<=48*1024**2,'ZIP expansion cap exceeded')
            for e in entries:
                safe_name(e.filename);require(not e.is_dir() and stat.S_IFMT(e.external_attr>>16) in (0,stat.S_IFREG) and not e.flag_bits&1 and e.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED),'unsupported ZIP member')
            files={e.filename:z.read(e) for e in entries}
    except (zipfile.BadZipFile,RuntimeError,EOFError) as error:raise ValueError('invalid evidence ZIP') from error
    # Every capture's inner RAW inventory is complete, not a selected file list.
    for name,body in files.items():
        if name=='SHA256SUMS' or name.endswith('/SHA256SUMS'):
            prefix=name[:-len('SHA256SUMS')]
            require(sums(body)=={n[len(prefix):]:digest(v) for n,v in files.items() if n.startswith(prefix) and n!=name},'inner RAW checksum differs')
    return files

def materialize(files,folder):
    folder.mkdir(parents=True,exist_ok=False)
    for name,data in files.items():
        p=folder.joinpath(*safe_name(name).parts);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)

def _checker(repository):
    sys.path.insert(0,str(repository))
    # A subprocess owns these imports; generic names belong to other consumers.
    from benchmarks.reporting.mpc07 import report
    return report

def recheck_raw(root,repository):
    report=_checker(repository);env,records,policies,hashes=report.checked_records(root,repository=repository)
    return dict(environment=env,records=records,groups=report.metrics(records),
        attainment=report.joint_attainment(records) if env['schema']=='csl.mpc07.joint-filter.capture/1' else None)

def validate(sources=None,*,repository=ROOT):
    sources=SOURCES if sources is None else sources;require(set(sources)==set(ANCHORS),'mandatory evidence source inventory differs')
    files={name:frozen(sources[name],name) for name in ANCHORS}
    require(files[FIXED]['offline.zip']==files[FIXED_CURRENT]['offline.zip'] and files[JOINT]['offline.zip']==files[JOINT_CURRENT]['offline.zip'],'corrected reading layer rewrote original capture')
    captures={};checks={}
    for label,identity,prefix in [('fixed',FIXED_CURRENT,'mpc07-report'),('joint',JOINT_CURRENT,'mpc07-joint-report')]:
        packed=checked_zip(files[identity]['offline.zip']);require(prefix+'/RAW/SHA256SUMS' in packed,'missing complete raw capture')
        # Also validate every retained diagnostic/checker ZIP before staging.
        for name,data in files[identity].items():
            if name.endswith('.zip'):checked_zip(data)
        raw={n[len(prefix+'/RAW/'):]:v for n,v in packed.items() if n.startswith(prefix+'/RAW/')};captures[label]=raw
        with tempfile.TemporaryDirectory(prefix='mpc07-publication-check-') as temporary:
            root=Path(temporary)/'RAW';materialize(raw,root)
            command=[sys.executable,'-B',str(repository/'scripts/reports/stage_mpc07_comparison.py'),'--check-raw',str(root),'--repository',str(repository)]
            result=subprocess.run(command,cwd=repository,capture_output=True,text=True,timeout=40)
            require(result.returncode==0,'saved '+label+' recheck failed: '+result.stderr[-1800:]);current=json.loads(result.stdout)
        require(len(current['records'])==(146 if label=='fixed' else 72),'saved outcome inventory differs')
        # Old sidecars are immutable; compare mathematical/process records literally.
        saved=json.loads(files[identity]['current-rechecks.json']);require(current['records']==saved,'corrected sidecar differs from current saved evidence checks')
        summary=json.loads(files[identity]['summary.json']);require(summary['environment']==current['environment'],'report environment differs')
        for key,group in summary['groups'].items():
            require(key in current['groups'],'summary profile differs')
            for field,value in group.items():require(current['groups'][key].get(field)==value,'summary count/cost/bound differs')
        export=json.loads(files[identity]['figure-export.json']);figure=json.loads(files[identity]['figure-data.json'])
        require(export['figure_data_sha256']==digest(files[identity]['figure-data.json']),'figure input binding differs')
        require(export['input_manifest_sha256']==digest(raw['SHA256SUMS']),'figure/raw binding differs')
        for name,value in export['images'].items():require(digest(files[identity][name])==value,'figure export hash differs')
        if label=='joint':
            require(summary['joint_attainment']==current['attainment'],'attainment summary differs')
            # These plotted objects must be actual retained T2 policies, not samples invented for publication.
            for field,kind in [('joint_policy','joint'),('fixed_policy','fixed-filter')]:
                require(any(row['receipt'].get('horizon')==2 and row['receipt'].get('policy_class')==kind and row['current_check']==figure[field] for row in current['records']),'figure policy does not match saved check')
        checks[label]=current
    return files,captures,dict(attempts=sum(len(v['records']) for v in checks.values()),
        fixed_outcomes=dict(Counter(r['current_check']['status'] for r in checks['fixed']['records'])),
        joint_outcomes=dict(Counter(r['current_check']['status'] for r in checks['joint']['records'])),
        joint_attainment=checks['joint']['attainment'],groups={k:v['groups'] for k,v in checks.items()},
        scope='current source/process/exact policy/containment/oracle/clock checks; no algorithm execution; descriptive timing only')

def online_inputs(sources=None):
    sources=ONLINE_SOURCES if sources is None else sources
    require(set(sources)==set(ONLINE_ANCHORS),'mandatory online evidence inventory differs')
    files={name:frozen(sources[name],name) for name in ONLINE_ANCHORS};original=files[ONLINE];corrected=files[ONLINE_CURRENT]
    packed=checked_zip(original['capture.zip'])
    require(len(packed)==24 and 'capture/SHA256SUMS' in packed and all(n=='SHA256SUMS' or n.startswith('capture/') for n in packed),'online raw member inventory differs')
    raw={n[len('capture/'):]:v for n,v in packed.items() if n.startswith('capture/')}
    environment=json.loads(raw['environment.json']);inputs=json.loads(raw['inputs.json']);reading=json.loads(corrected['verification.json'])
    require(set(environment['source_sha256'])==set(reading['checking_sources'])==set(ONLINE_HELPERS),'mandatory online helper/source inventory differs')
    require(raw['inputs.json']==raw['source/benchmarks/reporting/mpc07/online/profiles.json'] and digest(raw['inputs.json'])==environment['input_sha256'],'online committed input binding differs')
    for revision in (environment['source_revision'],reading['checking_revision']):require(isinstance(revision,str) and re.fullmatch('[0-9a-f]{40}',revision),'invalid online source revision')
    qualification=json.loads(corrected['qualification.json'])
    require(qualification['capture_source']==environment['source_revision'] and qualification['checking_source']==reading['checking_revision'],'online qualification source differs')
    require(qualification['original_inventory_sha256']==ONLINE_ANCHORS[ONLINE] and qualification['original_capture_zip_sha256']==digest(original['capture.zip']) and qualification['corrected_verification_sha256']==digest(corrected['verification.json']),'online qualification/archive binding differs')
    source_files=checked_zip(corrected['checking-source.zip'])
    require(set(source_files)==set(ONLINE_HELPERS)|{'SHA256SUMS'},'online corrected source ZIP inventory differs')
    for name,checksum in reading['checking_sources'].items():require(digest(source_files[name])==checksum,'online corrected source fingerprint differs')
    old=json.loads(original['verification.json']);stable=lambda value:{k:v for k,v in value.items() if k not in ('checking_revision','checking_sources')}
    require(stable(old)==stable(reading),'online correction changed original numeric reports/inputs/timings')
    figure=json.loads(original['figure-data.json']);export=json.loads(original['figure-export.json'])
    require(export['input_data_sha256']==digest(original['figure-data.json']) and export['verification_sha256']==figure['verification_sha256']==digest(original['verification.json']),'online historical figure/receipt binding differs')
    require(set(export['images'])=={'online-policy-traces.svg','online-policy-traces.png'},'online figure inventory differs')
    for name,checksum in export['images'].items():require(digest(original[name])==checksum,'online figure image hash differs')
    records=[json.loads(line) for line in raw['measured/stdout.jsonl'].decode().splitlines()]
    selected=[r for r in records if r['profile'].startswith('joint-T8-') and r['family']=='positive' and r['repetition']==0]
    require(len(selected)==4 and figure['rows']==selected,'online figure differs from actual consumed N8 trace records')
    return dict(files=files,raw=raw,environment=environment,inputs=inputs,reading=reading,checking_files=source_files,figure=figure)


def validate_online(online,*,repository=ROOT,sources=None):
    reading=online['reading'];sources=SOURCES if sources is None else sources
    require(set(sources)==set(ANCHORS),'online upstream source inventory differs')
    # Authenticate the historical corrected checker separately; then execute the
    # current exported checker rather than trusting a cached success receipt.
    for name,checksum in reading['checking_sources'].items():
        data=subprocess.check_output(['git','show','--end-of-options',reading['checking_revision']+':'+name],cwd=repository)
        require(data==online['checking_files'][name] and digest(data)==checksum,'online corrected source differs from authentic Git object')
    with tempfile.TemporaryDirectory(prefix='mpc07-online-publication-check-') as temporary:
        root=Path(temporary);materialize(online['raw'],root/'capture')
        bootstrap="import json,sys; from pathlib import Path; from scripts.reports import stage_mpc07_comparison as upstream; upstream.SOURCES={n:Path(p) for n,p in json.loads(sys.argv[1]).items()}; from benchmarks.reporting.mpc07.online.check import check; from benchmarks.reporting.mpc07.online.inputs import encoded; Path(sys.argv[3]).write_bytes(encoded(check(Path(sys.argv[2]))))"
        command=[sys.executable,'-B','-c',bootstrap,json.dumps({n:str(Path(p).resolve()) for n,p in sources.items()}),str(root/'capture'),str(root/'current.json')]
        result=subprocess.run(command,cwd=repository,capture_output=True,text=True,timeout=60)
        require(result.returncode==0,'online saved source/policy replay failed: '+result.stderr[-2400:])
        current=json.loads((root/'current.json').read_bytes())
    stable=lambda value:{k:v for k,v in value.items() if k not in ('checking_revision','checking_sources')}
    require(set(current['checking_sources'])==set(ONLINE_HELPERS) and all(digest((repository/n).read_bytes())==v for n,v in current['checking_sources'].items()),'current online checker/export source binding differs')
    require(stable(current)==stable(reading) and current['status']=='checked','online corrected receipt differs from actual current replay')
    require(current['scheduled_episodes']==432 and current['scheduled_stages']==2016 and len(current['reports'])==2,'online scheduled inventory differs')
    require(all(r['status']=='checked' and r['episodes']==432 and r['stages']==2016 and r['outcomes']=={'verified-numerical-evaluation':432} for r in current['reports']),'online complete replay inventory differs')
    print(json.dumps(dict(schema='csl.mpc07.online-current-publication-check/1',capture_source=current['source_revision'],checking_revision=current['checking_revision'],checking_sources=current['checking_sources'],status=current['status']),sort_keys=True),file=sys.stderr)
    clock=online['environment']['clock'];measured=[g for g in reading['groups'] if g['family']=='positive' and g['profile']=='joint-T8-optimized-diagonal-joint']
    require(len(measured)==1,'online primary profile inventory differs')
    return dict(status='checked',episodes=864,stages=4032,profiles=reading['profiles'],measured_episodes=sum(g['completed'] for g in reading['groups']),measured_stages=sum(g['query']['count'] for g in reading['groups']),
        capture_source=online['environment']['source_revision'],corrected_checking_source=reading['checking_revision'],corrected_verification_sha256=digest(online['files'][ONLINE_CURRENT]['verification.json']),
        clock_pair_ns=clock['empty_pair_ns'],primary_query=measured[0]['query'],preparation=measured[0]['preparation'],
        scope='instrumented stored-feedback evaluation only; substantial timestamp overhead, no intrinsic latency resolution/ranking or LP/MPC reoptimization')


def online_reading(online):
    original=online['files'][ONLINE];corrected=online['files'][ONLINE_CURRENT]
    data=dict(online['figure']);data['historical_figure_data_sha256']=digest(original['figure-data.json']);data['verification_sha256']=digest(corrected['verification.json'])
    bound=encoded(data)
    export=dict(schema='csl.mpc07.online-publication-figure/1',corrected_verification_sha256=digest(corrected['verification.json']),input_data_sha256=digest(bound),historical_export_sha256=digest(original['figure-export.json']),capture_zip_sha256=digest(original['capture.zip']),
        images={n:digest(original[n]) for n in ('online-policy-traces.svg','online-policy-traces.png')},scope='unchanged original image bytes; actual raw trace rows and corrected complete replay bound separately')
    return {'figures/online-policy-traces.svg':original['online-policy-traces.svg'],'figures/online-policy-traces.png':original['online-policy-traces.png'],
        'online-verification.json':corrected['verification.json'],'online-figure-data.json':bound,'online-figure-export.json':encoded(export)}


def online_section(online):
    query=online['primary_query'];clock=online['clock_pair_ns']
    return f'''<section id="online-evaluation"><h2>Actual causal feedback evaluation, separate from synthesis/replanning</h2>
<p>All36 existing verified profiles run two physical trace families: w=+1 or alternating signs, with constant delta=+epsilon (0 additive,1/64 uncertain-A) in both. The controller API receives only observed states and its own past controls. It reconstructs the previous transition residual or normalized innovation, returns an action, and only then does the plant apply current uncertainty. The returned actions are consumed in the saved physical traces.</p>
<p>One excluded warmup plus five measured repetitions derive432episodes/2016stages per arm;360episodes/1680stages enter statistics. A separate instrumented profile arm is entirely excluded from latency statistics. Current source/rational/policy/physical/bound checks verify all864episodes/4032stages. These sample paths do not add a robustness, global-optimality or reachable-set guarantee.</p>
<img src="figures/online-policy-traces.svg" alt="Actual N8 positive physical trace for four stored causal policy classes, with phase/state/control panels and q=0 cost reference">
<p>The displayed N8positive trace is selected, not asserted worst-case. Circles identify initial state and crosses terminal state; q=0 marks zero terminal q-squared cost as a reference, not claimed attainment. Full matrices, rational policies, causal information, physical bounds and both trace definitions are in <a href="minimal-inputs.json">complete inputs</a>.</p>
<p><strong>Instrumented query spans, not resolved intrinsic latency.</strong> The N8joint/positive profile has median{query['median_ns']}ns and range{query['minimum_ns']}–{query['maximum_ns']}ns across{query['count']}queries. Empty timestamp-pair median{clock['median']}ns (range{clock['minimum']}–{clock['maximum']}ns) is substantial; no overhead is subtracted. Initial observation, past-residual update, query, rational-to-binary64 policy preparation, episode and process/CPU/RSS scopes remain distinct. This generic dense Python evaluator is not sparsity-tuned. No policy ranking, native/real-time bound, LP-solve or MPC-reoptimization latency is inferred.</p>
<p><a href="online-verification.json">Corrected complete replay and all integer timing groups</a> · <a href="online-figure-data.json">Bound actual trace arrays</a> · <a href="online-figure-export.json">Figure/current-receipt binding</a> · <a href="evidence/{ONLINE}/capture.zip">Unchanged original online capture</a> · <a href="evidence/{ONLINE_CURRENT}/qualification.json">Corrected source qualification</a>. Capture source0524 and corrected checking sourceaed remain distinct; original archives/figures/timings are unchanged. The online source profile and committed inputs are authenticated, including during the exported outside-checkout replay.</p></section>'''


def helper_revision():
    return subprocess.check_output(['git','log','-1','--format=%H','--',*HELPERS],cwd=ROOT,text=True).strip()

def source_export(captures,online=None):
    revision=helper_revision();require(re.fullmatch('[0-9a-f]{40}',revision),'invalid helper revision')
    files={};objects=set();sources=[]
    for name in HELPERS:
        data=(ROOT/name).read_bytes();committed=subprocess.check_output(['git','show','--end-of-options',revision+':'+name],cwd=ROOT)
        require(data==committed,'helper differs from stable committed source: '+name);files[name]=data
    sources.append((revision,{name:digest(files[name]) for name in HELPERS}))
    for raw in captures.values():
        env=json.loads(raw['environment.json']);native=env['native_source_commit']
        # Import-free closed maps mirror the reviewed strict current checkers.
        maps={'PLAN.md':'benchmarks/reporting/mpc07/PLAN.md','README.md':'benchmarks/reporting/mpc07/README.md','capture.py':'benchmarks/reporting/mpc07/capture.py','policy.py':'benchmarks/reporting/mpc07/policy.py','report.py':'benchmarks/reporting/mpc07/report.py','native-build-receipt.json':'benchmarks/reporting/mpc07/native-build-receipt.json','test_mpc07_policy.py':'tests/reporting/test_mpc07_policy.py','native-affine_bridge.cpp':'benchmarks/reporting/mpc11/affine_bridge.cpp','native-CMakeLists.txt':'benchmarks/reporting/mpc11/CMakeLists.txt'}
        if env['schema']=='csl.mpc07.joint-filter.capture/1':maps.update({'JOINT-FILTER.md':'benchmarks/reporting/mpc07/JOINT-FILTER.md','joint_filter.py':'benchmarks/reporting/mpc07/joint_filter.py','joint_capture.py':'benchmarks/reporting/mpc07/joint_capture.py','test_mpc07_joint_filter.py':'tests/reporting/test_mpc07_joint_filter.py','joint-gain-fixture.json':'tests/reporting/fixtures/mpc07-joint-gain-t08.json','figure_style.py':'scripts/reports/figure_style.py'})
        require(set(maps)==set(env['source_sha256']),'export capture source inventory differs')
        for commit in (env['source_commit'],native):
            require(re.fullmatch('[0-9a-f]{40}',commit),'invalid capture source revision')
            sources.append((commit,{path:env['source_sha256'][name] for name,path in maps.items() if (name.startswith('native-') and name!='native-build-receipt.json')==(commit==native)}))
    if online is not None:
        environment=online['environment'];reading=online['reading']
        sources.extend([(environment['source_revision'],environment['source_sha256']),
                        (reading['checking_revision'],reading['checking_sources'])])
    def include(oid):
        require(re.fullmatch('[0-9a-f]{40}',oid),'invalid object revision')
        if oid in objects:return
        objects.add(oid);kind=subprocess.check_output(['git','cat-file','-t',oid],cwd=ROOT,text=True).strip();require(kind in ('commit','tree','blob'),'unexpected object kind')
        content=subprocess.check_output(['git','cat-file',kind,oid],cwd=ROOT);raw=f'{kind} {len(content)}'.encode()+b'\0'+content;require(hashlib.sha1(raw).hexdigest()==oid,'object hash differs');files['.git/objects/'+oid[:2]+'/'+oid[2:]]=zlib.compress(raw)
    for commit,paths in sources:
        include(commit);include(subprocess.check_output(['git','rev-parse',commit+'^{tree}'],cwd=ROOT,text=True).strip())
        for name,checksum in paths.items():
            safe_name(name);content=subprocess.check_output(['git','show','--end-of-options',commit+':'+name],cwd=ROOT);require(digest(content)==checksum,'Git source digest differs')
            parts=PurePosixPath(name).parts
            for size in range(1,len(parts)+1):include(subprocess.check_output(['git','rev-parse',commit+':'+str(PurePosixPath(*parts[:size]))],cwd=ROOT,text=True).strip())
    if online is not None:
        # The capture authenticator lists this entire prefix, requiring trees,
        # including historical evidence-directory trees, but not their blobs.
        lines=subprocess.check_output(['git','ls-tree','-r','-t',online['environment']['source_revision'],'--','benchmarks/reporting/mpc07'],cwd=ROOT,text=True).splitlines()
        for line in lines:
            fields=line.split(None,3)
            if fields[1]=='tree':include(fields[2])
    files['.git/config']=b'[core]\nrepositoryformatversion = 0\nbare = false\n';files['.git/HEAD']=b'ref: refs/heads/evidence\n';files['.git/refs/heads/evidence']=(revision+'\n').encode()
    return files,dict(helper_revision=revision,helper_sha256={name:digest(files[name]) for name in HELPERS},object_count=len(objects))

def verify_export(root,receipt):
    require(set(receipt['helper_sha256'])==set(HELPERS),'export helper inventory differs');revision=receipt['helper_revision'];require(re.fullmatch('[0-9a-f]{40}',revision),'invalid helper revision')
    git=root/'.git';require((git/'config').read_bytes()==b'[core]\nrepositoryformatversion = 0\nbare = false\n' and (git/'HEAD').read_bytes()==b'ref: refs/heads/evidence\n' and (git/'refs/heads/evidence').read_bytes()==(revision+'\n').encode(),'source proof configuration differs')
    count=0
    for p in git.rglob('*'):
        require(not p.is_symlink(),'source proof symlink')
        if not p.is_file():continue
        name=p.relative_to(git).as_posix()
        if name in ('config','HEAD','refs/heads/evidence'):continue
        require(re.fullmatch('objects/[0-9a-f]{2}/[0-9a-f]{38}',name),'unexpected Git file');count+=1
        dec=zlib.decompressobj();raw=dec.decompress(p.read_bytes(),2*1024**2+1);require(len(raw)<=2*1024**2 and dec.eof and not dec.unused_data and not dec.unconsumed_tail,'invalid source object')
        require(hashlib.sha1(raw).hexdigest()==p.parent.name+p.name,'Git object SHA differs')
    require(count==receipt['object_count']<=180,'Git object inventory differs')
    for name,checksum in receipt['helper_sha256'].items():
        data=(root/name).read_bytes();require(digest(data)==checksum,'export helper hash differs');require(subprocess.check_output(['git','show','--end-of-options',revision+':'+name],cwd=root)==data,'export helper Git bytes differ')

def _index(path):
    require(path.is_file() and not path.is_symlink(),'regular Pages index required');text=path.read_text();require(len(re.findall(r'<body\b',text,re.I))==1 and text.count('</body>')==1,'one body insertion point required');return text

def stage(site,sources=None,*,online_sources=None):
    site=Path(site);require(site.is_dir() and not site.is_symlink() and not (site/'examples').is_symlink(),'regular Pages site required')
    landing=_index(site/'index.html');gallery=_index(site/'examples/index.html')
    files,captures,checks=validate(sources);online=online_inputs(online_sources)
    proof,source_receipt=source_export(captures,online);checks['online']=validate_online(online,repository=ROOT,sources=sources)
    files.update(online['files'])
    route='mpc07-comparison-'+digest(encoded({**ANCHORS,**ONLINE_ANCHORS})+encoded(source_receipt))[:16]
    require(not (site/route).exists() and not (site/(route+'.zip')).exists() and route not in landing and route not in gallery,'immutable route exists')
    generated={'verification.json':encoded(checks),'source-files.json':encoded(source_receipt),'minimal-inputs.json':encoded(dict(**minimal_inputs(),online_policy_evaluation=online['inputs'])),'index.html':page(route,checks['online']).encode()}
    for identity,contents in files.items():
        for name,data in contents.items():generated['evidence/'+identity+'/'+name]=data
    for name,data in proof.items():generated['source-root/'+name]=data
    generated['figures/fixed-filter-policy.svg']=files[FIXED_CURRENT]['fixed-filter-policy.svg'];generated['figures/joint-filter-policy.svg']=files[JOINT_CURRENT]['joint-filter-policy.svg']
    generated.update(online_reading(online))
    generated['disposition.md']=(ROOT/'docs/research/mpc07-delivery-disposition-2026-11-10.md').read_bytes()
    generated['offline_check.py']=b'''from pathlib import Path\nimport importlib.util,json\nroot=Path(__file__).resolve().parent\nspec=importlib.util.spec_from_file_location('mpc07_stage',root/'source-root/scripts/reports/stage_mpc07_comparison.py')\nm=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)\nm.verify_export(root/'source-root',json.loads((root/'source-files.json').read_bytes()))\n_,_,checks=m.validate({name:root/'evidence'/name for name in m.ANCHORS},repository=root/'source-root')\nonline=m.online_inputs({name:root/'evidence'/name for name in m.ONLINE_ANCHORS})\nchecks['online']=m.validate_online(online,repository=root/'source-root',sources={name:root/'evidence'/name for name in m.ANCHORS})\nassert checks==json.loads((root/'verification.json').read_bytes()),'publication check sidecar differs'\nprint(json.dumps(checks))\n'''
    generated['README.md']=f'''# MPC07 offline checked comparison\n\nExtract ../{route}.zip into a fresh directory, enter {route}, then run `python -B offline_check.py`. Python3.11+ and Git are required; no source checkout, solver, native binary, Matplotlib, network or install is required. This rechecks218 original outcomes plus864online episodes/4032stages; it never optimizes. Minimal authentic selected Git commit/tree/blob objects are retained under source-root/.git with fixed empty configuration, no host config/credentials/hooks, and no full history. Missing/mutated objects refuse the check; no fallback exists.\n\nOriginal fixed/joint archives, historical receipts and separately corrected reading layers are all under evidence/ unchanged. Current helper revision and object count are in source-files.json. The helper revision is the last change to required helper files, independent of later documentation commits. Historical compiler/process paths are evidence, not portable executable paths. Performance is inconclusive. See disposition.md and index.html for equations, controls, information order, oracle and license/platform qualifications. No general-filter/uncertain-B/recursive-feasibility/online-latency claim. Publication requires reviewed current-main CI/freshness gates; this hook does not deploy.\n'''.encode()
    generated['publication-manifest.json']=encoded(dict(schema='csl.mpc07.publication/1',route=route,anchors={**ANCHORS,**ONLINE_ANCHORS},helper_revision=source_receipt['helper_revision'],files={n:digest(v) for n,v in generated.items()}))
    generated['SHA256SUMS']=(''.join(f'{digest(v)}  {n}\n' for n,v in sorted(generated.items()))).encode()
    from scripts.reports.mpc01.stage_per_attempt import _insert_landing_link
    with tempfile.TemporaryDirectory(prefix='mpc07-stage-') as temporary:
        scratch=Path(temporary);(scratch/'examples').mkdir();(scratch/'index.html').write_text(landing);(scratch/'examples/index.html').write_text(gallery)
        _insert_landing_link(scratch,route,route+'/index.html','MPC07 checked affine policies and joint diagonal-filter comparison')
        card=f'<article class="saved-figure" id="{route}-example"><h2>Two-state robust policy and filter example</h2><p>Fixed and joint restricted causal policies; exact bounds, raw data and inconclusive timings.</p><a href="../{route}/index.html#minimal-example"><img src="../{route}/figures/joint-filter-policy.svg" alt="Two-state saved joint-filter enclosure and terminal support boxes">Open complete minimal MPC07 example</a></article>'
        (scratch/'examples/index.html').write_text(gallery.replace('</body>',card+'</body>'))
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for name,data in sorted(generated.items()):
                entry=zipfile.ZipInfo(route+'/'+name,date_time=(2026,1,1,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED;entry.external_attr=0o100644<<16;z.writestr(entry,data)
        materialize(generated,site/route)
        with (site/(route+'.zip')).open('xb') as output:output.write(buffer.getvalue())
        (site/'index.html').write_bytes((scratch/'index.html').read_bytes());(site/'examples/index.html').write_bytes((scratch/'examples/index.html').read_bytes())
    return route

def minimal_inputs():
    return dict(state_dimension=2,coordinates=['position p','velocity q'],horizons=[2,4,8],initial=[0,0],
        A=[[1,1],[0,1]],B=['1/2',1],physical_disturbance_direction=[0,1],
        dynamics='p_next=p+q+u/2; q_next=(1+delta)*q+u+w',controls='continuous |u|<=1; u0=0',
        state_bounds='|p|<=64, |q|<=16',terminal_cost='qT^2; no running cost',
        additive_profile='delta=0, w in[-1,1]',uncertain_A_profile='delta in[-1/64,1/64], w in[-1,1]',
        fixed_policies=['fixed-plan','fixed-gain','adf','response'],joint_policies=['fixed-plan','fixed-gain','joint','fixed-filter'],
        gains=dict(additive='u=-q',fixed_filter='u=-q/16',joint_uncertain_A='u=-q/16'),
        repetitions=dict(warmups_per_profile=1,measured_per_profile=5,fixed_primary=144,fixed_separate_probes=2,joint_primary=72),
        fixed_filter='uniform lumped disturbance bound5/4 via |q|<=16',joint_filter='positive diagonal virtual filter; position floor1/1024; s[t,q]>=1+(1/64)*sum(abs(R[t,q,:]))',
        information='exact full state; reconstruct only past lumped disturbances; normalized innovations after each observed transition',
        physical_causal_lower='(65/64)^(2*(T-1)) for this terminal-only uncertain-A toy',
        minimal_T2=dict(joint_physical_upper_and_lower='4225/4096',fixed_filter_virtual_optimum='9/4',additive_optimum='1'))

def page(route,online=None):
    body=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MPC07 causal policies and joint filters</title><style>body{{font:16px/1.6 system-ui;background:#1e1e2e;color:#cdd6f4;max-width:1200px;margin:2rem auto;padding:1rem}}a{{color:#89b4fa}}img{{max-width:100%;height:auto}}code{{color:#f9e2af}}</style><body><h1>Checked causal policies and joint diagonal filters</h1><p>Two-state continuous-control model; T2/4/8. Independent restricted-policy implementations of published equations, not author-code reproduction. Performance: <strong>inconclusive</strong>. All218 saved outcomes, including two native refusal/infeasibility probes, retain their literal status.</p><p><a href="minimal-inputs.json">Complete inputs</a> · <a href="verification.json">Current218 checks and timing/count ranges</a> · <a href="disposition.md">Six-criterion disposition</a> · <a href="publication-manifest.json">Source/raw identities</a> · <a href="../{route}.zip">Full offline raw/source ZIP</a> · <a href="README.md">Offline recheck</a></p><section id="minimal-example"><h2>One two-state model, distinct uncertainty bounds</h2><p>x=(p,q), x0=(0,0), p_next=p+q+u/2, q_next=(1+delta)q+u+w, |u|≤1 and u0=0, |p|≤64, |q|≤16. Minimize terminal qT². The additive case has delta=0, |w|≤1. The uncertain-A case has |delta|≤1/64 and |w|≤1. Full states are observed; eta_t=q_next−q−u is reconstructed after the transition, never observed in advance.</p><p>Affine feedback uses u_t=v_t+sum(j&lt;t)M_tj eta_j. A fixed5/4 box conservatively encloses the physical lumped disturbance through |q|≤16. Its T2 virtual optimum9/4 is distinct from both the returned policy's physical cost and the physical optimum4225/4096. The fixed-gain and M=0 baselines share continuous actuator domains; their robust feasible costs are upper bounds, not finite-action rankings.</p><img src="figures/fixed-filter-policy.svg" alt="Saved two-state fixed-filter disturbance enclosure and terminal policy set"><p>The joint specialization optimizes scaled responses and a positive diagonal filter from Chen v3(24),(26),(36)–(39). R_next=A R+B H+diag(s); H is strictly causal; s[t,q]≥1+(1/64)sum|R[t,q,:]|. Position filter floor1/1024 conservatively makes the virtual filter invertible. Observed residuals reconstruct only past normalized innovations.</p><img src="figures/joint-filter-policy.svg" alt="Saved joint diagonal-filter enclosure and terminal support boxes"><p>In the saved T2/4/8 joint policies, independent exact upper/lower gaps are zero for the stated terminal-only toy. The lower bound is (65/64)^(2(T−1)); at T2 it is4225/4096. This proves policy-level attainment for these verified policies. Valid positive-gap repaired policies remain upper bounds and receive no attainment claim. It does not establish general SLS minimax equality. Support boxes and uncertainty vertices are not complete winning/reachable sets.</p></section><h2>Evidence, objective and timing scope</h2><p>Exact robust counterparts use affine-box support sums, squared terminal absolute bounds, independently replayed uncertainty containment and complete tiny analytic/vertex references. No transfer to arbitrary piecewise/replanned policies. Current checks independently authenticate native/capture source objects, original feasibility, causality, process outcomes and nested clocks. Preparation and batch native setup/port-run spans are available; port-run includes adapter checks. No isolated LP solve or executed MPC-update latency was measured.</p><p><a href="evidence/{FIXED_CURRENT}/index.html">Fixed-filter reading layer</a> · <a href="evidence/{JOINT_CURRENT}/index.html">Joint-filter reading layer</a>. All four historical/corrected folders and original offline/diagnostic ZIPs remain under evidence/. No timing winner, full non-diagonal filter, uncertain-B, recursive-feasibility or general controller claim.</p><h2>Paper, software and release qualification</h2><p>Chen arXiv2203.11375v3(2023-09-26); author repository ShaoruChen/Polytopic-SLSMPC at3f6873299ec5d0d2d87630a66486f723788390a4, no license grant visible at the recorded2026-11-10 audit, zero releases and last push2024-05-03. Author-code adoption refused; MATLAB/YALMIP/MPT3/MOSEK stack not adopted. Goulart2006's nominal quadratic formulation is not relabelled exact minimax. Our independently authored diagonal restriction uses the published equations and an existing optional CSL ConvexPort/HiGHS1.11.0 numerical LP bridge.</p><p>Linuxx86-64 saved ReleaseGCC16.2.1/CMake3.31.6; exact source/build/binary receipts retained. Historical author/software facts are audit snapshots. No redistributed solver/runtime, core API or required dependency change, install or standalone library release. Offline checking uses Python/Git only; original rendering used Matplotlib3.11.2 and shared quantitative styles. Live publication follows independent review, current CI and managed main-only stale-head gates.</p></body></html>'''
    if online is not None:body=body.replace('<h2>Paper, software and release qualification</h2>',online_section(online)+'<h2>Paper, software and release qualification</h2>')
    return body


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--site',type=Path);p.add_argument('--check-raw',type=Path);p.add_argument('--repository',type=Path,default=ROOT);a=p.parse_args()
    if a.check_raw:print(json.dumps(recheck_raw(a.check_raw,a.repository),default=str))
    elif a.site:print(stage(a.site))
    else:p.error('--site or --check-raw required')
