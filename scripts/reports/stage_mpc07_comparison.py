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
HELPERS=['benchmarks/reporting/mpc07/'+name for name in ('capture.py','policy.py','report.py','joint_filter.py','joint_capture.py')]+['scripts/reports/stage_mpc07_comparison.py','docs/research/mpc07-delivery-disposition-2026-11-10.md']

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
    files={p.name:p.read_bytes() for p in entries};require(digest(files['SHA256SUMS'])==ANCHORS[identity],'not the reviewed frozen manifest')
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

def helper_revision():
    return subprocess.check_output(['git','log','-1','--format=%H','--',*HELPERS],cwd=ROOT,text=True).strip()

def source_export(captures):
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

def stage(site,sources=None):
    site=Path(site);require(site.is_dir() and not site.is_symlink() and not (site/'examples').is_symlink(),'regular Pages site required')
    landing=_index(site/'index.html');gallery=_index(site/'examples/index.html')
    files,captures,checks=validate(sources);proof,source_receipt=source_export(captures)
    route='mpc07-comparison-'+digest(encoded(ANCHORS)+encoded(source_receipt))[:16]
    require(not (site/route).exists() and not (site/(route+'.zip')).exists() and route not in landing and route not in gallery,'immutable route exists')
    generated={'verification.json':encoded(checks),'source-files.json':encoded(source_receipt),'minimal-inputs.json':encoded(minimal_inputs()),'index.html':page(route).encode()}
    for identity,contents in files.items():
        for name,data in contents.items():generated['evidence/'+identity+'/'+name]=data
    for name,data in proof.items():generated['source-root/'+name]=data
    generated['figures/fixed-filter-policy.svg']=files[FIXED_CURRENT]['fixed-filter-policy.svg'];generated['figures/joint-filter-policy.svg']=files[JOINT_CURRENT]['joint-filter-policy.svg']
    generated['disposition.md']=(ROOT/'docs/research/mpc07-delivery-disposition-2026-11-10.md').read_bytes()
    generated['offline_check.py']=b'''from pathlib import Path\nimport importlib.util,json\nroot=Path(__file__).resolve().parent\nspec=importlib.util.spec_from_file_location('mpc07_stage',root/'source-root/scripts/reports/stage_mpc07_comparison.py')\nm=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)\nm.verify_export(root/'source-root',json.loads((root/'source-files.json').read_bytes()))\n_,_,checks=m.validate({name:root/'evidence'/name for name in m.ANCHORS},repository=root/'source-root')\nassert checks==json.loads((root/'verification.json').read_bytes()),'publication check sidecar differs'\nprint(json.dumps(checks))\n'''
    generated['README.md']=f'''# MPC07 offline checked comparison\n\nExtract ../{route}.zip into a fresh directory, enter {route}, then run `python -B offline_check.py`. Python3.11+ and Git are required; no source checkout, solver, native binary, Matplotlib, network or install is required. This rechecks218 saved outcomes; it never optimizes. Minimal authentic selected Git commit/tree/blob objects are retained under source-root/.git with fixed empty configuration, no host config/credentials/hooks, and no full history. Missing/mutated objects refuse the check; no fallback exists.\n\nOriginal fixed/joint archives, historical receipts and separately corrected reading layers are all under evidence/ unchanged. Current helper revision and object count are in source-files.json. The helper revision is the last change to required helper files, independent of later documentation commits. Historical compiler/process paths are evidence, not portable executable paths. Performance is inconclusive. See disposition.md and index.html for equations, controls, information order, oracle and license/platform qualifications. No general-filter/uncertain-B/recursive-feasibility/online-latency claim. Publication requires reviewed current-main CI/freshness gates; this hook does not deploy.\n'''.encode()
    generated['publication-manifest.json']=encoded(dict(schema='csl.mpc07.publication/1',route=route,anchors=ANCHORS,helper_revision=source_receipt['helper_revision'],files={n:digest(v) for n,v in generated.items()}))
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

