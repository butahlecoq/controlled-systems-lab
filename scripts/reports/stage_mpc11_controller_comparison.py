"""Validate and stage immutable MPC-11 comparisons without running controllers."""
from __future__ import annotations
import argparse
import hashlib
import html
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT/'benchmarks/reporting/mpc11'
EVIDENCE = MODULE/'evidence'
FIGURES = 'figures-60bda0fb'
FIGURE_ANCHOR = '8e384775137d4f717170d11835faa2dde87a728565f3e13b28c86b6300ca4140'
ARCHIVES = {
    'affine': ('affine-pilot-b3978a98','98c6d9663bad80757ddef1adb150706ca8f7e19633267dc436bc4b84f09fe9b3'),
    'nonlinear': ('nonlinear-pilot-0092081b','c8be3f89a377c5f9be3c0da4c818df26475c17ae282186cd16869c9a923f437e'),
    'nmpc': ('nmpc-pilot-55f65110','c13fb2db4f5492f5be85d42b3d5866c2a07ec24f78eb3a6a457d37ac15186253'),
}

PILOT_WRAPPERS = {'affine-pilot-b3978a98/README.md': '3e6fd29a2aa235fb668edee5036e41d3c2022157b1084d2776cef23440195188', 'affine-pilot-b3978a98/summary.json': 'cf1bbaf486102930b1353a91b169959442e930fc7b6d48d1aa12f095223d623f', 'nmpc-pilot-55f65110/README.md': '8238d7929f9f8e62a10cb155ed85809e7389967920c114138fcd1791b1554ca6', 'nmpc-pilot-55f65110/summary.json': '3c48e559def6784d4d3bb0c803945b34ca37400aa1cb143f3548469f72343b35', 'nonlinear-pilot-0092081b/README.md': 'ebdbe8def4db98c4ad2cdc9ee9ad0614258627c1f4a22557f5feb37c066b6c43', 'nonlinear-pilot-0092081b/summary.json': 'df8b7e514d7d36406a023f5ad0a6b7d11b66adb9c86dd297382ca8e6a4b70554'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(content):
    return hashlib.sha256(content).hexdigest()


def safe_name(name):
    path = PurePosixPath(name)
    require(bool(name) and not path.is_absolute() and path.as_posix() == name and
            all(re.fullmatch(r'[A-Za-z0-9_.-]+', part) and part not in ('.','..') for part in path.parts),
            'unsafe artifact path: '+name)
    return path


def sums(content):
    result = {}
    for line in content.decode('ascii').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)',line)
        require(match is not None,'invalid checksum manifest')
        checksum,name = match.groups();safe_name(name)
        require(name not in result,'duplicate checksum path')
        result[name] = checksum
    require(bool(result),'empty checksum manifest')
    return result


def verify_files(files):
    require('SHA256SUMS' in files,'missing checksum manifest')
    expected = sums(files['SHA256SUMS'])
    require(set(expected) == set(files)-{'SHA256SUMS'},'checksum inventory differs')
    for name,checksum in expected.items():
        require(digest(files[name]) == checksum,'checksum mismatch: '+name)


def safe_zip(content):
    files = {}
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        entries = archive.infolist()
        require(len(entries) <= 2000 and sum(entry.file_size for entry in entries) <= 64*1024**2,'archive resource limit')
        for entry in entries:
            safe_name(entry.filename)
            require(not entry.is_dir() and entry.filename not in files and entry.file_size <= 16*1024**2 and
                    stat.S_IFMT(entry.external_attr>>16) in (0,stat.S_IFREG) and not entry.flag_bits & 1 and
                    entry.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED),'unsafe ZIP entry')
            files[entry.filename] = archive.read(entry)
    require(not any(str(parent) in files for name in files for parent in PurePosixPath(name).parents if str(parent) != '.'),
            'ZIP file/directory conflict')
    verify_files(files)
    return files


def directory(path):
    require(path.is_dir() and not path.is_symlink(),'artifact directory must be regular')
    files = {}
    for child in path.rglob('*'):
        require(not child.is_symlink() and (child.is_dir() or child.is_file()),'unsafe artifact type')
        if child.is_file():
            name=child.relative_to(path).as_posix();safe_name(name);files[name]=child.read_bytes()
    return files


