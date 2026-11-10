"""Stage immutable MPC10 evidence and a separate checked reading layer; no solves."""
from __future__ import annotations
import argparse
import copy
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
import zipfile
import zlib

ROOT=Path(__file__).resolve().parents[2]
PREFIX='benchmarks/reporting/mpc10/'
FROZEN=ROOT/PREFIX/'evidence/comparison-525871ea'
READING=ROOT/PREFIX/'evidence/publication-reading-v1'
FROZEN_SHA='b41039541c43f6d563752d92aab13ced6b9a49f90ebe745cdb118c8f0074b887'
READING_SHA='3817decb10d40d85b2ee628c26f1222e5009a477eeeee11b149dba9f1a19a39b'
HELPERS=[PREFIX+name for name in ('check.py','evidence.py','figures.py','fixtures.py','metrics.py','oracle.py','run.py','scip_reference.py','bridge.cpp','CMakeLists.txt')]+['scripts/reports/figure_style.py','scripts/reports/plot.py','scripts/reports/stage_mpc10_comparison.py']


def digest(data):return hashlib.sha256(data).hexdigest()
def encoded(value):return (json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n').encode()
def require(condition,message):
    if not condition:raise ValueError(message)


def safe(name):
    path=PurePosixPath(name)
    require(bool(name) and not path.is_absolute() and path.as_posix()==name and all(re.fullmatch('[A-Za-z0-9_.-]+',p) and p not in ('.','..') for p in path.parts),'unsafe publication path')
    return path


def sums(data):
    result={}
    for line in data.decode('ascii').splitlines():
        match=re.fullmatch(r'([0-9a-f]{64})  (.+)',line);require(match is not None,'invalid inventory line')
        name=match[2];safe(name);require(name not in result,'duplicate inventory path');result[name]=match[1]
    require(result,'empty inventory');return result


def reviewed(folder,expected):
    require(folder.is_dir() and not folder.is_symlink(),'not a regular evidence directory')
    paths=list(folder.iterdir());require(all(p.is_file() and not p.is_symlink() for p in paths),'evidence must be flat regular files')
    files={p.name:p.read_bytes() for p in paths}
    require('SHA256SUMS' in files and digest(files['SHA256SUMS'])==expected,'not the reviewed evidence inventory')
    require(sums(files['SHA256SUMS'])=={n:digest(v) for n,v in files.items() if n!='SHA256SUMS'},'evidence inventory differs')
    return files


def capture_files(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries=archive.infolist();names=[e.filename for e in entries]
        require(len(names)==len(set(names)) and len(names)<=5000,'archive member inventory differs')
        require(sum(e.file_size for e in entries)<=64*1024**2,'archive expansion cap exceeded')
        for entry in entries:
            safe(entry.filename)
            require(not entry.is_dir() and stat.S_IFMT(entry.external_attr>>16) in (0,stat.S_IFREG) and not entry.flag_bits&1 and entry.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED),'unsupported archive member')
        files={e.filename:archive.read(e) for e in entries}
    require(sums(files['SHA256SUMS'])=={n:digest(v) for n,v in files.items() if n!='SHA256SUMS'},'archive inventory differs')
    capture={n.removeprefix('capture/'):v for n,v in files.items() if n.startswith('capture/')}
    require(len(capture)==1036,'capture input count differs')
    return capture


def materialize(files,folder):
    folder.mkdir(parents=True,exist_ok=False)
    for name,data in files.items():
        target=folder.joinpath(*safe(name).parts);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)


