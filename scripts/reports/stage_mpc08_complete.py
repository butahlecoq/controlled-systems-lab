"""Stage the bounded MPC08 delivery from two immutable captures; no native run."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
import zipfile
import zlib

ROOT=Path(__file__).resolve().parents[2]
EXACT_ID='mpc08-exact-regions-79ec2978-20261110'
HORIZON_ID='mpc08-horizon-regions-01762505-20261110'
EXACT_SOURCE=ROOT/'reports/algorithm-results'/EXACT_ID
HORIZON_SOURCE=ROOT/'reports/algorithm-results'/HORIZON_ID
SPECS={EXACT_ID:('4b5fcbac7a4e158dc52c43834409ccddc3ba03ae95a0d8b0a47556899b5a5d22','79ec2978bb18a77abf5817b6f940aa3a89b0e488',17),
       HORIZON_ID:('bd2c153d4642383abc1d75299775d9b1b6b78119b9b714455e1de253290dc818','017625057d253ae191405ca163bbda85729af3aa',10)}
HELPERS=['benchmarks/reporting/mpc08_explicit/'+name for name in
         ('recheck_exact_regions.py','exact_regions.py','capture_exact_regions.py','explicit_double_integrator.py',
          'horizon_regions.py','capture_horizon_regions.py','mpc08_strategy_comparison.cpp')]+[
         'benchmarks/reporting/review05/run_horizon_ladder.py','benchmarks/reporting/review05/highs_clock_events.py',
         'scripts/reports/figure_style.py','scripts/reports/stage_mpc08_complete.py']


def digest(data):return hashlib.sha256(data).hexdigest()

def require(condition,message):
    if not condition:raise ValueError(message)


def safe_name(name):
    path=PurePosixPath(name)
    require(bool(name) and not path.is_absolute() and path.as_posix()==name and
            all(re.fullmatch(r'[A-Za-z0-9_.-]+',part) and part not in ('.','..') for part in path.parts),'unsafe artifact path')
    return path


def sums(data):
    result={}
    for line in data.decode('ascii').splitlines():
        match=re.fullmatch(r'([0-9a-f]{64})  (.+)',line);require(match is not None,'invalid checksum line')
        name=match[2];safe_name(name);require(name not in result,'duplicate checksum path');result[name]=match[1]
    require(result,'empty checksum inventory');return result


def frozen(source,identity):
    require(source.name==identity and source.is_dir() and not source.is_symlink(),'unexpected frozen report directory')
    paths=list(source.iterdir());require(all(p.is_file() and not p.is_symlink() for p in paths),'frozen report must contain regular flat files')
    files={p.name:p.read_bytes() for p in paths};require('SHA256SUMS' in files,'missing frozen inventory')
    require(digest(files['SHA256SUMS'])==SPECS[identity][0],'not the reviewed immutable report manifest')
    expected=sums(files['SHA256SUMS'])
    require(expected=={n:digest(b) for n,b in files.items() if n!='SHA256SUMS'},'frozen report inventory differs')
    return files


def checked_zip(data,count):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries=archive.infolist();names=[e.filename for e in entries]
            require(len(entries)==count and len(names)==len(set(names)),'capture member inventory differs')
            require(sum(e.file_size for e in entries)<=16*1024**2,'capture expansion cap exceeded')
            for entry in entries:
                require(len(safe_name(entry.filename).parts)==1 and not entry.is_dir(),'capture must have flat regular members')
                require(stat.S_IFMT(entry.external_attr>>16) in (0,stat.S_IFREG) and not entry.flag_bits&1 and
                        entry.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED),'unsupported ZIP member')
            files={e.filename:archive.read(e) for e in entries}
    except (zipfile.BadZipFile,RuntimeError,EOFError) as error:raise ValueError('invalid capture ZIP') from error
    require('SHA256SUMS' in files,'missing capture inventory')
    require(sums(files['SHA256SUMS'])=={n:digest(b) for n,b in files.items() if n!='SHA256SUMS'},'capture checksum mismatch')
    return files


def materialize(files,folder):
    folder.mkdir(parents=True,exist_ok=False)
    for name,data in files.items():
        target=folder.joinpath(*safe_name(name).parts);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)


def validate(exact_source=EXACT_SOURCE,horizon_source=HORIZON_SOURCE,*,repository=ROOT):
    frozen_files={identity:frozen(Path(source),identity) for identity,source in ((EXACT_ID,exact_source),(HORIZON_ID,horizon_source))}
    captures={identity:checked_zip(files['capture.zip'],SPECS[identity][2]) for identity,files in frozen_files.items()}
    for identity,files in captures.items():
        manifest=json.loads(files['manifest.json'])
        require(manifest['source_commit']==SPECS[identity][1] and manifest['source_status']=='','capture source identity differs')
    commands=[('exact','recheck_exact_regions.py',EXACT_ID),('horizon','capture_horizon_regions.py',HORIZON_ID)]
    checks={}
    with tempfile.TemporaryDirectory(prefix='mpc08-saved-publication-check-') as temporary:
        for label,script,identity in commands:
            folder=Path(temporary)/label;materialize(captures[identity],folder)
            command=[sys.executable,'-B',str(repository/'benchmarks/reporting/mpc08_explicit'/script)]
            command.extend([str(folder)] if label=='exact' else ['--recheck',str(folder)])
            checked=subprocess.run(command,cwd=repository,capture_output=True,text=True,timeout=30)
            require(checked.returncode==0,'saved '+label+' evidence recheck failed: '+checked.stderr[-2000:])
            checks[label]=json.loads(checked.stdout);require(checks[label]['status']=='checked','saved evidence is inconclusive')
    require(checks['exact']['native_observations']==360 and checks['exact']['support_observations']==432,'exact native inventory differs')
    counts={(r['horizon'],r['status']):r['count'] for r in checks['horizon']['native']['counts']}
    require(counts=={(2,'verified-complete-reduced-linear-family'):12,(2,'unsupported-original-quadratic-profile'):12,
                    (4,'resource-inconclusive-reduced-family'):12,(4,'unsupported-original-quadratic-profile'):12,
                    (8,'resource-inconclusive-reduced-family'):12,(8,'unsupported-original-quadratic-profile'):12},'horizon native disposition differs')
    return frozen_files,captures,checks


def source_export(captures):
    """Only objects needed for the two fixed source maps, never host Git config."""
    # Follow the parent owning these helper bytes; retain genuinely combined helper merges.
    revision=subprocess.check_output(
        ['git','log','-1','--format=%H','--',*HELPERS],
        cwd=ROOT,text=True).strip()
    files={}
    require(re.fullmatch('[0-9a-f]{40}',revision),'invalid current source revision')
    for name in HELPERS:
        data=(ROOT/name).read_bytes();committed=subprocess.check_output(['git','show','--end-of-options',revision+':'+name],cwd=ROOT)
        require(data==committed,'publication helper differs from committed source: '+name);files[name]=data
    files['.git/HEAD']=b'ref: refs/heads/evidence\n';files['.git/refs/heads/evidence']=(SPECS[EXACT_ID][1]+'\n').encode()
    files['.git/config']=b'[core]\nrepositoryformatversion = 0\nbare = false\n'
    objects=set()
    def include(oid):
        require(re.fullmatch('[0-9a-f]{40}',oid),'invalid source object identity')
        if oid in objects:return
        objects.add(oid);kind=subprocess.check_output(['git','cat-file','-t',oid],cwd=ROOT,text=True).strip()
        require(kind in ('commit','tree','blob'),'unsupported source object kind')
        content=subprocess.check_output(['git','cat-file',kind,oid],cwd=ROOT)
        raw=f'{kind} {len(content)}'.encode()+b'\0'+content
        require(hashlib.sha1(raw).hexdigest()==oid,'Git object SHA differs')
        files['.git/objects/'+oid[:2]+'/'+oid[2:]]=zlib.compress(raw)
    sources=[(revision,{name:digest(files[name]) for name in HELPERS})]
    sources.extend((SPECS[identity][1],json.loads(capture['manifest.json'])['source_sha256']) for identity,capture in captures.items())
    for commit,fingerprints in sources:
        include(commit)
        include(subprocess.check_output(['git','rev-parse',commit+'^{tree}'],cwd=ROOT,text=True).strip())
        for name,checksum in fingerprints.items():
            safe_name(name)
            data=subprocess.check_output(['git','show','--end-of-options',commit+':'+name],cwd=ROOT)
            require(digest(data)==checksum,'captured source fingerprint differs from Git')
            parts=PurePosixPath(name).parts
            for size in range(1,len(parts)+1):
                include(subprocess.check_output(['git','rev-parse',commit+':'+str(PurePosixPath(*parts[:size]))],cwd=ROOT,text=True).strip())
    return files,dict(helper_revision=revision,helper_sha256={n:digest(files[n]) for n in HELPERS},
                      object_count=len(objects),object_scope='only selected authentic commit/tree/blob objects; not a full checkout/history')


def verify_export(root,receipt):
    git=root/'.git'
    require((git/'config').read_bytes()==b'[core]\nrepositoryformatversion = 0\nbare = false\n' and (git/'HEAD').read_bytes()==b'ref: refs/heads/evidence\n' and (git/'refs/heads/evidence').read_bytes()==(SPECS[EXACT_ID][1]+'\n').encode(),'source proof configuration differs')
    object_paths=[]
    for path in git.rglob('*'):
        require(not path.is_symlink(),'source-proof symlink refused')
        if not path.is_file():continue
        name=path.relative_to(git).as_posix()
        if name in ('config','HEAD','refs/heads/evidence'):continue
        require(re.fullmatch(r'objects/[0-9a-f]{2}/[0-9a-f]{38}',name),'unexpected source-proof Git file')
        object_paths.append(path);packed=path.read_bytes();require(len(packed)<=2*1024**2,'source object compressed cap exceeded')
        decoder=zlib.decompressobj();raw=decoder.decompress(packed,2*1024**2+1)
        require(len(raw)<=2*1024**2 and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,'invalid/oversized source object')
        oid=path.parent.name+path.name;require(hashlib.sha1(raw).hexdigest()==oid,'source object SHA differs')
        header,body=raw.split(b'\0',1);match=re.fullmatch(rb'(commit|tree|blob) ([0-9]+)',header)
        require(match is not None and int(match[2])==len(body),'invalid source object header')
    require(len(object_paths)==receipt['object_count']<=128,'source object inventory differs')
    revision=receipt['helper_revision']
    require(isinstance(revision,str) and re.fullmatch('[0-9a-f]{40}',revision),'invalid exported helper revision')
    require(set(receipt['helper_sha256'])==set(HELPERS),'exported helper inventory differs')
    for name,checksum in receipt['helper_sha256'].items():
        data=(root/name).read_bytes()
        require(digest(data)==checksum,'exported helper fingerprint differs')
        committed=subprocess.check_output(['git','show','--end-of-options',revision+':'+name],cwd=root)
        require(committed==data,'exported helper differs from authentic Git object')


def minimal_inputs():
    return dict(state_dimension=2,state_coordinates=['position p','velocity v'],model=dict(A=[[1,1],[0,1]],B=[[0],[1]]),
        original_quadratic=dict(initial_parameter_box=[[-3,3],[-2,2]],control_box=[-1,1],horizons=[1,2,4,8],
            terminal_H=[[1,1],[-1,-1],[1,2],[-1,-2]],terminal_upper=[1,1,1,1],objective='pN^2+vN^2; no running cost',
            intermediate_states='unconstrained',minimal_initial=[0,0],N1_answer=dict(first_action=0,value=0),
            complete_control_fiber='-1<=uj<=1; sum((N-1-j)*uj)=zstar_p-p0-N*v0; sum(uj)=zstar_v-v0'),
        robust_predecessor=dict(disturbance_direction=[0,1],disturbance_interval=['-1/8','1/8'],quantifiers='exists u forall w',
            invariant_policy=[-1,-2],robust_terminal_s_bound='3/4',robust_terminal_t_bound=1),
        separate_nonunique_velocity_variant=dict(horizon=2,objective='v2^2',terminal_set='none',selector='u0=u1=-v0/2; selector only',
            complete_control_fiber='u0 in [-1,1] intersect [-v0-1,-v0+1]; u1=-v0-u0'))


def _json(value):return (json.dumps(value,indent=2,sort_keys=True)+'\n').encode()


def _page(route):
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MPC08 exact regions and optimizer fibers</title>
<style>body{{font:16px/1.6 system-ui;background:#1e1e2e;color:#cdd6f4;max-width:1200px;margin:2rem auto;padding:1rem}}a{{color:#89b4fa}}h1,h2{{color:#a6e3a1}}img{{max-width:100%;height:auto}}code{{color:#f9e2af}}table{{display:block;overflow:auto}}th,td{{text-align:left;padding:.4rem}}</style><body>
<h1>Exact MPC regions, matched predecessors and whole optimizer fibers</h1>
<p>Two-state double integrator; N=1/2/4/8. These are initial-state parameter sets, not forward reachable sets or general feedback winning sets. The original objective is terminal-only pN²+vN², with the same X, U and terminal T; intermediate states are unconstrained. Performance verdict: <strong>inconclusive</strong>.</p>
<p><a href="minimal-inputs.json">Complete minimal inputs</a> · <a href="verification.json">Current saved-data checks</a> · <a href="publication-manifest.json">Source and archive identities</a> · <a href="../{route}.zip">Complete offline source/raw/figure ZIP</a> · <a href="README.md">Offline recheck instructions</a></p>
<section id="minimal-example"><h2>One initial point and four different products</h2><p>Use x=(p,v), x_next=(p+v,v+u), |u|≤1, X=[−3,3]×[−2,2], and T={{|p+v|≤1, |p+2v|≤1}}. At x0=(0,0), N=1 has u*=0 and value0. F describes feasible initial states; T is a separately invariant terminal set under u=−p−2v; the parametric action/value map describes one x0 at a time; the complete optimizer fiber retains every optimal control/history for that x0.</p>
<img src="figures/exact-critical-regions.svg" alt="Nine N1 initial-state critical regions, separate terminal sets and labelled nominal/robust predecessor inclusions">
<p>N=1 has nine exact action/value regions and22 shared boundaries, covering feasible area21/2. Exact whole-H checks reject recession directions before finite-vertex reasoning. Seven whole-set inclusions preserve exists-u/forall-w order for the robust curves. T is nominally invariant; the smaller T_robust is invariant for all velocity disturbances in [−1/8,1/8]. Inner/outer target boxes have containment directions, not invariant-box claims. Original T's robust counterexample is retained.</p></section>
<h2>Matched horizons and the complete original-quadratic relation</h2>
<img src="figures/horizon-regions.svg" alt="Matched N2/N4/N8 exact initial-state endpoint-map partitions with9/7/1 labelled cells">
<p>Exact endpoint-map cell counts are9/7/1 and feasible areas47/3,23,24. Region counts decrease here; no region explosion is observed. These are endpoint cells, not a claimed minimal/maximal first-action partition. Strict convexity makes the optimal endpoint z* unique. It does not make controls unique: the complete original optimizer relation is the box slice <code>D_N u=z*(x0)−A^N x0</code>, with column j of D_N equal to (N−1−j,1); intermediate states follow from dynamics. A selected first action or minimum-norm history is a different product.</p>
<table><tr><th>Actual public CSL request</th><th>Retained outcomes, including warmups</th></tr><tr><td>Original quadratic exact-family profile</td><td>36 explicit preparation refusals</td></tr><tr><td>Endpoint-fixed zero-linear-cost reduction, N=2</td><td>12 registry-verified complete H-relations, independently compared to the entire expected history/control relation</td></tr><tr><td>Same reduction, N=4/8</td><td>24 resource-inconclusive outcomes: exact-H row or arithmetic budget</td></tr></table>
<p>The reduction uses the six dyadic parameters (p,v)=(0,0),(1,0) at each horizon, where z*=0. Its equivalence follows from the separate whole-domain original-quadratic proof. This grants no general CSL quadratic complete-family capability. The earlier separate N=2 velocity-only example has a different objective/no T and retains its full fiber separately from u0=u1=−v0/2. Fixed-v fiber vertex growth and N=16 output-cap refusal are not critical-region growth.</p>
<h2>Read the raw records and cost scopes</h2><p>The first capture retains360 strategy/QP observations and432 public-LP support witnesses. Candidate membership and numerical support samples do not prove whole-family equality or whole-set containment; the rational proofs are separate. Offline construction/check intervals, serialized sizes/H rows/polygon edges, actual location/evaluation batches, native per-state spans, warmups and failures remain distinct. Storage is not peak Python working memory; native wait4 RSS covers the direct child. Fresh client compilation uses explicitly hash-bound reused static libraries. No ranking, native-limiter, hard-real-time or portable-binary claim.</p>
<p><a href="evidence/{EXACT_ID}/README.md">N=1/predecessor scope</a> · <a href="evidence/{EXACT_ID}/capture.zip">Original immutable first ZIP</a> · <a href="evidence/{HORIZON_ID}/README.md">Matched-horizon scope</a> · <a href="evidence/{HORIZON_ID}/capture.zip">Original immutable horizon ZIP</a> · <a href="captures/exact/exact-reference.json">Complete first exact inputs</a> · <a href="captures/horizon/reference.json">Complete horizon H/V/maps/fibers/costs</a></p>
<p>This authored fixture is not a port/reproduction of corrected Bemporad Example7.1. MPT3's GPL version and MATLAB/toolbox terms remain qualified; no MPT/MATLAB installation or execution is required. The optional publication changes no public C++ API, required dependency or installed package: no release needed. Local staging is not deployment; current review/CI, main-only freshness and live URL/hash checks remain delivery gates.</p></body></html>'''.encode()


def _example_card(site,identity,card):
    path=site/'examples/index.html';page=path.read_text();require(page.count('</body>')==1,'gallery insertion point differs')
    path.write_text(page.replace('</body>',card+'</body>'))


def stage(site,exact_source=EXACT_SOURCE,horizon_source=HORIZON_SOURCE,*,example_card_writer=None):
    site=Path(site);require(site.is_dir() and not site.is_symlink(),'site must be a regular directory')
    for path in (site/'index.html',site/'examples',site/'examples/index.html'):
        require(not path.is_symlink(),'symlink site destination refused')
    landing=(site/'index.html').read_text();gallery=(site/'examples/index.html').read_text()
    require(landing.count('</body>')==1 and gallery.count('</body>')==1,'site insertion points differ')
    frozen_files,captures,checks=validate(exact_source,horizon_source)
    helpers,source_receipt=source_export(captures)
    generated={f'evidence/{identity}/{name}':data for identity,files in frozen_files.items() for name,data in files.items()}
    generated.update({f'captures/{label}/{name}':data for label,identity in (('exact',EXACT_ID),('horizon',HORIZON_ID)) for name,data in captures[identity].items()})
    offline_objects={'source-root/'+name:data for name,data in helpers.items() if name.startswith('.git/')}
    generated.update({'source-root/'+name:data for name,data in helpers.items() if not name.startswith('.git/')})
    generated['source-files.json']=_json(source_receipt);generated['minimal-inputs.json']=_json(minimal_inputs());generated['verification.json']=_json(checks)
    generated['figures/exact-critical-regions.svg']=captures[EXACT_ID]['critical-regions.svg'];generated['figures/exact-critical-regions.png']=captures[EXACT_ID]['critical-regions.png']
    generated['figures/horizon-regions.svg']=captures[HORIZON_ID]['horizon-regions.svg'];generated['figures/horizon-regions.png']=captures[HORIZON_ID]['horizon-regions.png']
    identity=digest(_json({name:digest(data) for name,data in sorted((generated|offline_objects).items())}))[:20];route='mpc08-complete-'+identity
    require(not any(p.exists() or p.is_symlink() for p in (site/route,site/(route+'.zip'))) and route not in landing and route not in gallery,'immutable MPC08 route already exists')
    generated['index.html']=_page(route)
    generated['offline_check.py']=f'''"""Saved-only offline checks; no native executable, optimizer or renderer."""
from pathlib import Path
import importlib.util,json
root=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('mpc08_offline',root/'source-root/scripts/reports/stage_mpc08_complete.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.verify_export(root/'source-root',json.loads((root/'source-files.json').read_bytes()))
_,_,checks=module.validate(root/'evidence/{EXACT_ID}',root/'evidence/{HORIZON_ID}',repository=root/'source-root')
print(json.dumps(checks))
'''.encode()
    generated['README.md']=f'''# Bounded MPC08 source/raw publication

Two frozen captures remain byte-preserved under evidence/. Their capture source
commits are {SPECS[EXACT_ID][1]} and {SPECS[HORIZON_ID][1]}.
Current saved-only checks and helper fingerprints are separate in verification.json
and source-files.json. Open index.html for labelled 2D figures and minimal inputs.

After downloading/extracting ../{route}.zip into a fresh directory, enter this
route and run:

```sh
sha256sum -c OFFLINE_SHA256SUMS
python3 -B offline_check.py
```

This needs Python3.11+ and Git, with no solver, Matplotlib, native binary, network
or existing source checkout. Inside the offline ZIP only, source-root/.git contains fresh fixed
configuration and only authentic commit/tree/blob objects needed by the original
full-commit git-show checks. It contains no host config, credentials, hooks or
complete repository history. Missing objects/source mismatches refuse the check;
there is no weaker cached-check fallback. This object store is not a full checkout.

The native process paths/compiler/library receipts are historical evidence, not
portable commands or redistributed binaries. Actual original-quadratic request
refusals, reduced-linear complete families and resource stops remain separate.
All optional plotting/native reproduction sources are included; reproducing native
runs additionally requires the normal reviewed CSL/backend build. No timing ranking,
MPT execution, new public API/required dependency or library release is claimed.

Only the existing current-main CI/freshness workflow may deploy this staged route.
Local source/HTML validation alone does not establish live publication or #604 closure.
'''.encode()
    manifest=dict(schema='csl.mpc08.publication/1',report_id=route,source_receipt=source_receipt,verification=checks,
        offline_only_source_objects={name:digest(data) for name,data in sorted(offline_objects.items())},
        reviewed_reports={identity:dict(manifest_sha256=SPECS[identity][0],capture_source=SPECS[identity][1],capture_zip_sha256=digest(files['capture.zip'])) for identity,files in frozen_files.items()},
        published_files={name:digest(data) for name,data in sorted(generated.items())})
    generated['publication-manifest.json']=_json(manifest)
    generated['OFFLINE_SHA256SUMS']=''.join(digest(data)+'  '+name+'\n' for name,data in sorted((generated|offline_objects).items())).encode()
    generated['SHA256SUMS']=''.join(digest(data)+'  '+name+'\n' for name,data in sorted(generated.items())).encode()
    card=f'<article id="{route}-example"><h3><a href="../{route}/index.html#minimal-example">Exact MPC regions, robust predecessors and whole optimizer fibers</a></h3><a href="../{route}/index.html#minimal-example"><img src="../{route}/figures/exact-critical-regions.svg" alt="Two-state exact critical regions and labelled nominal/robust predecessors"></a><p>Matched terminal-only N=1/2/4/8; complete minimal inputs, full control fibers, actual public solver refusals and saved checks.</p><p><a href="../{route}.zip">Complete offline source/raw/figure ZIP</a></p></article>'
    with tempfile.TemporaryDirectory(prefix='mpc08-publication-stage-') as temporary:
        scratch=Path(temporary);(scratch/'examples').mkdir();(scratch/'index.html').write_text(landing);(scratch/'examples/index.html').write_text(gallery)
        link=f'<section id="{route}"><h2>Exact MPC sets and optimizer fibers</h2><p><a href="{route}/index.html">Read the bounded comparison and minimal 2D examples</a> · <a href="{route}.zip">Download complete offline evidence</a>.</p></section>'
        (scratch/'index.html').write_text(landing.replace('</body>',link+'</body>'))
        (example_card_writer or _example_card)(scratch,route+'-example',card)
        staged_gallery=(scratch/'examples/index.html').read_text();require(route+'/index.html#minimal-example' in staged_gallery,'gallery writer dropped discovery link')
        materialize(generated,scratch/route)
        with zipfile.ZipFile(scratch/(route+'.zip'),'w',zipfile.ZIP_DEFLATED) as archive:
            for name,data in sorted((generated|offline_objects).items()):
                safe_name(name);entry=zipfile.ZipInfo(route+'/'+name,date_time=(2026,1,1,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED;entry.external_attr=0o100644<<16;archive.writestr(entry,data)
        materialize(generated,site/route)
        with (site/(route+'.zip')).open('xb') as output:output.write((scratch/(route+'.zip')).read_bytes())
        (site/'index.html').write_bytes((scratch/'index.html').read_bytes());(site/'examples/index.html').write_text(staged_gallery)
    return route


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--site',required=True,type=Path);parser.add_argument('--exact-source',type=Path,default=EXACT_SOURCE);parser.add_argument('--horizon-source',type=Path,default=HORIZON_SOURCE);args=parser.parse_args();print(stage(args.site,args.exact_source,args.horizon_source))
