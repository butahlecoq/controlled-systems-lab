"""Optional immutable MPC06 offline-cost extension; no solver or measurement."""
from __future__ import annotations
import argparse
import hashlib
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
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.reports.mpc06_offline import study
SOURCE=ROOT/'reports/algorithm-results/mpc06-offline-costs-8f58473d-20261110'
ANCHOR='4a6572d0fb95f7e95d1e93df79e2f81f03e31f4a74440c7a896df489f1705349'
FIGURE='reports/algorithm-results/mpc06-completion-v2/invariant-tightenings.svg'
FIGURE_SHA='a41340078df2332822e201f6529f4bb9ad49c3182a451cd33d47c6522a5a9ebe'
HELPERS=tuple(study.FILES)+('scripts/reports/stage_mpc06_offline_costs.py',FIGURE)
def require(condition,message):
    if not condition:raise ValueError(message)
def digest(data):return hashlib.sha256(data).hexdigest()
def encoded(value):return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def safe(name):
    p=PurePosixPath(name);require(bool(name) and not p.is_absolute() and p.as_posix()==name and all(re.fullmatch('[A-Za-z0-9_.-]+',n) and n not in ('.','..') for n in p.parts),'unsafe publication path');return p

def sums(data):
    values={}
    for line in data.decode('ascii').splitlines():
        m=re.fullmatch(r'([0-9a-f]{64})  (.+)',line);require(m is not None,'invalid checksum line');safe(m[2]);require(m[2] not in values,'duplicate checksum path');values[m[2]]=m[1]
    require(values,'empty checksum inventory');return values

def frozen(source):
    source=Path(source);require(source.name==SOURCE.name and source.is_dir() and not source.is_symlink(),'unexpected evidence directory')
    paths=list(source.iterdir());require(all(p.is_file() and not p.is_symlink() for p in paths),'flat regular evidence required');files={p.name:p.read_bytes() for p in paths}
    require(digest(files['SHA256SUMS'])==ANCHOR,'not the reviewed frozen inventory');require(sums(files['SHA256SUMS'])=={n:digest(v) for n,v in files.items() if n!='SHA256SUMS'},'frozen evidence hash differs');return files

def capture_files(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        entries=z.infolist();require(len(entries)<=64 and len(entries)==len({e.filename for e in entries}) and sum(e.file_size for e in entries)<=8*1024**2,'capture ZIP inventory/size differs')
        for e in entries:
            safe(e.filename);require(e.filename.startswith('capture/') and not e.is_dir() and stat.S_IFMT(e.external_attr>>16) in (0,stat.S_IFREG) and not e.flag_bits&1 and e.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED),'unsupported ZIP member')
        files={e.filename[8:]:z.read(e) for e in entries}
    require(sums(files['SHA256SUMS'])=={n:digest(v) for n,v in files.items() if n!='SHA256SUMS'},'inner capture inventory differs');return files

def materialize(files,root):
    root.mkdir(parents=True,exist_ok=False)
    for name,data in files.items():
        p=root.joinpath(*safe(name).parts);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)

def validate(source=SOURCE,*,repository=ROOT):
    files=frozen(source);raw=capture_files(files['capture.zip'])
    with tempfile.TemporaryDirectory(prefix='mpc06-offline-publication-check-') as temp:
        folder=Path(temp);materialize(raw,folder/'capture');(folder/'verification.json').write_bytes(files['verification.json'])
        command=[sys.executable,'-B','-c',"from pathlib import Path; import json,sys; from scripts.reports.mpc06_offline.check import checked_receipt; print(json.dumps(checked_receipt(Path(sys.argv[1]),Path(sys.argv[2]))))",str(folder/'capture'),str(folder/'verification.json')]
        result=subprocess.run(command,cwd=repository,capture_output=True,text=True,timeout=20);require(result.returncode==0,'saved offline-cost recheck failed: '+result.stderr[-1800:]);checked=json.loads(result.stdout)
    require(checked['status']=='verified' and all(r['attempts']==r['verified']==6 for r in checked['reports']),'saved work incomplete')
    qualification=json.loads(files['qualification.json']);require(qualification['measured']==checked['measured'] and qualification['capture_zip_sha256']==digest(files['capture.zip']) and qualification['capture_source']==checked['source_revision'] and qualification['checking_source']==checked['checking_revision'],'qualification binding differs')
    image=(repository/FIGURE).read_bytes();require(digest(image)==FIGURE_SHA,'original invariant figure differs')
    return files,raw,checked,image