def source_export(capture,checking=None):
    revision=subprocess.check_output(['git','log','--first-parent','--full-history','-1','--format=%H','--',*HELPERS],cwd=ROOT,text=True).strip()
    require(re.fullmatch('[0-9a-f]{40}',revision),'invalid helper source revision')
    files={};objects=set()
    for name in HELPERS:
        files[name]=(ROOT/name).read_bytes()
        require(files[name]==subprocess.check_output(['git','show','--end-of-options',revision+':'+name],cwd=ROOT),'publication helper differs from committed source: '+name)
    environment=json.loads(capture['environment.json']);captured=environment['source_revision']
    require(re.fullmatch('[0-9a-f]{40}',captured),'invalid capture revision')
    checking=checking or dict(checking_revision=captured,checking_sources={})
    checked=checking['checking_revision'];require(isinstance(checked,str) and re.fullmatch('[0-9a-f]{40}',checked),'invalid checking revision')
    files['.git/HEAD']=b'ref: refs/heads/evidence\n';files['.git/refs/heads/evidence']=(checked+'\n').encode();files['.git/config']=b'[core]\nrepositoryformatversion = 0\nbare = false\n'
    def include(oid):
        require(re.fullmatch('[0-9a-f]{40}',oid),'invalid source object')
        if oid in objects:return
        objects.add(oid);kind=subprocess.check_output(['git','cat-file','-t',oid],cwd=ROOT,text=True).strip()
        require(kind in ('commit','tree','blob'),'unsupported source object kind')
        content=subprocess.check_output(['git','cat-file',kind,oid],cwd=ROOT);raw=f'{kind} {len(content)}'.encode()+b'\0'+content
        require(hashlib.sha1(raw).hexdigest()==oid,'source object SHA differs');files['.git/objects/'+oid[:2]+'/'+oid[2:]]=zlib.compress(raw)
    sources=[(revision,{n:digest(files[n]) for n in HELPERS}),(captured,{PREFIX+n:v for n,v in environment['source_sha256'].items()}),(checked,{PREFIX+n:v for n,v in checking['checking_sources'].items()})]
    for commit,fingerprints in sources:
        include(commit);include(subprocess.check_output(['git','rev-parse',commit+'^{tree}'],cwd=ROOT,text=True).strip())
        for name,checksum in fingerprints.items():
            parts=safe(name).parts;data=subprocess.check_output(['git','show','--end-of-options',commit+':'+name],cwd=ROOT)
            require(digest(data)==checksum,'source fingerprint differs from authentic object')
            for size in range(1,len(parts)+1):include(subprocess.check_output(['git','rev-parse',commit+':'+PurePosixPath(*parts[:size]).as_posix()],cwd=ROOT,text=True).strip())
    return files,dict(helper_revision=revision,helper_sha256={n:digest(files[n]) for n in HELPERS},capture_revision=captured,checking_revision=checked,object_count=len(objects))


def verify_source(root,receipt):
    git=root/'.git';require((git/'config').read_bytes()==b'[core]\nrepositoryformatversion = 0\nbare = false\n' and (git/'HEAD').read_bytes()==b'ref: refs/heads/evidence\n' and (git/'refs/heads/evidence').read_bytes()==(receipt['checking_revision']+'\n').encode(),'source proof configuration differs')
    objects=[]
    for path in git.rglob('*'):
        require(not path.is_symlink(),'source proof symlink refused')
        if not path.is_file():continue
        name=path.relative_to(git).as_posix()
        if name in ('config','HEAD','refs/heads/evidence'):continue
        require(re.fullmatch(r'objects/[0-9a-f]{2}/[0-9a-f]{38}',name),'unexpected source proof file')
        packed=path.read_bytes();require(len(packed)<=2*1024**2,'oversized source object')
        decoder=zlib.decompressobj();raw=decoder.decompress(packed,2*1024**2+1)
        require(len(raw)<=2*1024**2 and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,'invalid source object')
        require(hashlib.sha1(raw).hexdigest()==path.parent.name+path.name,'source object SHA differs')
        header,body=raw.split(b'\0',1);match=re.fullmatch(rb'(commit|tree|blob) ([0-9]+)',header)
        require(match is not None and int(match[2])==len(body),'invalid source object header');objects.append(path)
    require(len(objects)==receipt['object_count']<=128,'source object inventory differs')
    revision=receipt['helper_revision'];require(isinstance(revision,str) and re.fullmatch('[0-9a-f]{40}',revision),'invalid helper revision')
    require(set(receipt['helper_sha256'])==set(HELPERS),'helper inventory differs')
    for name,checksum in receipt['helper_sha256'].items():
        data=(root/name).read_bytes();require(digest(data)==checksum,'helper fingerprint differs')
        require(data==subprocess.check_output(['git','show','--end-of-options',revision+':'+name],cwd=root),'helper differs from authentic Git object')


