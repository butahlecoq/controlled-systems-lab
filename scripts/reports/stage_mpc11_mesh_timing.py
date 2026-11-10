"""Publish the frozen NI1/NI2 mesh and alternating-cost studies, saved checks only."""
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

ROOT=Path(__file__).resolve().parents[2]
MODULE=ROOT/'benchmarks/reporting/mpc11'
SPECS={
 'mesh-pilot-c0029ded':('c98b3af3f7033211da9c7d8502f30fd49623f2d5c11f603277ed3ecc14b4940b',487),
 'timing-five-68515dcb':('1c6b6d295d13cf7e11010bb8e3f95a535e70d741cf5ecd7ee6ab04a95d81e78b',3087),
 'nmpc-pilot-55f65110':('d50109507dadc49d8fe279058d5643c2e51f5dd2fe9c13b7aacdeb470b6ce60a',392),
}
MESH='mesh-pilot-c0029ded';TIMING='timing-five-68515dcb';BASELINE='nmpc-pilot-55f65110'
EVIDENCE=MODULE/'evidence'
FIGURES=('mesh-phase-overlays','mesh-differences','timing-phases')


def digest(data):return hashlib.sha256(data).hexdigest()

def require(condition,message):
    if not condition:raise ValueError(message)

def encoded(value):return (json.dumps(value,indent=2,sort_keys=True)+'\n').encode()


def safe_name(name):
    path=PurePosixPath(name)
    require(bool(name) and not path.is_absolute() and path.as_posix()==name and
            all(re.fullmatch(r'[A-Za-z0-9_.-]+',p) and p not in ('.','..') for p in path.parts),'unsafe study artifact path')
    return path


def checksums(data):
    result={}
    for line in data.decode('ascii').splitlines():
        match=re.fullmatch(r'([0-9a-f]{64})  (.+)',line);require(match is not None,'invalid study checksum record')
        name=match[2];safe_name(name);require(name not in result,'duplicate study checksum path');result[name]=match[1]
    require(result,'empty study checksum inventory');return result


def frozen(source,identity):
    require(source.name==identity and source.is_dir() and not source.is_symlink(),'unexpected study evidence directory')
    paths=list(source.iterdir());require(all(p.is_file() and not p.is_symlink() for p in paths),'study evidence requires regular flat files')
    files={p.name:p.read_bytes() for p in paths};require('SHA256SUMS'in files,'missing study inventory')
    require(digest(files['SHA256SUMS'])==SPECS[identity][0],'study manifest differs from reviewed immutable evidence')
    inventory=checksums(files['SHA256SUMS'])
    if identity==BASELINE:
        require(set(files)=={'README.md','summary.json','capture.zip','SHA256SUMS'} and set(inventory)=={'capture.zip'},'baseline evidence inventory differs')
        # Historical baseline's outer manifest authenticates only its ZIP. Do not
        # publish or consume its unbound adjacent reading-layer files.
        files={n:files[n] for n in ('capture.zip','SHA256SUMS')}
    require(inventory=={n:digest(b) for n,b in files.items() if n!='SHA256SUMS'},'study evidence inventory differs')
    return files


def archive_files(content,count):
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries=archive.infolist();names={e.filename for e in entries}
            require(len(entries)==count and len(names)==count,'study archive member inventory differs')
            require(sum(e.file_size for e in entries)<=256*1024**2,'study archive expansion limit')
            for entry in entries:
                path=safe_name(entry.filename)
                require(not entry.is_dir() and stat.S_IFMT(entry.external_attr>>16) in (0,stat.S_IFREG) and not entry.flag_bits&1 and
                        entry.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED) and entry.file_size<=16*1024**2,'unsupported study archive member')
                require(not any(p.as_posix() in names for p in path.parents if p!=PurePosixPath('.')),'study file/directory conflict')
            files={e.filename:archive.read(e) for e in entries}
    except (zipfile.BadZipFile,RuntimeError,EOFError) as error:raise ValueError('invalid study ZIP') from error
    require('SHA256SUMS'in files,'missing inner study inventory')
    require(checksums(files['SHA256SUMS'])=={n:digest(b) for n,b in files.items() if n!='SHA256SUMS'},'inner study checksum mismatch')
    return files