def helper_revision():return subprocess.check_output(['git','log','--first-parent','--full-history','-1','--format=%H','--',*HELPERS],cwd=ROOT,text=True).strip()

def source_export(raw,checking):
    revision=helper_revision();require(re.fullmatch('[0-9a-f]{40}',revision),'invalid helper revision');files={};objects=set()
    for name in HELPERS:
        data=(ROOT/name).read_bytes();require(data==subprocess.check_output(['git','show','--end-of-options',revision+':'+name],cwd=ROOT),'helper differs from committed source');files[name]=data
    captured=json.loads(raw['environment.json']);sources=[(revision,{n:digest(v) for n,v in files.items()}),(captured['source_revision'],captured['source_sha256']),(checking['checking_revision'],checking['checking_sources'])]
    def include(oid):
        require(re.fullmatch('[0-9a-f]{40}',oid),'invalid Git object identity')
        if oid in objects:return
        objects.add(oid);kind=subprocess.check_output(['git','cat-file','-t',oid],cwd=ROOT,text=True).strip();require(kind in ('commit','tree','blob'),'unsupported Git object')
        body=subprocess.check_output(['git','cat-file',kind,oid],cwd=ROOT);content=f'{kind} {len(body)}'.encode()+b'\0'+body;require(hashlib.sha1(content).hexdigest()==oid,'Git object hash differs');files['.git/objects/'+oid[:2]+'/'+oid[2:]]=zlib.compress(content)
    for commit,paths in sources:
        require(isinstance(commit,str) and re.fullmatch('[0-9a-f]{40}',commit),'invalid source revision');include(commit);include(subprocess.check_output(['git','rev-parse',commit+'^{tree}'],cwd=ROOT,text=True).strip())
        for name,checksum in paths.items():
            parts=safe(name).parts;require(digest(subprocess.check_output(['git','show','--end-of-options',commit+':'+name],cwd=ROOT))==checksum,'source digest differs from Git')
            for size in range(1,len(parts)+1):include(subprocess.check_output(['git','rev-parse',commit+':'+str(PurePosixPath(*parts[:size]))],cwd=ROOT,text=True).strip())
    files['.git/HEAD']=b'ref: refs/heads/evidence\n';files['.git/refs/heads/evidence']=(checking['checking_revision']+'\n').encode();files['.git/config']=b'[core]\nrepositoryformatversion = 0\nbare = false\n'
    return files,dict(helper_revision=revision,checking_revision=checking['checking_revision'],helper_sha256={n:digest(files[n]) for n in HELPERS},object_count=len(objects))

def verify_export(root,receipt):
    require(set(receipt['helper_sha256'])==set(HELPERS),'mandatory helper inventory differs');revision=receipt['helper_revision'];checked=receipt['checking_revision'];require(all(isinstance(v,str) and re.fullmatch('[0-9a-f]{40}',v) for v in (revision,checked)),'invalid source revision')
    git=root/'.git';require((git/'config').read_bytes()==b'[core]\nrepositoryformatversion = 0\nbare = false\n' and (git/'HEAD').read_bytes()==b'ref: refs/heads/evidence\n' and (git/'refs/heads/evidence').read_bytes()==(checked+'\n').encode(),'Git configuration differs')
    count=0
    for p in git.rglob('*'):
        require(not p.is_symlink(),'source proof symlink')
        if not p.is_file():continue
        name=p.relative_to(git).as_posix()
        if name in ('HEAD','config','refs/heads/evidence'):continue
        require(re.fullmatch('objects/[0-9a-f]{2}/[0-9a-f]{38}',name),'unexpected Git file');count+=1
        with p.open('rb') as stream:packed=stream.read(2*1024**2+1)
        require(len(packed)<=2*1024**2,'oversized source object');dec=zlib.decompressobj();body=dec.decompress(packed,2*1024**2+1);require(len(body)<=2*1024**2 and dec.eof and not dec.unused_data and not dec.unconsumed_tail,'invalid source object');require(hashlib.sha1(body).hexdigest()==p.parent.name+p.name,'Git object SHA differs')
    require(count==receipt['object_count']<=128,'source object inventory differs')
    for name,checksum in receipt['helper_sha256'].items():
        data=(root/name).read_bytes();require(digest(data)==checksum,'helper hash differs');require(data==subprocess.check_output(['git','show','--end-of-options',revision+':'+name],cwd=root),'helper differs from authentic Git')