def metrics_agree(saved,rebuilt):
    """Allow accumulation rounding only in the four derived nonnegative sums.

    Python3.12 changed sum(float). Each sum has a known number of nonnegative
    terms; four ULPs per term covers sequential versus compensated accumulation.
    The frozen reading bytes remain the published authority, never this rebuild.
    """
    if not isinstance(saved,dict) or not isinstance(rebuilt,dict):return False
    if not isinstance(saved.get('cases'),list) or not isinstance(rebuilt.get('cases'),list):return False
    if len(saved['cases'])!=len(rebuilt['cases']):return False
    normalized=copy.deepcopy(rebuilt)
    for expected,observed in zip(saved['cases'],normalized['cases']):
        if not isinstance(expected,dict) or not isinstance(observed,dict):return False
        groups=(('native_seconds',('native_lp_load_sum','native_lp_solve_sum'),expected.get('native_branches')),
                ('scip_fixed_branch_totals',('formulation_and_setup_seconds','optimization_seconds'),expected.get('scip_fixed_branch_totals',{}).get('count')))
        for group,names,count in groups:
            if type(count) is not int or count<0 or not isinstance(expected.get(group),dict) or not isinstance(observed.get(group),dict):return False
            for name in names:
                if name not in expected[group] or name not in observed[group]:return False
                left,right=expected[group][name],observed[group][name]
                if left is None or right is None:
                    if left is not right:return False
                else:
                    if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in (left,right)):return False
                    if count==0 or left==0 or right==0:
                        if left!=right:return False
                    elif abs(left-right)>4*count*max(math.ulp(left),math.ulp(right)):return False
                observed[group][name]=left
    return saved==normalized


def validate(frozen=FROZEN,reading=READING,*,repository=ROOT):
    original=reviewed(Path(frozen),FROZEN_SHA);current=reviewed(Path(reading),READING_SHA);capture=capture_files(original['capture.zip'])
    with tempfile.TemporaryDirectory(prefix='mpc10-publication-check-') as temporary:
        folder=Path(temporary);materialize(capture,folder/'capture');(folder/'verification.json').write_bytes(current['verification.json'])
        command=[sys.executable,'-B','-c',"import json,sys; from pathlib import Path; from benchmarks.reporting.mpc10.evidence import checked_verification; from benchmarks.reporting.mpc10.metrics import metrics; b=Path(sys.argv[1]); v=Path(sys.argv[2]); checked_verification(b,v); print(json.dumps(metrics(b,v),sort_keys=True))",str(folder/'capture'),str(folder/'verification.json')]
        result=subprocess.run(command,cwd=repository,capture_output=True,text=True,timeout=30)
        require(result.returncode==0,'saved bindings/metrics check failed: '+result.stderr[-2000:])
        require(metrics_agree(json.loads(current['metrics.json']),json.loads(result.stdout)),'current metrics differ from checked raw inputs')
    receipt=json.loads(current['verification.json']);rows=json.loads(current['metrics.json'])['cases']
    require(len(receipt['reports'])==len(rows)==26,'case count differs')
    require(sum(r['native_branches'] for r in rows)==119,'native LP count differs')
    require(sum(r['scip_global'] is not None for r in rows)==24 and sum(r['scip_fixed_branch_totals']['count'] for r in rows)==131,'SCIP attempt count differs')
    require(json.loads(original['figure-export.json'])['figures']=={n:digest(original[n]) for n in ('paths.svg','paths.png','branches.svg','branches.png')},'frozen figure identity differs')
    return original,current,capture,rows