def page(route):
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MPC07 causal policies and joint filters</title><style>body{{font:16px/1.6 system-ui;background:#1e1e2e;color:#cdd6f4;max-width:1200px;margin:2rem auto;padding:1rem}}a{{color:#89b4fa}}img{{max-width:100%;height:auto}}code{{color:#f9e2af}}</style><body><h1>Checked causal policies and joint diagonal filters</h1><p>Two-state continuous-control model; T2/4/8. Independent restricted-policy implementations of published equations, not author-code reproduction. Performance: <strong>inconclusive</strong>. All218 saved outcomes, including two native refusal/infeasibility probes, retain their literal status.</p><p><a href="minimal-inputs.json">Complete inputs</a> · <a href="verification.json">Current218 checks and timing/count ranges</a> · <a href="disposition.md">Six-criterion disposition</a> · <a href="publication-manifest.json">Source/raw identities</a> · <a href="../{route}.zip">Full offline raw/source ZIP</a> · <a href="README.md">Offline recheck</a></p><section id="minimal-example"><h2>One two-state model, distinct uncertainty bounds</h2><p>x=(p,q), x0=(0,0), p_next=p+q+u/2, q_next=(1+delta)q+u+w, |u|≤1 and u0=0, |p|≤64, |q|≤16. Minimize terminal qT². The additive case has delta=0, |w|≤1. The uncertain-A case has |delta|≤1/64 and |w|≤1. Full states are observed; eta_t=q_next−q−u is reconstructed after the transition, never observed in advance.</p><p>Affine feedback uses u_t=v_t+sum(j&lt;t)M_tj eta_j. A fixed5/4 box conservatively encloses the physical lumped disturbance through |q|≤16. Its T2 virtual optimum9/4 is distinct from both the returned policy's physical cost and the physical optimum4225/4096. The fixed-gain and M=0 baselines share continuous actuator domains; their robust feasible costs are upper bounds, not finite-action rankings.</p><img src="figures/fixed-filter-policy.svg" alt="Saved two-state fixed-filter disturbance enclosure and terminal policy set"><p>The joint specialization optimizes scaled responses and a positive diagonal filter from Chen v3(24),(26),(36)–(39). R_next=A R+B H+diag(s); H is strictly causal; s[t,q]≥1+(1/64)sum|R[t,q,:]|. Position filter floor1/1024 conservatively makes the virtual filter invertible. Observed residuals reconstruct only past normalized innovations.</p><img src="figures/joint-filter-policy.svg" alt="Saved joint diagonal-filter enclosure and terminal support boxes"><p>In the saved T2/4/8 joint policies, independent exact upper/lower gaps are zero for the stated terminal-only toy. The lower bound is (65/64)^(2(T−1)); at T2 it is4225/4096. This proves policy-level attainment for these verified policies. Valid positive-gap repaired policies remain upper bounds and receive no attainment claim. It does not establish general SLS minimax equality. Support boxes and uncertainty vertices are not complete winning/reachable sets.</p></section><h2>Evidence, objective and timing scope</h2><p>Exact robust counterparts use affine-box support sums, squared terminal absolute bounds, independently replayed uncertainty containment and complete tiny analytic/vertex references. No transfer to arbitrary piecewise/replanned policies. Current checks independently authenticate native/capture source objects, original feasibility, causality, process outcomes and nested clocks. Preparation and batch native setup/port-run spans are available; port-run includes adapter checks. No isolated LP solve or executed MPC-update latency was measured.</p><p><a href="evidence/{FIXED_CURRENT}/index.html">Fixed-filter reading layer</a> · <a href="evidence/{JOINT_CURRENT}/index.html">Joint-filter reading layer</a>. All four historical/corrected folders and original offline/diagnostic ZIPs remain under evidence/. No timing winner, full non-diagonal filter, uncertain-B, recursive-feasibility or general controller claim.</p><h2>Paper, software and release qualification</h2><p>Chen arXiv2203.11375v3(2023-09-26); author repository ShaoruChen/Polytopic-SLSMPC at3f6873299ec5d0d2d87630a66486f723788390a4, no license grant visible at the recorded2026-11-10 audit, zero releases and last push2024-05-03. Author-code adoption refused; MATLAB/YALMIP/MPT3/MOSEK stack not adopted. Goulart2006's nominal quadratic formulation is not relabelled exact minimax. Our independently authored diagonal restriction uses the published equations and an existing optional CSL ConvexPort/HiGHS1.11.0 numerical LP bridge.</p><p>Linuxx86-64 saved ReleaseGCC16.2.1/CMake3.31.6; exact source/build/binary receipts retained. Historical author/software facts are audit snapshots. No redistributed solver/runtime, core API or required dependency change, install or standalone library release. Offline checking uses Python/Git only; original rendering used Matplotlib3.11.2 and shared quantitative styles. Live publication follows independent review, current CI and managed main-only stale-head gates.</p></body></html>'''

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--site',type=Path);p.add_argument('--check-raw',type=Path);p.add_argument('--repository',type=Path,default=ROOT);a=p.parse_args()
    if a.check_raw:print(json.dumps(recheck_raw(a.check_raw,a.repository),default=str))
    elif a.site:print(stage(a.site))
    else:p.error('--site or --check-raw required')