def current_renderer():
    spec=importlib.util.spec_from_file_location('mpc11_publication_renderer',MODULE/'figures.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


AFFINE_RECHECK_QUALIFICATION={
    'path':'benchmarks/reporting/mpc11/check_affine_saved.py',
    'frozen_checker_sha256':'658d326941bb761654de417a8ca3b5be5144088b0a62b3d6496511a8c167ca24',
    'current_checker_sha256':'f93b54995f3b1aa063ff927cc028e6fcb43bddd5ecfd2e74f04873fa69f29de2',
    'derivation_absolute_tolerance':1e-13,
    'derivation_relative_tolerance':1e-12,
    'scope':'floating model/transform rebuild only; all stored input/output/program and immutable-archive hashes remain exact',
}


def validate(evidence=EVIDENCE):
    evidence=Path(evidence)
    require(not evidence.is_symlink(),'unsafe evidence root')
    figures=directory(evidence/FIGURES)
    require(digest(figures['SHA256SUMS']) == FIGURE_ANCHOR,'reviewed figure manifest changed')
    verify_files(figures)
    receipt=json.loads(figures['receipt.json'])
    for name,checksum in receipt['output_sha256'].items():
        safe_name(name);require(digest(figures[name]) == checksum,'figure output binding differs')
    for name,checksum in receipt['helper_snapshot_sha256'].items():
        safe_name(name);require(digest(figures['source/'+name]) == checksum,'helper snapshot differs')
    for name,checksum in receipt['tool_sha256'].items():
        safe_name(name)
        if name==AFFINE_RECHECK_QUALIFICATION['path']:
            require(checksum==AFFINE_RECHECK_QUALIFICATION['frozen_checker_sha256'] and
                    digest((ROOT/name).read_bytes())==AFFINE_RECHECK_QUALIFICATION['current_checker_sha256'],
                    'current affine checker differs from qualified post-capture source')
        else:
            require(digest((ROOT/name).read_bytes()) == checksum,'current checker/source differs from reviewed figure: '+name)
    frozen={FIGURES:figures};archives={};extracted={}
    for kind,(folder,checksum) in ARCHIVES.items():
        files=directory(evidence/folder)
        require(set(files) == {'README.md','summary.json','SHA256SUMS','capture.zip'},'pilot inventory differs')
        require(sums(files['SHA256SUMS']) == {'capture.zip':checksum},'pilot manifest differs')
        for name in ('README.md','summary.json'):
            require(digest(files[name]) == PILOT_WRAPPERS[folder+'/'+name],'reviewed pilot reading layer changed')
        require(digest(files['capture.zip']) == checksum,'reviewed pilot archive changed')
        frozen[folder]=files;extracted[kind]=safe_zip(files['capture.zip'])
        archived=receipt['input_archives'][kind]
        require(archived['sha256'] == checksum and archived['archive'] == f'benchmarks/reporting/mpc11/evidence/{folder}/capture.zip',
                'figure input archive differs')
        archives[kind]=archived
    with tempfile.TemporaryDirectory(prefix='mpc11-publication-check-') as temporary:
        bundles={}
        for kind,files in extracted.items():
            folder=Path(temporary)/kind;folder.mkdir()
            for name,content in files.items():
                target=folder.joinpath(*safe_name(name).parts);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
            bundles[kind]=folder/'accepted'
            manifest=json.loads((bundles[kind]/'manifest.json').read_text())
            require(manifest['source_revision'] == archives[kind]['capture_source'],'capture source differs')
        reports=current_renderer().checked_inputs(**bundles)
        require(reports == receipt['saved_checks'],'current saved checks differ from frozen figure checks')
        for slug in ('syn-nl-lv-01','syn-nl-fuel-01'):
            load=lambda path:json.loads(path.read_text())
            scenario=load(bundles['nmpc']/slug/'scenario.json')
            require(scenario == load(bundles['affine']/slug/'scenario.json') == load(bundles['nonlinear']/slug/'source/scenario.json'),
                    'cross-variant scenario differs')
            a=load(bundles['affine']/slug/'check.json');nl=load(bundles['nonlinear']/slug/'cvodes/record.json');nm=load(bundles['nmpc']/slug/'attempt.json')
            require(a == load(bundles['nonlinear']/slug/'affine-witness.json'),'affine source witness differs')
            variants=[dict(label='Affine prediction',times=scenario['time']['grid'],states=a['affine_replay_states'],controls=a['physical_controls']),
                      dict(label='Affine controls on nonlinear plant',times=nl['times'],states=nl['physical_states'],controls=a['physical_controls']),
                      dict(label='Shrinking-horizon NMPC execution',times=nm['times'],states=nm['physical_states'],controls=nm['controls'])]
            require(json.loads(figures[slug+'-plotted-data.json']) == {'scenario':scenario,'variants':variants},'plotted arrays differ from checked raw histories')
            for key,path in {'scenario':bundles['nmpc']/slug/'scenario.json','affine':bundles['affine']/slug/'check.json',
                             'nonlinear':bundles['nonlinear']/slug/'cvodes/record.json','nmpc':bundles['nmpc']/slug/'attempt.json'}.items():
                require(digest(path.read_bytes()) == receipt['input_sha256'][slug+'/'+key],'plotted input hash differs')
    verification={'affine_checks':len(reports['affine']),'nonlinear_cases':len(reports['nonlinear']),
                  'nmpc_steps':sum(row['transcriptions_checked'] for row in reports['nmpc']),
                  'post_capture_affine_checker':AFFINE_RECHECK_QUALIFICATION,
                  'scope':'saved identities, numerical witnesses, sampled cost/constraints and transcription rebuild; no optimization/integration rerun'}
    return frozen,archives,verification


def index(path):
    require(path.is_file() and not path.is_symlink(),'site index must be regular')
    text=path.read_text();require(text.count('</body>') == 1,'site index needs one closing body');return text


def stage(site,evidence=EVIDENCE,*,example_card_writer=None):
    """Callable Pages augmentation hook; deployment stays with managed CI."""
    site=Path(site);require(site.is_dir() and not site.is_symlink(),'site must be regular')
    require((site/'examples').is_dir() and not (site/'examples').is_symlink(),'examples directory must be regular')
    landing=index(site/'index.html');gallery=index(site/'examples/index.html')
    source_files={p.relative_to(ROOT).as_posix():digest(p.read_bytes()) for p in MODULE.glob('*.py')}
    for folder in ('scenarios','environment'):
        source_files.update({f'benchmarks/reporting/mpc11/{folder}/'+name:digest(content)
                             for name,content in directory(MODULE/folder).items() if '__pycache__' not in PurePosixPath(name).parts})
    for p in (MODULE/'FIGURES.md', MODULE/'AFFINE-RECHECK.md', ROOT/'scripts/reports/figure_style.py'):
        source_files[p.relative_to(ROOT).as_posix()]=digest(p.read_bytes())
    identity={'figures_manifest':FIGURE_ANCHOR,'archives':ARCHIVES,'stager_sha256':digest(Path(__file__).read_bytes()),
              'current_sources':source_files}
    route='mpc11-controller-comparison-'+digest(json.dumps(identity,sort_keys=True).encode())[:20]
    require(not (site/route).exists() and not (site/route).is_symlink() and not (site/(route+'.zip')).exists() and
            not (site/(route+'.zip')).is_symlink() and route not in landing and route not in gallery,'immutable publication route exists')
    frozen,archives,verification=validate(evidence)
    prefix='benchmarks/reporting/mpc11/'
    generated={prefix+'evidence/'+folder+'/'+name:content for folder,files in frozen.items() for name,content in files.items()}
    for kind,(folder,_) in ARCHIVES.items():generated['raw/'+kind+'.zip']=frozen[folder]['capture.zip']
    for source in MODULE.glob('*.py'):generated[prefix+source.name]=source.read_bytes()
    for folder in ('scenarios','environment'):
        for name,content in directory(MODULE/folder).items():
            if '__pycache__' not in PurePosixPath(name).parts:generated[prefix+folder+'/'+name]=content
    for name in ('figure_style.py','stage_mpc11_controller_comparison.py'):
        generated['scripts/reports/'+name]=(ROOT/'scripts/reports'/name).read_bytes()
    for name in ('FIGURES.md','AFFINE-RECHECK.md'):generated[prefix+name]=(MODULE/name).read_bytes()
    figures_path=prefix+'evidence/'+FIGURES
    sections=[]
    for slug,title in [('syn-nl-lv-01','Lotka–Volterra: P/R'),('syn-nl-fuel-01','Fuel: m_ox/q_ox and m_f/q_f')]:
        plotted=json.loads(frozen[FIGURES][slug+'-plotted-data.json']);scenario=plotted['scenario']
        scenario_path=prefix+'scenarios/'+slug+'.json'
        require(json.loads(generated[scenario_path]) == scenario,'published minimal scenario differs')
        identities={key:scenario[key] for key in ('case_id','model_id','controller_id','time','initial_guess','affine','nmpc','execution','independent_replay','objective','states','controls','parameters')}
        sections.append(f'<section id="{slug}"><h2>{title}</h2><p>Equations: '+html.escape('; '.join(scenario['equations']))+'</p>'+
            f'<p><a href="{scenario_path}">Complete minimal inputs and equations</a> · <a href="{figures_path}/{slug}-plotted-data.json">Plotted arrays</a></p>'+
            f'<img src="{figures_path}/{slug}-phase.svg" alt="{title}: three individual trajectories with physical coordinates and time markers">'+
            f'<img src="{figures_path}/{slug}-traces.svg" alt="{title}: physical states and held control traces">'+
            '<details><summary>Scenario, model, controller and integrator identities</summary><pre>'+html.escape(json.dumps(identities,indent=2))+'</pre></details></section>')
    generated['index.html']=('''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MPC-11 saved controller comparison</title><style>body{font:16px/1.6 system-ui;background:#1e1e2e;color:#cdd6f4;max-width:1100px;margin:3rem auto;padding:0 1.5rem}a{color:#89b4fa}h1,h2{color:#a6e3a1}img{max-width:100%;height:auto}pre{overflow:auto;white-space:pre-wrap}</style><body><h1>Synthetic controller comparison: saved numerical trajectories</h1>
<p>Three distinct variants: <strong>Affine prediction</strong> uses the affine plan and affine dynamics; <strong>Affine controls on nonlinear plant</strong> replays those same held inputs using CVODES; <strong>Shrinking-horizon NMPC execution</strong> uses full observations and nominal do-mpc Radau/IPOPT/MUMPS optimization to the fixed terminal time, with nonlinear CVODES execution and independent CSL RK4 saved replay checks. These are authored synthetic scenarios. LV has state dimension 2; fuel has state dimension 4 and is shown in two mass/flow projections.</p>
<p>The current saved checks verify three affine records, two nonlinear cases and all 70 saved NMPC transcriptions. They rebuild identities, sampled cost/constraints and local stationarity diagnostics; they do not rerun any solver or integrator. Complete accepted trajectories are plotted. Initial/failed/resource-limited attempts remain in the raw archives and are excluded from these complete overlays. Prefix/resource outcomes are unavailable as complete answers, not mathematical counterexamples.</p>
<p><strong>Performance comparison: inconclusive.</strong> Pilot durations do not rank controllers. Local numerical solver status is not a global/minimax guarantee. These are individual trajectories, not reachable-set enclosures, backward sets, continuous-time safety certificates or robust policies. Connecting affine hold-boundary samples does not add integrated samples. No acados result is claimed.</p>'''+''.join(sections)+
        '<h2>Raw evidence, source and reproduction</h2><p>'+ ' · '.join(f'<a href="raw/{kind}.zip">{kind} complete pilot ZIP</a>' for kind in ARCHIVES)+
        f'</p><p><a href="{figures_path}/receipt.json">Frozen figure receipt and full input/tool hashes</a> · <a href="publication-manifest.json">Current publication provenance</a> · <a href="README.md">Offline checking commands</a> · <a href="../{route}.zip">Complete publication ZIP</a></p>'+
        '<p>Source commits: '+' · '.join(f'<a href="https://github.com/butahlecoq/controlled-systems-lab/commit/{data["capture_source"]}">{kind}: {data["capture_source"]}</a>' for kind,data in archives.items())+
        f'. Renderer source: 60bda0fb; <a href="{figures_path}/source/figures.py">frozen renderer</a>. Required library dependencies/API remain unchanged; reproduction uses the optional Linux CPython environment and retains solver/license limits. Issue #607 remains open for remaining study and deployment gates.</p></body></html>').encode()
    generated['README.md']=f'''# Offline saved comparison checks

Enter this publication route after extracting the complete ZIP into a fresh
folder. Run `sha256sum -c SHA256SUMS`. Frozen pilot/figure manifests and receipts
remain byte-preserved. New checking provenance is publication-manifest.json.

Use the optional environment described in `{prefix}environment/README.md`;
its exact Linux CPython wheel lock and notices are included. No required library
dependency is added. Do not infer redistribution permission from version pins.

Extract each raw archive into a separate new directory, then check its manifest:

```sh
mkdir affine nonlinear nmpc
unzip raw/affine.zip -d affine
unzip raw/nonlinear.zip -d nonlinear
unzip raw/nmpc.zip -d nmpc
(cd affine && sha256sum -c SHA256SUMS)
(cd nonlinear && sha256sum -c SHA256SUMS)
(cd nmpc && sha256sum -c SHA256SUMS)
python {prefix}check_affine_saved.py --bundle affine/accepted
python {prefix}check_nonlinear_saved.py --bundle nonlinear/accepted
python {prefix}check_nmpc_saved.py --bundle nmpc/accepted
```

These commands check saved evidence and rebuild transcriptions without running
optimization or numerical integration. `{prefix}FIGURES.md` documents optional
rendering to a new directory. This publication is staged locally only; managed
main/CI freshness, review, shared route audit and deployed-link checks remain
required before calling it published. No comparative timing verdict is supported.
'''.encode()
    manifest={'schema':'csl.mpc11.publication/1','identity':identity,'input_archives':archives,'verification':verification,
              'source_files':{folder:{name:digest(content) for name,content in sorted(files.items())} for folder,files in frozen.items()},
              'published_files':{name:digest(content) for name,content in sorted(generated.items())}}
    generated['publication-manifest.json']=(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode()
    generated['SHA256SUMS']=''.join(f'{digest(content)}  {name}\n' for name,content in sorted(generated.items())).encode()
    if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
    from scripts.reports.mpc01.stage_per_attempt import _insert_landing_link
    from scripts.reports.landing import links_html
    card=f'<article id="{route}-example"><h3><a href="../{route}/index.html">Synthetic LV and fuel controller trajectories</a></h3><a href="../{route}/index.html"><img src="../{route}/{figures_path}/syn-nl-lv-01-phase.svg" alt="LV P/R: three individually checked trajectories"></a><p>Minimal inputs, fuel mass/flow panels and held controls. Individual numerical paths; no set/safety or timing guarantee.</p><p>'+links_html((('Comparison and minimal inputs',f'../{route}/index.html'),('Complete raw/source ZIP',f'../{route}.zip')))+'</p></article>'
    with tempfile.TemporaryDirectory(prefix='mpc11-publication-stage-') as temporary:
        scratch=Path(temporary);(scratch/'examples').mkdir();(scratch/'index.html').write_text(landing);(scratch/'examples/index.html').write_text(gallery)
        _insert_landing_link(scratch,route+'-archive',route+'/index.html','Saved synthetic LV/fuel controller comparison and minimal visual inputs')
        if example_card_writer:example_card_writer(scratch,route+'-example',card)
        else:(scratch/'examples/index.html').write_text(gallery.replace('</body>',card+'</body>'))
        staged_gallery=index(scratch/'examples/index.html');require(route+'/index.html' in staged_gallery,'example helper dropped discovery link')
        archive_path=scratch/(route+'.zip')
        with zipfile.ZipFile(archive_path,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            for name,content in sorted(generated.items()):
                safe_name(name);entry=zipfile.ZipInfo(route+'/'+name,date_time=(2026,1,1,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED;entry.external_attr=0o100644<<16;archive.writestr(entry,content)
        destination=site/route;destination.mkdir()
        for name,content in generated.items():
            target=destination.joinpath(*safe_name(name).parts);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
        with (site/(route+'.zip')).open('xb') as stream:stream.write(archive_path.read_bytes())
        (site/'index.html').write_bytes((scratch/'index.html').read_bytes());(site/'examples/index.html').write_text(staged_gallery)
    return route


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--site',type=Path,required=True)
    args=parser.parse_args();print(stage(args.site))