def offline_check(folder,*,full=False):
    receipt=json.loads((folder/'source-files.json').read_bytes());verify_source(folder/'source-root',receipt)
    _,_,capture,_=validate(folder/'original',folder/'reading',repository=folder/'source-root')
    if full:
        with tempfile.TemporaryDirectory(prefix='mpc10-full-offline-check-') as temporary:
            materialize(capture,Path(temporary)/'capture')
            command=[sys.executable,'-B','-m','benchmarks.reporting.mpc10.check','--bundle',str(Path(temporary)/'capture'),'--output',str(Path(temporary)/'verification.json')]
            subprocess.run(command,cwd=folder/'source-root',check=True,timeout=120)
            require(json.loads((Path(temporary)/'verification.json').read_bytes())==json.loads((folder/'reading/verification.json').read_bytes()),'full saved check differs from published receipt')
    return dict(status='checked',cases=26,native_LPs=119,SCIP_global=24,SCIP_fixed=131,interrupted=1,scope='full saved model/row/oracle recheck' if full else 'source, raw/receipt and metrics bindings; use --full for saved mathematical/model recheck')


def page(route,rows):
    def proof(row):
        value=row['native_core_family_verification']
        return 'not supplied' if value is None else 'optimality='+str(value['global_optimality'])+', coverage='+str(value['continuous_coverage'])
    table=''.join(f"<tr><td>{r['id']}</td><td>{r['native_status']}</td><td>{r['native_branches']}</td><td>{r['exact_optimum']}</td><td>{r['all_tie_count']}</td><td>{proof(r)}</td></tr>" for r in rows)
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MPC10 finite, mixed and hybrid comparison</title><style>body{{font:16px/1.6 system-ui;background:#1e1e2e;color:#cdd6f4;max-width:1100px;margin:auto;padding:2rem}}a{{color:#89b4fa}}h1,h2{{color:#a6e3a1}}img{{max-width:100%}}table{{display:block;overflow:auto}}td,th{{text-align:left;padding:.3rem}}</style><body><h1>Finite actions, mixed controls and hybrid paths</h1><p>26 bounded nominal fixtures, horizons0–3, physical dimension2 with the exact invariant y=0: one active scalar coordinate. Actual public CSL construction/native LPs and an independent SCIP one-hot/indicator encoding. No guessed big-M. Performance verdict: inconclusive; these single configured observations establish no timing ranking or general scalability result.</p><p><a href="../{route}.zip">Complete offline source/raw/figure ZIP</a> · <a href="minimal-inputs.json">All complete minimal fixtures</a> · <a href="reading/verification.json">Current saved checks</a> · <a href="reading/metrics.json">All scoped clocks/counts</a> · <a href="publication-manifest.json">Publication identities</a> · <a href="README.md">Offline instructions</a></p><section id="minimal-example"><h2>Supported two-dimensional example and parallel ties</h2><p>Start at(-1,0), flow(x+u,y), u=1, then an explicit identity-switch edge reaches(0,0); terminal cost is x. The second example applies its source invariant before and after flow, a guard before reset x⁺=1−x⁻, and the destination invariant after reset. Parallel edge identities remain separate at the tied optimum1/2.</p><img src="figures/paths.svg" alt="Actual saved two-dimensional source flow and post-reset anchors"><img src="figures/branches.svg" alt="Two separate parallel optimal edges with guard/reset timing"></section><h2>Observed products and proof limits</h2><p>119 native fixed-branch LPs,24 unrestricted SCIP models,131 additional fixed-history models and one actual node-limit stop. Exact independent interval propagation and reconstructed whole LP rows establish bounded feasibility/minima/tie inventories. One-step/flat continuous families have actual CSL exact-H verification; T=2/3 inclusion proofs remain unsupported. Independent candidate-face row checks and numerical SCIP incumbents are separate products. Unknown bounds/gaps, refusals, cancellation and incomplete prefixes are retained. Core proof states below preserve the actual enum values:0 not checked,1 established,2 refuted,3 unsupported. A SCIP point is never a complete continuous family.</p><table><tr><th>Fixture</th><th>Native outcome</th><th>LP branches</th><th>Exact value</th><th>Tied histories</th><th>Actual core proof states</th></tr>{table}</table><p>Setup, enumeration, formulation, native LP load/run, family verification, unrestricted SCIP setup/optimization, extra fixed-history checks, process CPU/RSS and offline checks have separate or nested scopes in the raw records. No observed timing ratios are claimed. Original pre-fix T3 evidence and every engineering failure remain archived; qualified measurements retain their actual capture source.</p><p>Linux/GCC Release and existing optional HiGHS/PySCIPOpt6.3/SCIP10.0.2 are qualified. No Windows/macOS benchmark, redistributed solver binary, new required dependency/API or library release. Saved figures use Matplotlib3.11.2/shared style; staging needs only Python/Git. Full offline saved checking additionally uses the existing qualified PySCIPOpt environment and rebuilds models without optimization. No acados/MATLAB/MPT.</p><p><a href="original/README.md">Immutable capture scope, licenses and build qualification</a>. Local staging is not deployment. Current review/CI, main-only freshness, live URL/hash checks and independent completion audit remain delivery gates.</p></body></html>'''.encode()


def stage(site,*,example_card_writer=None):
    site=Path(site);require(site.is_dir() and not site.is_symlink(),'site must be a regular directory')
    for name in ('index.html','examples','examples/index.html'):require(not (site/name).is_symlink(),'site symlink refused')
    landing=(site/'index.html').read_text();gallery=(site/'examples/index.html').read_text();require(landing.count('</body>')==gallery.count('</body>')==1,'site insertion points differ')
    original,reading,capture,rows=validate();source,source_receipt=source_export(capture,json.loads(reading['verification.json']))
    files={'original/'+n:v for n,v in original.items()}|{'reading/'+n:v for n,v in reading.items()}|{'source-root/'+n:v for n,v in source.items() if not n.startswith('.git/')}
    objects={'source-root/'+n:v for n,v in source.items() if n.startswith('.git/')}
    files['source-files.json']=encoded(source_receipt)
    files['minimal-inputs.json']=encoded([json.loads(v) for n,v in sorted(capture.items()) if n.endswith('/fixture.json')])
    files.update({'figures/'+n:original[n] for n in ('paths.svg','paths.png','branches.svg','branches.png')})
    route='mpc10-comparison-'+digest(encoded({n:digest(v) for n,v in sorted((files|objects).items())}))[:20]
    require(not any(p.exists() or p.is_symlink() for p in (site/route,site/(route+'.zip'))) and route not in landing and route not in gallery,'immutable MPC10 route already exists')
    files['index.html']=page(route,rows)
    files['offline_check.py']=b"from pathlib import Path\nimport importlib.util,json,sys\nr=Path(__file__).resolve().parent\ns=importlib.util.spec_from_file_location('publication',r/'source-root/scripts/reports/stage_mpc10_comparison.py')\nm=importlib.util.module_from_spec(s);s.loader.exec_module(m)\nprint(json.dumps(m.offline_check(r,full='--full' in sys.argv)))\n"
    files['README.md']=f'''# MPC10 complete offline evidence

Original immutable capture and figures remain byte-preserved under original/.
The strengthened current checking/metrics receipt is a separate reading layer.
Authentic minimal Git objects are inside the ZIP only, under source-root/.git;
this is not a full checkout/history and includes no host configuration/hooks.

Extract ../{route}.zip into a fresh directory and enter this report folder:

```sh
sha256sum -c OFFLINE_SHA256SUMS
python3 -B offline_check.py
<QUALIFIED_SCIP_PYTHON> -B offline_check.py --full
```

The first command needs Python3.11+ and Git only and checks authentic helper and
capture-source identities, all raw/current-receipt bindings and derived metrics.
The --full command additionally needs PySCIPOpt6.3.0/SCIP10.0.2: it independently
rechecks the exact oracle/whole LP rows, ties, raw responses/solutions and rebuilds
SCIP indicator models for byte comparison. It performs NO optimization or native
execution. It works outside a source checkout without a network. Missing source
objects refuse validation; no cached-success fallback exists. Matplotlib is not
needed for saved checking. Optional figure reproduction requires the qualified
Matplotlib3.11.2 environment; native reproduction requires the normal reviewed
CSL/backend build. Historical binary paths are evidence, not portable commands.

119 native LPs,24 unrestricted SCIP models,131 fixed-history solves and one
node-limit attempt remain separate. All26 fixtures and failed/unsupported/raw
attempts are retained. Continuous proof statuses and numerical witnesses remain
separate; descriptive one-observation clocks support no performance ranking.
Staging is not deployment. Managed current-main CI and live verification remain
required before any issue completion. No API/package/release change is introduced.
'''.encode()
    files['publication-manifest.json']=encoded(dict(schema='csl.mpc10.publication/1',report_id=route,source_receipt=source_receipt,original_inventory_sha256=FROZEN_SHA,reading_inventory_sha256=READING_SHA,published_files={n:digest(v) for n,v in sorted(files.items())},offline_only_source_objects={n:digest(v) for n,v in sorted(objects.items())}))
    files['OFFLINE_SHA256SUMS']=''.join(digest(v)+'  '+n+'\n' for n,v in sorted((files|objects).items())).encode();files['SHA256SUMS']=''.join(digest(v)+'  '+n+'\n' for n,v in sorted(files.items())).encode()
    link=f'<section id="{route}"><h2>Finite, mixed and hybrid MPC comparison</h2><p><a href="{route}/index.html">Read the bounded comparison and complete minimal examples</a> · <a href="{route}.zip">Download offline evidence</a></p></section>'
    card=f'<article id="{route}-example"><h3><a href="../{route}/index.html#minimal-example">Finite actions, guarded hybrid paths and parallel ties</a></h3><img src="../{route}/figures/paths.svg" alt="Actual two-dimensional hybrid flow/reset anchors"><p>All26 bounded nominal fixtures; complete raw/source/offline download and explicit proof limits.</p></article>'
    with tempfile.TemporaryDirectory(prefix='mpc10-publication-stage-') as temporary:
        scratch=Path(temporary);(scratch/'examples').mkdir();(scratch/'examples/index.html').write_text(gallery)
        if example_card_writer:example_card_writer(scratch,route+'-example',card)
        else:(scratch/'examples/index.html').write_text(gallery.replace('</body>',card+'</body>'))
        updated=(scratch/'examples/index.html').read_text();require(route+'/index.html#minimal-example' in updated,'gallery writer dropped link')
        materialize(files,scratch/route)
        with zipfile.ZipFile(scratch/(route+'.zip'),'w',zipfile.ZIP_DEFLATED) as archive:
            for name,data in sorted((files|objects).items()):
                safe(name);entry=zipfile.ZipInfo(route+'/'+name,date_time=(2026,1,1,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED;entry.external_attr=0o100644<<16;archive.writestr(entry,data)
        materialize(files,site/route)
        with (site/(route+'.zip')).open('xb') as output:output.write((scratch/(route+'.zip')).read_bytes())
        (site/'index.html').write_text(landing.replace('</body>',link+'</body>'));(site/'examples/index.html').write_text(updated)
    return route


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--site',type=Path,required=True);args=parser.parse_args();print(stage(args.site))