def _index(path):
    require(path.is_file() and not path.is_symlink(),'regular Pages index required');text=path.read_text();require(len(re.findall(r'<body\b',text,re.I))==1 and text.count('</body>')==1,'single body insertion point required');return text

def page(route,checked,parent):
    rows=''.join(f'<tr><td>{name}</td><td>{value["median_ns"]/1000:.3f}</td><td>{value["minimum_ns"]/1000:.3f}–{value["maximum_ns"]/1000:.3f}</td></tr>' for name,value in checked['measured'].items())
    link=f'<p><a href="../{parent}/index.html">Full original tube/native-QP comparison</a></p>' if parent else ''
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MPC06 offline construction costs</title><style>body{{font:16px/1.6 system-ui;background:#1e1e2e;color:#cdd6f4;max-width:1100px;margin:2rem auto;padding:1rem}}a{{color:#89b4fa}}h1,h2{{color:#a6e3a1}}img{{max-width:100%;height:auto}}td,th{{text-align:left;padding:.4rem}}</style><body><h1>Actual offline tube construction, separately checked</h1><p>New source-frozen prescribed-K construction; performance verdict: inconclusive. This fills the offline construction cost observation, not a retrospective timing of the180 original QPs. No gain optimizer, native solve, trajectory reexecution, comparative winner or online-latency claim.</p><p><a href="minimal-inputs.json">Complete model and three actual native-input identities</a> · <a href="verification.json">All raw clocks/counts/current checks</a> · <a href="evidence/{SOURCE.name}/capture.zip">Original capture/source/profile ZIP</a> · <a href="../{route}.zip">Complete offline recheck ZIP</a> · <a href="README.md">Recheck instructions</a></p>{link}<section id="offline-example"><h2>Same two-state invariant tube and nominal-QP artifacts</h2><p>A=[[1,1],[0,1]], B=E=(0,1), K=(−1,−2), |w|≤1/8, X=[−1,1]², U=[−1,1]. F=A+BK is nilpotent: F²=0. Construct Z=EW⊕FEW, nominal terminal{{0}} and support tightenings(7/8,3/4,5/8). The returned Fraction bounds feed the unchanged operational nominal-QP constructor; three complete coefficients/input-byte records match actual saved first-polytope requests. Independent checks verify all eight RPI vertex images, support maxima and zero-terminal continuation.</p><img src="invariant-tightenings.svg" alt="Previously checked MPC06 two-state invariant and tightened constraints"><p>This unchanged illustration comes from the full original comparison, which also shows other representation variants. The new timings concern only canonical exact Z, not those other enclosures. Complete initial/model/policy/native-request provenance is retained; no geometry is inferred from volume or sampled trajectories.</p></section><h2>One warmup and five measured repetitions</h2><table><tr><th>Actual timed phase</th><th>Median µs</th><th>Range µs</th></tr>{rows}</table><p>Construction includes prescribed matrix/Fraction conversion and Z/H/support/terminal formation. Independent checking includes exact certificate work, the existing nominal-QP constructor and native input-byte comparisons. Serialization times only the returned artifact JSON; JSON inside checking belongs to checking. Episode includes bookkeeping. Process wall additionally includes imports/input load/startup/I/O/polling and is not the sum of isolated phases.</p><p>The1000 measured-arm empty-counter controls have median1.466µs; no subtraction is applied. The separately profiled arm is excluded and only identifies observed certificate/consumer/Fraction costs. All12 measured/profiled attempts and limits/errors remain in the denominator. LinuxCPython3.14.8/Ryzen53550H capture; actual15sCPU/30swall/512MiBaddress-space process limits and wait4CPU/RSS, not native heap enforcement. Offline checking uses Python/Git only, no solver/runtime binary or required dependency/API/library release. Review, current-main CI and live download/example verification remain required.</p></body></html>'''.encode()

def stage(site,source=SOURCE,*,parent_route=None):
    site=Path(site);require(site.is_dir() and not site.is_symlink() and not (site/'examples').is_symlink(),'regular Pages site required');landing=_index(site/'index.html');gallery=_index(site/'examples/index.html')
    files,raw,checked,image=validate(source)
    if parent_route:
        require(len(safe(parent_route).parts)==1 and parent_route.startswith('mpc06-complete-'),'unexpected parent route')
        require(not (site/parent_route).is_symlink() and not (site/parent_route/'index.html').is_symlink() and not (site/parent_route/'invariant-tightenings.svg').is_symlink() and (site/parent_route/'index.html').is_file() and digest((site/parent_route/'invariant-tightenings.svg').read_bytes())==FIGURE_SHA,'parent MPC06 report identity differs')
    source_files,proof=source_export(raw,checked);route='mpc06-offline-costs-'+digest(encoded(dict(anchor=ANCHOR,source=proof,parent=parent_route)))[:20]
    require(not any(p.exists() or p.is_symlink() for p in (site/route,site/(route+'.zip'))) and route not in landing and route not in gallery,'immutable offline route exists')
    generated={'evidence/'+SOURCE.name+'/'+n:v for n,v in files.items()};objects={}
    for name,data in source_files.items():(objects if name.startswith('.git/') else generated)['source-root/'+name]=data
    generated.update({'index.html':page(route,checked,parent_route),'verification.json':encoded(checked),'source-files.json':encoded(proof),'minimal-inputs.json':raw['inputs.json'],'invariant-tightenings.svg':image})
    generated['offline_check.py']=b"from pathlib import Path\nimport importlib.util,json\nr=Path(__file__).resolve().parent\ns=importlib.util.spec_from_file_location('offline_extension',r/'source-root/scripts/reports/stage_mpc06_offline_costs.py')\nm=importlib.util.module_from_spec(s);s.loader.exec_module(m)\nm.verify_export(r/'source-root',json.loads((r/'source-files.json').read_bytes()))\n_,_,checked,_=m.validate(r/'evidence'/m.SOURCE.name,repository=r/'source-root')\nassert checked==json.loads((r/'verification.json').read_bytes())\nprint(json.dumps(checked))\n"
    generated['README.md']=f'''# MPC06 offline cost supplement

Extract ../{route}.zip in a fresh directory, enter {route}, verify OFFLINE_SHA256SUMS, then run `python -B offline_check.py`. Python3.11+ and Git suffice; no checkout/network/native solver/Matplotlib/install is needed. The complete original capture and checking receipt are unchanged under evidence/. Selected authentic Git objects exist only in the offline ZIP, with fixed empty configuration, no host hooks/credentials/full history. They preserve full-commit byte checks for capture/checker/helpers; missing or corrupted objects refuse, with no cached-success fallback. Helper identity is the stable last helper-changing commit. Historical process paths are evidence, not portable execution commands.

This is new measured construction of mathematically identical operational artifacts, not historical180QP timing. Copying prescribed K is not optimization. Certificate/consumer comparison and serialization are explicit separate work; every failed/resource outcome remains inconclusive. Frozen original2D figure is contextual, not a new measurement of other tube representations. Original native archives remain unchanged. Root owns cumulative wiring/catalogue/current-main publication and live acceptance checks; local staging is not delivery or closure.
'''.encode()
    generated['publication-manifest.json']=encoded(dict(schema='csl.mpc06.offline-publication/1',route=route,anchor=ANCHOR,source=proof,files={n:digest(v) for n,v in generated.items()},offline_objects={n:digest(v) for n,v in objects.items()}))
    generated['OFFLINE_SHA256SUMS']=''.join(f'{digest(v)}  {n}\n' for n,v in sorted((generated|objects).items())).encode();generated['SHA256SUMS']=''.join(f'{digest(v)}  {n}\n' for n,v in sorted(generated.items())).encode()
    card=f'<article id="{route}-example"><h2><a href="../{route}/index.html#offline-example">Exact two-state tube construction and its separate costs</a></h2><img src="../{route}/invariant-tightenings.svg" alt="Previously verified two-state tube and tightened constraints"><p>Actual canonical offline artifacts, exact native-QP identity and complete raw/source recheck.</p></article>'
    link=f'<section id="{route}"><h2>Tube MPC offline construction costs</h2><a href="{route}/index.html">Read supplement</a> · <a href="{route}.zip">Full offline evidence</a></section>'
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,data in sorted((generated|objects).items()):
            safe(name);entry=zipfile.ZipInfo(route+'/'+name,date_time=(2026,1,1,0,0,0));entry.external_attr=0o100644<<16;entry.compress_type=zipfile.ZIP_DEFLATED;z.writestr(entry,data)
    materialize(generated,site/route)
    with (site/(route+'.zip')).open('xb') as output:output.write(buffer.getvalue())
    (site/'index.html').write_text(landing.replace('</body>',link+'</body>'));(site/'examples/index.html').write_text(gallery.replace('</body>',card+'</body>'))
    return route

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--site',type=Path,required=True);p.add_argument('--parent-route');a=p.parse_args();print(stage(a.site,parent_route=a.parent_route))