def materialize(files,folder):
    folder.mkdir(parents=True,exist_ok=False)
    for name,data in files.items():
        target=folder.joinpath(*safe_name(name).parts);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)


def sources():
    paths=[*sorted(MODULE.glob('*.py')),*sorted(MODULE.glob('*.md')),ROOT/'scripts/reports/figure_style.py',Path(__file__).resolve()]
    require(all(p.is_file() and not p.is_symlink() for p in paths),'regular current study source files required')
    files={p.relative_to(ROOT).as_posix():p.read_bytes() for p in paths}
    for folder in ('environment','scenarios'):
        for path in sorted((MODULE/folder).rglob('*')):
            require(not path.is_symlink(),'source snapshot symlink refused')
            if path.is_file() and '__pycache__'not in path.parts:files[path.relative_to(ROOT).as_posix()]=path.read_bytes()
    return files


def unpack(evidence,destination):
    require(not destination.exists(),'new offline extraction directory required')
    frozen_files={key:frozen(evidence/key,key) for key in SPECS}
    expanded={key:archive_files(value['capture.zip'],SPECS[key][1]) for key,value in frozen_files.items()}
    destination.mkdir(parents=True)
    for key,value in expanded.items():materialize(value,destination/key)
    return destination


def check_and_render(expanded,frozen_files,output):
    command=[sys.executable,'-B',str(MODULE/'study_report.py'),'--mesh',str(expanded/MESH),'--baseline',str(expanded/BASELINE),
        '--timing',str(expanded/TIMING),'--mesh-summary',str(output.parent/'mesh-frozen-summary.json'),
        '--timing-summary',str(output.parent/'timing-frozen-summary.json'),'--output',str(output)]
    (output.parent/'mesh-frozen-summary.json').write_bytes(frozen_files[MESH]['summary.json'])
    (output.parent/'timing-frozen-summary.json').write_bytes(frozen_files[TIMING]['summary.json'])
    result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=900)
    if result.stderr:print(result.stderr,file=sys.stderr,end='')
    require(result.returncode==0,'current full saved study checks failed: '+result.stderr[-5000:])
    verification=json.loads((output/'verification.json').read_bytes())
    require(verification['status']=='checked' and (verification['mesh_transcriptions'],verification['timing_transcriptions'])==(140,420),'full study check inventory differs')
    return verification


def page(route,mesh,timing):
    rows=''.join(f'<tr><td>{r["case_id"]}</td><td>{r["ni1"]["executed_objective_J0"]:.16g}</td><td>{r["ni2"]["executed_objective_J0"]:.16g}</td><td>{r["max_abs_control_difference_by_component"]}</td></tr>' for r in mesh['cases'])
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MPC11 mesh sensitivity and recorded phase costs</title><style>body{{font:16px/1.6 system-ui;background:#1e1e2e;color:#cdd6f4;max-width:1250px;margin:2rem auto;padding:1rem}}a{{color:#89b4fa}}h1,h2{{color:#a6e3a1}}img{{max-width:100%;height:auto}}table{{display:block;overflow:auto}}th,td{{text-align:left;padding:.4rem}}</style><body>
<h1>NMPC mesh sensitivity and repeated phase costs</h1><p><strong>Comparative performance: inconclusive.</strong> Two authored synthetic LV/fuel models, complete physical units/inputs, original objective and retained local-solver/replay diagnostics. This later-study report complements the earlier pilot. It is a different-model/controller experiment, not equal-problem solver parity or restoration of historical B04/L05 results.</p>
<p><a href="minimal-inputs.json">Complete NI1/NI2 scenario inputs</a> · <a href="verification.json">Current saved-check scope/counts</a> · <a href="figure-data.json">Exact plotted arrays and original phase ranges</a> · <a href="publication-manifest.json">Source/archive identities</a> · <a href="../{route}.zip">Complete offline HTML/source/raw ZIP</a> · <a href="README.md">Recheck instructions and optional runtime</a></p>
<section id="mesh-example"><h2>Same plant and original objective, NI1 versus NI2</h2><p>NI1 and NI2 retain the original terminal time, dense physical output grid, held controls, full-state observation, all-node constraints and original cost denominator. Only controller identity and Radau subelements per original interval differ. These are distinct local discretized NLPs, not globally optimal nonlinear policies. Circles mark initial states, crosses final states. Fuel pairs are oxidizer mass/flow m_ox/q_ox and fuel mass/flow m_f/q_f; storage order is masses then flows.</p>
<a href="mesh-phase-overlays.svg"><img src="mesh-phase-overlays.svg" alt="NI1/NI2 LV P/R and fuel oxidizer/fuel mass-flow paths overlaid in physical coordinates"></a>
<a href="mesh-differences.svg"><img src="mesh-differences.svg" alt="Componentwise NI2-minus-NI1 state and held-control differences against physical time with explicit display scales"></a>
<table><tr><th>Case</th><th>NI1 executed J0</th><th>NI2 executed J0</th><th>Maximum held-control difference</th></tr>{rows}</table>
<p>Complete equations, units, initial values, transformations, hard bounds, hold/grid/tolerances and original objectives are in the linked full scenario JSONs. Paths connect saved samples; neither zero sampled violations nor small mesh differences certify continuous-time safety, robust containment or convergence. Independent CSL RK4 replay at both contract tolerances remains distinct from CVODES execution. Original raw refusals, initial attempts and fresh replay receipts are preserved.</p></section>
<h2>Five alternating measured repetitions, phase scopes kept separate</h2><a href="timing-phases.svg"><img src="timing-phases.svg" alt="Separate affine and NI1 NMPC phase medians and min-max ranges from five measured repetitions"></a>
<p>One warmup is retained but excluded. Five measured arm orders alternate A/B, B/A, A/B, B/A, A/B. A is affine full-joint optimization with declared positive uniform cost scale 1000, then nonlinear execution/replay. B is nominal shrinking-horizon NI1 NMPC plus nonlinear execution/replay. Actuators, physical plant and observations are matched; model/policy restrictions differ. Affine optimization/affine replay, affine controls on nonlinear dynamics and nonlinear optimization/execution keep distinct IDs.</p>
<p>Python configuration, native QP setup/run, sums of NMPC controller setup/local solves, held CVODES and complete process times are different spans. Affine CVODES includes integrator construction; NMPC's held-call sum excludes its once-per-case integrator construction. Do not sum nested spans or compute a solver-time ratio. Each of four arm/case cells has five complete measured samples; all 18 outer units and 420 saved NLP transcriptions are retained. A separate Python profile is not a native limiter/tuning study. No solver ranking or real-time guarantee follows.</p>
<p><a href="timing-comparison.json">All original timing samples/ranges and clock scopes</a> · <a href="mesh-comparison.json">Original mesh diagnostic fields</a></p>
<h2>Immutable data, current checks and qualifications</h2><p>Publication ran current 140 mesh plus 420 repeated-study saved NLP transcription checks and the associated stored affine/replay checks; it ran no optimizer, integrator or native binary. Current host-specific numerical residuals and checker durations stay in logs/CI receipts, outside immutable publication bytes. Original measured clocks, arrays, source snapshots and native streams are unchanged. Actual hashes authenticate stored data; independently recomputed floating derivations follow their separately qualified numerical policies.</p>
<p>Optional checking/rendering uses the existing Linux Python 3.11.14 lock, do-mpc 5.1.2, CasADi 3.8.0 and Matplotlib 3.11.2, with existing solver/notice qualifications. No installation, author-code adoption, acados run, new core API/required dependency, binary distribution or library release belongs to this report. Historical correspondence and physical-enclosure questions remain separate; unsupported nonlinear/global/minimax guarantees are refused.</p>
<p>Original archives: <a href="evidence/{BASELINE}/capture.zip">NI1 baseline</a> · <a href="evidence/{MESH}/capture.zip">NI2 mesh</a> · <a href="evidence/{TIMING}/capture.zip">Alternating timing/profile</a>. The full offline ZIP also contains current checker/plot sources and existing docs/lock/notices. Root's existing main-only/current-head-protected cumulative pipeline owns deployment; local staging is not live publication. Keep #607 open until review, current CI and deployed URL/download hashes pass.</p></body></html>'''.encode()


def stage(site,evidence=EVIDENCE,*,example_card_writer=None):
    site=Path(site);evidence=Path(evidence)
    require(site.is_dir() and not site.is_symlink(),'site must be a regular directory')
    for path in (site/'index.html',site/'examples',site/'examples/index.html'):require(not path.is_symlink(),'symlink site destination refused')
    landing=(site/'index.html').read_text();gallery=(site/'examples/index.html').read_text()
    require(landing.count('</body>')==1 and gallery.count('</body>')==1,'publication insertion points differ')
    frozen_files={key:frozen(evidence/key,key) for key in SPECS}
    expanded_files={key:archive_files(value['capture.zip'],SPECS[key][1]) for key,value in frozen_files.items()}
    exported=sources();identity={'reports':{k:SPECS[k][0] for k in SPECS},'current_sources':{n:digest(b) for n,b in sorted(exported.items())}}
    route='mpc11-mesh-timing-'+digest(encoded(identity))[:20]
    require(not any(p.exists() or p.is_symlink() for p in (site/route,site/(route+'.zip'))) and route not in landing and route not in gallery,'immutable study route already exists')
    with tempfile.TemporaryDirectory(prefix='mpc11-study-publication-') as temporary:
        scratch=Path(temporary);(scratch/'examples').mkdir();(scratch/'index.html').write_text(landing);(scratch/'examples/index.html').write_text(gallery)
        card=f'<article id="{route}-example"><h3><a href="../{route}/index.html#mesh-example">LV/fuel mesh sensitivity and measured phase costs</a></h3><a href="../{route}/index.html#mesh-example"><img src="../{route}/mesh-phase-overlays.svg" alt="NI1/NI2 LV and fuel mass-flow paths overlaid"></a><p>Componentwise physical differences, original inputs, five alternating phase-cost repetitions; no solver ranking or safety/convergence certificate.</p><p><a href="../{route}.zip">Complete offline source/raw ZIP</a></p></article>'
        if example_card_writer:example_card_writer(scratch,route+'-example',card)
        else:(scratch/'examples/index.html').write_text(gallery.replace('</body>',card+'</body>'))
        require(route+'/index.html#mesh-example'in(scratch/'examples/index.html').read_text(),'gallery writer dropped discovery link')
        (scratch/'index.html').write_text(landing.replace('</body>',f'<section id="{route}"><h2>MPC11 mesh and repeated-workload studies</h2><p><a href="{route}/index.html">Read the saved study and minimal visual inputs</a> · <a href="{route}.zip">Download complete offline source/raw data</a>.</p></section></body>'))
        expanded=scratch/'expanded';expanded.mkdir()
        for key,files in expanded_files.items():materialize(files,expanded/key)
        output=scratch/'reading';verification=check_and_render(expanded,frozen_files,output)
        generated={p.name:p.read_bytes() for p in output.iterdir() if p.is_file()}
        generated.update({f'evidence/{key}/{n}':b for key,files in frozen_files.items() for n,b in files.items()})
        generated.update({'source/'+n:b for n,b in exported.items()})
        minimal={f'ni{elements}-{case}':json.loads(expanded_files[identity0][f'accepted/syn-nl-{case}-01/scenario.json']) for elements,identity0 in ((1,BASELINE),(2,MESH)) for case in ('lv','fuel')}
        generated['minimal-inputs.json']=encoded(minimal)
        generated['index.html']=page(route,json.loads(generated['mesh-comparison.json']),json.loads(generated['timing-comparison.json']))
        generated['README.md']=f'''# Offline MPC11 mesh/timing reading layer

Open index.html for complete minimal inputs, labelled phase/difference plots and
descriptive timing scopes. Original archives remain byte-preserved under evidence/.
Run `sha256sum -c SHA256SUMS` after extracting ../{route}.zip into a fresh folder.
Reading HTML/raw data requires no optional numerical stack.

Full saved mathematical/source checks require the existing locked Linux Python 3.11.14
MPC11 environment and Git objects for the recorded source/review commits. They execute
no optimizer, integrator or native binary. Copied source hashes alone do not authenticate
Git commits; missing objects refuse checks. Use the exported current helper bytes in
source/, whose hashes are in publication-manifest.json. To use a separate complete
checkout only as a read-only Git object store:

```sh
export GIT_DIR="$(git -C /path/to/full/source rev-parse --absolute-git-dir)"
python3 -B source/scripts/reports/stage_mpc11_mesh_timing.py --unpack-only \\
  --evidence evidence --destination /path/to/NEW_EXTRACT
/PINNED_MPC11_ENV/bin/python -B source/benchmarks/reporting/mpc11/study_report.py \\
  --mesh /path/to/NEW_EXTRACT/{MESH} \\
  --baseline /path/to/NEW_EXTRACT/{BASELINE} \\
  --timing /path/to/NEW_EXTRACT/{TIMING} \\
  --mesh-summary evidence/{MESH}/summary.json \\
  --timing-summary evidence/{TIMING}/summary.json --output /path/to/NEW_REPORT
```

Existing optional lock/notices are exported in source/benchmarks/reporting/mpc11/environment/.
Native reproduction additionally needs the original qualified bridges/build, not
redistributed here. Current host-specific diagnostics are stderr/CI artifacts only;
immutable figures/records preserve the original measured data. No performance ranking,
global nonlinear optimum, robustness/safety or convergence certificate is supplied.
No core API/dependency/install/package/release change. Keep #607 open through its
review/current-CI/main-only freshness/live-publication gates.
'''.encode()
        manifest=dict(schema='csl.mpc11.study-publication/1',report_id=route,identity=identity,verification=verification,
            archive_sha256={k:digest(v['capture.zip']) for k,v in frozen_files.items()},
            published_files={n:digest(b) for n,b in sorted(generated.items())})
        generated['publication-manifest.json']=encoded(manifest)
        generated['SHA256SUMS']=''.join(digest(b)+'  '+n+'\n' for n,b in sorted(generated.items())).encode()
        with zipfile.ZipFile(scratch/(route+'.zip'),'w',zipfile.ZIP_DEFLATED) as archive:
            for name,content in sorted(generated.items()):
                safe_name(name);item=zipfile.ZipInfo(route+'/'+name,date_time=(2026,1,1,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED;item.external_attr=0o100644<<16;archive.writestr(item,content)
        materialize(generated,site/route)
        with (site/(route+'.zip')).open('xb') as target:target.write((scratch/(route+'.zip')).read_bytes())
        (site/'index.html').write_bytes((scratch/'index.html').read_bytes());(site/'examples/index.html').write_bytes((scratch/'examples/index.html').read_bytes())
    return route


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--site',type=Path);parser.add_argument('--evidence',type=Path,default=EVIDENCE);parser.add_argument('--unpack-only',action='store_true');parser.add_argument('--destination',type=Path);a=parser.parse_args()
    if a.unpack_only and a.destination:print(unpack(a.evidence,a.destination))
    elif a.site:print(stage(a.site,a.evidence))
    else:parser.error('supply --site or --unpack-only with --destination')
