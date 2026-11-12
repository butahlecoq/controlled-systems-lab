"""Validate frozen REVIEW-05 evidence and stage one immutable Pages route.

No solver or captured executable is invoked. Shared augmentation wiring belongs
in augment_pages_bundle.py; this module is a report-specific callable hook.
"""
from __future__ import annotations

import argparse
from collections import Counter
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

ROOT=Path(__file__).resolve().parents[2]
BENCH=ROOT/'benchmarks/reporting/review05'
QUERY_ID='review05-family-query-20261110-3b98f5b0'
PHASE_ID='review05-build-phases-20261110-468cc0eb'
QUERY_SOURCE=ROOT/'reports/algorithm-results'/QUERY_ID
PHASE_SOURCE=ROOT/'reports/algorithm-results'/PHASE_ID
ANCHORS={QUERY_ID:'887b3109a132053ba284a34aa50373ff106108bc08bb6ace2ca70eeddb45cc2b',
         PHASE_ID:'988aa80683ca1dddbd7bacd8c7a1b0bebe42babb3da3f6ed1b361cbc086a0214'}
CAPTURES={QUERY_ID:'3b98f5b02838909981b7ce70378f58dc25c74457',PHASE_ID:'468cc0eb2d3d8e3f7f3ade632db8a2e88cf2cd85'}
HISTORICAL_ROUTE_CAPTURE=ROOT/'reports/algorithm-results/review05-highs-clocks-8abaf50b-20261109'
HISTORICAL_ROUTE_CAPTURE_SHA='f7c8f38f30ce3152f87f95fe0563404069b8d0c3dfc78d6bdaec675180e4d836'
HISTORICAL_ROUTE_README_SHA='838d25b02d6514fc8270df78fc8bdbee04d8baaaf66cbccd0f90a2b19bb99386'
HISTORICAL_ROUTE_ALIAS=PurePosixPath('benchmarks/reporting/review05/README.md')
HISTORICAL_ROUTE_METADATA_SOURCE=ROOT/'reports/algorithm-results/review05-guide-route-retirement-20261112.json'
HISTORICAL_ROUTE_METADATA_ALIAS=PurePosixPath('benchmarks/reporting/review05/route-retirement.json')
MAX_ARCHIVE_BYTES=256*1024**2


def digest(data):return hashlib.sha256(data).hexdigest()

def require(condition,message):
    if not condition:raise ValueError(message)


def _name(name):
    path=PurePosixPath(name)
    require(bool(name) and not path.is_absolute() and path.as_posix()==name and
            all(re.fullmatch(r'[A-Za-z0-9_.-]+',part) and part not in ('.','..') for part in path.parts),
            'unsafe REVIEW-05 artifact path: '+repr(name))
    return path


def _sums(content):
    result={}
    for line in content.decode('ascii').splitlines():
        match=re.fullmatch(r'([0-9a-f]{64})  (.+)',line)
        require(match is not None,'invalid REVIEW-05 checksum record')
        name=match[2];_name(name);require(name not in result,'duplicate REVIEW-05 checksum path')
        result[name]=match[1]
    require(result,'empty REVIEW-05 checksum inventory')
    return result


def _read_frozen(source,identity):
    source=Path(source)
    require(not source.is_symlink() and source.is_dir(),'frozen REVIEW-05 source must be a regular directory')
    require(source.name==identity,'unexpected reviewed REVIEW-05 report identity')
    entries=list(source.rglob('*'))
    require(not any(p.is_symlink() for p in entries),'symlink in frozen REVIEW-05 source')
    require(all(p.is_dir() or stat.S_ISREG(p.stat().st_mode) for p in entries),'nonregular frozen REVIEW-05 entry')
    files={p.relative_to(source).as_posix():p.read_bytes() for p in entries if p.is_file()}
    for name in files:_name(name)
    require('SHA256SUMS' in files,'missing reviewed REVIEW-05 manifest')
    require(digest(files['SHA256SUMS'])==ANCHORS[identity],'manifest is not the reviewed REVIEW-05 evidence')
    sums=_sums(files['SHA256SUMS'])
    require(set(sums)==set(files)-{'SHA256SUMS'},'frozen REVIEW-05 inventory differs')
    require(all(digest(files[name])==sha for name,sha in sums.items()),'frozen REVIEW-05 checksum mismatch')
    return files


def checked_zip(content,expected_manifest=None):
    """Bounded, path-safe read; large gmon samples are hashed but not retained."""
    kept={}
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries=archive.infolist();names=[entry.filename for entry in entries]
            require(0<len(entries)<=1000 and len(names)==len(set(names)),'duplicate or excessive REVIEW-05 ZIP entries')
            require(sum(x.file_size for x in entries)<=MAX_ARCHIVE_BYTES,'REVIEW-05 ZIP expansion limit exceeded')
            for entry in entries:
                path=_name(entry.filename)
                require(not entry.is_dir() and entry.file_size<=16*1024**2 and not entry.flag_bits&1 and
                        entry.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED), 'unsupported REVIEW-05 ZIP member')
                require(stat.S_IFMT(entry.external_attr>>16) in (0,stat.S_IFREG),'nonregular REVIEW-05 ZIP member')
                require(not any(parent.as_posix() in names for parent in path.parents if parent!=PurePosixPath('.')),
                        'REVIEW-05 ZIP file/directory conflict')
            sums=None
            if expected_manifest is not None:
                require('SHA256SUMS' in names,'missing inner REVIEW-05 manifest')
                require(archive.read('SHA256SUMS')==expected_manifest,'inner REVIEW-05 manifest differs from reviewed inventory')
                sums=_sums(expected_manifest)
                require(set(names)==set(sums)|{'SHA256SUMS'},'inner REVIEW-05 ZIP inventory differs')
            for entry in entries:
                value=hashlib.sha256();blocks=[];retain=not PurePosixPath(entry.filename).name.startswith('gmon.')
                with archive.open(entry) as stream:
                    while block:=stream.read(1024**2):
                        value.update(block)
                        if retain:blocks.append(block)
                if sums is not None and entry.filename!='SHA256SUMS':
                    require(value.hexdigest()==sums[entry.filename],'inner REVIEW-05 ZIP checksum mismatch')
                if retain:kept[entry.filename]=b''.join(blocks)
    except (zipfile.BadZipFile,RuntimeError,EOFError) as error:
        raise ValueError('invalid REVIEW-05 ZIP: '+str(error)) from error
    return kept


def _historical_route_readme():
    sums_path=HISTORICAL_ROUTE_CAPTURE/'SHA256SUMS';archive_path=HISTORICAL_ROUTE_CAPTURE/'capture.zip'
    require(not HISTORICAL_ROUTE_CAPTURE.is_symlink() and not sums_path.is_symlink() and not archive_path.is_symlink() and
            sums_path.is_file() and archive_path.is_file(),'sealed REVIEW-05 route capture is missing or unsafe')
    outer_sums=_sums(sums_path.read_bytes())
    content=archive_path.read_bytes()
    require(outer_sums.get('capture.zip')==HISTORICAL_ROUTE_CAPTURE_SHA and
            digest(content)==HISTORICAL_ROUTE_CAPTURE_SHA,'sealed REVIEW-05 route ZIP hash differs')
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            require('SHA256SUMS' in archive.namelist(),'sealed REVIEW-05 route ZIP has no inner manifest')
            inner_manifest=archive.read('SHA256SUMS')
    except (zipfile.BadZipFile,RuntimeError,EOFError) as error:
        raise ValueError('invalid sealed REVIEW-05 route ZIP: '+str(error)) from error
    files=checked_zip(content,inner_manifest)
    readme=files.get('README.md')
    require(readme is not None and digest(readme)==HISTORICAL_ROUTE_README_SHA,
            'sealed REVIEW-05 route README differs from the published source bytes')
    return readme


def _historical_route_metadata():
    path=HISTORICAL_ROUTE_METADATA_SOURCE
    require(not path.is_symlink() and path.is_file(),'REVIEW-05 retirement metadata is missing or unsafe')
    content=path.read_bytes()
    try:
        metadata=json.loads(content)
    except (UnicodeDecodeError,json.JSONDecodeError) as error:
        raise ValueError('invalid REVIEW-05 retirement metadata: '+str(error)) from error
    source=metadata['retained_source'];git_source=source['git'];capture=source['sealed_capture']
    require(metadata['schema']=='csl.retired-working-guide-route/1' and
            metadata['status']=='working-guide-retired-from-current-tree' and
            git_source['commit']=='8abaf50b1dc612eeb9deaf1827c8e57042e8364f' and
            git_source['path']=='benchmarks/reporting/review05/README.md' and
            git_source['sha256']==HISTORICAL_ROUTE_README_SHA and
            capture['path']=='reports/algorithm-results/review05-highs-clocks-8abaf50b-20261109/capture.zip' and
            capture['sha256']==HISTORICAL_ROUTE_CAPTURE_SHA and capture['member']=='README.md' and
            capture['member_size_bytes']==11761 and capture['member_sha256']==HISTORICAL_ROUTE_README_SHA and
            metadata['current_project_route']['public_alias'].endswith('/controlled-systems-lab/benchmarks/reporting/review05/README.md') and
            metadata['current_project_route']['source_metadata'].endswith('/controlled-systems-lab/benchmarks/reporting/review05/route-retirement.json') and
            metadata['preservation']['sealed_report_readmes_and_capture_zip_modified'] is False and
            metadata['preservation']['current_working_guide_restored'] is False,
            'REVIEW-05 retirement metadata does not match the retained source')
    return content


def _write_historical_route_aliases(site,readme,metadata):
    for route,content in ((HISTORICAL_ROUTE_ALIAS,readme),(HISTORICAL_ROUTE_METADATA_ALIAS,metadata)):
        alias=site.joinpath(*route.parts)
        parent=alias.parent
        require(not parent.is_symlink() and not alias.is_symlink(),'historical REVIEW-05 route asset is unsafe')
        parent.mkdir(parents=True,exist_ok=True)
        if alias.exists():
            require(alias.is_file() and alias.read_bytes()==content,'historical REVIEW-05 route asset conflicts with its source bytes')
        else:
            alias.write_bytes(content)


def _module(name):
    spec=importlib.util.spec_from_file_location('_review05_publish_'+name,BENCH/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def _materialize(files,folder):
    folder.mkdir()
    for name,content in files.items():
        target=folder.joinpath(*_name(name).parts);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)


def _source(files,identity):
    environment=json.loads(files['environment.json'])
    require(environment['source_commit']==CAPTURES[identity] and environment['source_status']=='',
            'REVIEW-05 clean captured source identity differs')
    for name,sha in environment['source_sha256'].items():
        require(_name(name).name==name and 'source/'+name in files,'unsafe or missing REVIEW-05 captured source')
        require(digest(files['source/'+name])==sha,'REVIEW-05 captured source fingerprint differs')
    if identity==QUERY_ID:
        provenance=json.loads(files['post-capture/provenance.json'])
        require(provenance['capture_source_commit']==CAPTURES[identity] and
                provenance['post_capture_checker_commit']=='77db095b85675a783f6dd51a44a5a54545722ad2',
                'REVIEW-05 post-capture checker provenance differs')
        for name,sha in provenance['files'].items():
            require(_name(name).name==name and digest(files['post-capture/'+name])==sha,
                    'REVIEW-05 post-capture source fingerprint differs')
    return environment


def _recheck(folder,checker,renderer,expected_count):
    checks=json.loads((folder/'checks.json').read_bytes());cached={x['attempt']:x for x in checks['attempts']}
    statuses=[];records=[]
    for path in sorted((folder/'attempts').glob('*/receipt.json')):
        key=path.parent.relative_to(folder).as_posix();require(key in cached,'missing frozen REVIEW-05 check binding')
        receipt=renderer.bound_receipt(folder,path,cached[key])
        scenario_path=folder/'scenarios'/receipt['scenario'];scenario=json.loads(scenario_path.read_bytes())
        raw=(path.parent/'stdout.txt').read_bytes()
        result=checker.check_process(receipt,raw,scenario,digest(scenario_path.read_bytes()))
        require(result['status']==cached[key]['status'],'current REVIEW-05 mathematical check differs from frozen result')
        expected='inconclusive' if receipt.get('refusal_probe') else 'verified'
        require(result['status']==expected,'unexpected REVIEW-05 mathematical failure or missing evidence')
        record=json.loads(raw);records.append(record);statuses.append(result['status'])
    require(len(statuses)==expected_count==len(cached),'REVIEW-05 attempt inventory differs')
    return dict(Counter(statuses)),records


def validate(query_source=QUERY_SOURCE,phase_source=PHASE_SOURCE):
    """Validate every immutable byte and current proofs before staging writes."""
    query=_read_frozen(query_source,QUERY_ID);phase=_read_frozen(phase_source,PHASE_ID)
    _source(query,QUERY_ID);_source(phase,PHASE_ID)
    inner=checked_zip(query['offline.zip'],query['archive-members.sha256'])
    for name in ('environment.json','checks.json','summary.json','figure-export.json','control-projection.svg','control-projection.png'):
        require(inner[name]==query[name],'REVIEW-05 outer/inner report bytes differ: '+name)
    checker=_module('check_family_query');renderer=_module('render_family_query');phase_runner=_module('run_build_phases')
    with tempfile.TemporaryDirectory(prefix='review05-publication-check-') as temporary:
        scratch=Path(temporary);q=scratch/QUERY_ID;p=scratch/PHASE_ID
        _materialize(inner,q);_materialize(phase,p)
        query_counts,records=_recheck(q,checker,renderer,170)
        phase_counts,_=_recheck(p,checker,renderer,86)
        recomputed,_=renderer.summary(q)
        require(recomputed==json.loads(query['summary.json']),'REVIEW-05 saved summary/timing inputs differ from checked raw records')
        phase_summary=phase_runner.summarize(p)
        require(phase_summary==json.loads(phase['phase-summary.json']),'REVIEW-05 phase report/timing inputs differ from checked raw records')
        profile_statuses=[]
        scenario_path=q/'scenarios/family-query-flat-t08.json';scenario=json.loads(scenario_path.read_bytes())
        for path in sorted((q/'limiter-profile').glob('*/receipt.json')):
            receipt=json.loads(path.read_bytes());result=checker.check_process(receipt,(path.parent/'stdout.txt').read_bytes(),scenario,digest(scenario_path.read_bytes()))
            require(result['status']=='verified','REVIEW-05 current profiler-history replay failed');profile_statuses.append(result['status'])
        require(len(profile_statuses)==40,'REVIEW-05 profiler attempt inventory differs')
    figure=json.loads(query['figure-export.json'])
    require(figure['state_dimension']==1 and figure['control_coordinates']==['u0','u1'] and
            figure['matplotlib']=='3.11.2' and figure['quantitative_axis_policy']=='csl-report-quantitative-v1',
            'REVIEW-05 scalar figure labels or plotting provenance differ')
    for name,sha in figure['files'].items():require(name in ('control-projection.svg','control-projection.png') and digest(query[name])==sha,'REVIEW-05 figure hash differs')
    require(any(r.get('fixture')=='FAMILY-QUERY-FLAT' and r['horizon']==2 and r['problem_id']==figure['source_problem_id'] and
                r['scenario_sha256']==figure['scenario_sha256'] and r.get('witnesses')==figure['histories'] for r in records),
            'REVIEW-05 figure is not bound to an independently checked scalar query record')
    verification={'query':query_counts,'phase':phase_counts,'profiler':dict(Counter(profile_statuses)),
        'scope':'current exact-dyadic fixed-fixture family inclusion, literal history/direction minimum and bound report inputs; no solver execution',
        'current_checkers':{name:digest((BENCH/(name+'.py')).read_bytes()) for name in
            ('check_family_query','scalar_query_oracle','render_family_query','check_build_phases','run_build_phases')}}
    return {QUERY_ID:query,PHASE_ID:phase},verification


def _index(path):
    require(not path.is_symlink() and path.is_file(),'Pages index must be a regular file')
    text=path.read_text(encoding='utf-8');require(len(re.findall(r'<body\b',text,re.I))==1 and text.count('</body>')==1,
        'Pages index must have one body insertion point');return text


def _example_card(site,marker,card):
    path=site/'examples/index.html';text=_index(path);require(marker not in text,'REVIEW-05 examples marker already exists')
    path.write_text(text.replace('</body>',card+'</body>'),encoding='utf-8')


def stage(site,query_source=QUERY_SOURCE,phase_source=PHASE_SOURCE,*,example_card_writer=None):
    """Callable augmentation hook; freshness/deployment stays in managed CI."""
    site=Path(site);require(not site.is_symlink() and site.is_dir(),'Pages site must be a regular directory')
    require(not (site/'examples').is_symlink() and (site/'examples').is_dir(),'Pages examples directory must be regular')
    landing=_index(site/'index.html');gallery=_index(site/'examples/index.html')
    historical_readme=_historical_route_readme();historical_metadata=_historical_route_metadata()
    for route,content in ((HISTORICAL_ROUTE_ALIAS,historical_readme),(HISTORICAL_ROUTE_METADATA_ALIAS,historical_metadata)):
        alias=site.joinpath(*route.parts)
        if alias.exists():require(alias.is_file() and not alias.is_symlink() and alias.read_bytes()==content,
                                  'historical REVIEW-05 route asset conflicts with its source bytes')
        else:require(not alias.is_symlink(),'historical REVIEW-05 route asset is unsafe')
    identity={'reviewed_manifests':ANCHORS,'stager_sha256':digest(Path(__file__).read_bytes()),
        'current_checkers':{name:digest((BENCH/(name+'.py')).read_bytes()) for name in
            ('check_family_query','scalar_query_oracle','render_family_query','check_build_phases','run_build_phases')}}
    route='review05-family-query-'+digest(json.dumps(identity,sort_keys=True,separators=(',',':')).encode())[:20]
    require(not (site/route).exists() and not (site/route).is_symlink() and not (site/(route+'.zip')).exists() and
            not (site/(route+'.zip')).is_symlink() and route not in landing and route not in gallery,'immutable REVIEW-05 route already exists')
    frozen,verification=validate(query_source,phase_source)
    generated={f'{key}/{name}':content for key,files in frozen.items() for name,content in files.items()}
    generated['index.html']=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Complete scalar families and query evidence</title>
<style>body{{font:16px/1.6 system-ui;background:#1e1e2e;color:#cdd6f4;max-width:1100px;margin:3rem auto;padding:0 1.5rem}}a{{color:#89b4fa}}h1,h2{{color:#a6e3a1}}img{{max-width:100%;height:auto}}code{{color:#f9e2af}}</style><body>
<h1>Complete scalar optimizer families and actual queries</h1><p><strong>Performance verdict: inconclusive.</strong> The bounded T=2/4/8 observations retain all complete-family/query outcomes, warmups, resource stops and separate profiling. No ranking, asymptotic or hard real-time guarantee is claimed.</p>
<p><a href="{QUERY_ID}/index.html">Frozen family-query report</a> · <a href="{PHASE_ID}/index.html">Actual assembly/program-construction phases</a> · <a href="publication-manifest.json">Publication provenance</a> · <a href="../{route}.zip">Complete publication ZIP</a> · <a href="{QUERY_ID}/offline.zip">Original immutable raw ZIP</a> · <a href="../benchmarks/reporting/review05/route-retirement.json">Historical guide source and route receipt</a></p>
<section id="scalar-2d"><h2>A minimal two-control example; scalar state dimension 1</h2>
<p>Inputs: <code>x[t+1]=x[t]+u[t], x[0]=0, T=2, 0≤u[t]≤1</code>; original terminal objective is constant zero. Thus <code>x1=u0</code> and <code>x2=u0+u1</code>. The full optimizer family projects to the complete control square <code>[0,1]²</code>. Coverage does not follow from selected witnesses: the current independent fixture checker establishes both H-family inclusions, separately from each selected history and direction optimum. Library assurance remains numerical.</p>
<img src="{QUERY_ID}/control-projection.svg" alt="Scalar state n=1, T=2: complete u0/u1 control square and recorded selected scalar state paths">
<p><a href="{QUERY_ID}/scenarios/family-query-flat-t02.json">Complete minimal input</a> · <a href="{QUERY_ID}/figure-export.json">Recorded paths and plotting provenance</a> · <a href="{QUERY_ID}/control-projection.png">PNG</a> · <a href="{QUERY_ID}/REPRODUCE.md">Offline checks and reproduction</a></p></section>
<p>168 primary query attempts and 84 phase attempts currently verify; two deliberate materialization resource stops in each capture remain inconclusive. Forty separate profiler histories verify and never enter primary timing distributions. Generic membership/slice APIs and isolated verifier timing were not measured. Original checks, summaries, source snapshots and raw ZIP bytes below are copied unchanged; current proof statuses and checker fingerprints are recorded separately in the publication manifest.</p>
<p>Native source commits: <a href="https://github.com/butahlecoq/controlled-systems-lab/commit/{CAPTURES[QUERY_ID]}">{CAPTURES[QUERY_ID]}</a> and <a href="https://github.com/butahlecoq/controlled-systems-lab/commit/{CAPTURES[PHASE_ID]}">{CAPTURES[PHASE_ID]}</a>. The supported strategy is nominal open-loop scalar synthesis; this is not a nonlinear/controller restoration claim. See the frozen reports for numerical scope and unavailable counters. Issue #95 remains open until its remaining integration/evidence gates pass.</p></body></html>'''.encode()
    generated['README.md']=('''# Immutable REVIEW-05 publication

The two named report subdirectories are byte-preserved frozen evidence. Their
original SHA256SUMS, checks, source snapshots, timings and raw ZIP are unchanged.
The outer publication manifest records current independent rechecks separately.

After downloading/extracting the publication ZIP into a fresh directory, enter
this route and run `sha256sum -c SHA256SUMS`. For complete raw query data, verify
the frozen query manifest, then extract its `offline.zip` into a new empty folder.
Inside that folder run `sha256sum -c SHA256SUMS`, followed by
`python3 post-capture/check_family_query.py .`. This executes only independent
checks; it never runs the recorded native binary. The frozen REPRODUCE.md names
the optional plotting environment and distinguishes historical host paths from
portable commands. The phase report's REPRODUCE.md similarly checks saved data.

Publication happens only through the existing reviewed main/CI deployment path
and its current-head freshness gate. This local stager does not deploy anything.
''').encode()
    manifest={'schema':'csl.review05.publication/1','report_id':route,'identity':identity,'verification':verification,
        'source_files':{key:{name:digest(content) for name,content in sorted(files.items())} for key,files in frozen.items()},
        'published_files':{name:digest(content) for name,content in sorted(generated.items())}}
    generated['publication-manifest.json']=(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode()
    generated['SHA256SUMS']=''.join(f'{digest(content)}  {name}\n' for name,content in sorted(generated.items())).encode('ascii')
    # Use existing discovery/link helpers against scratch indexes first. Only
    # after source proof and output preflight succeed do real staging writes run.
    if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
    from scripts.reports.mpc01.stage_per_attempt import _insert_landing_link
    from scripts.reports.landing import links_html
    card=(f'<article class="saved-figure" id="{route}-scalar-example"><p class="eyebrow">Scalar optimal family · saved query histories</p>'
          f'<h3><a href="../{route}/index.html#scalar-2d">Two control coordinates; scalar state dimension 1</a></h3>'
          f'<a href="../{route}/index.html#scalar-2d"><img src="../{route}/{QUERY_ID}/control-projection.svg" alt="Scalar n=1; complete control square and recorded state paths"></a>'
          '<p>The full control square is checked independently; selected paths do not establish coverage. Performance comparison remains inconclusive.</p>'
          '<p>'+links_html((('Report and minimal inputs',f'../{route}/index.html#scalar-2d'),('Raw evidence ZIP',f'../{route}/{QUERY_ID}/offline.zip')))+ '</p></article>')
    with tempfile.TemporaryDirectory(prefix='review05-publication-stage-') as temporary:
        scratch=Path(temporary);(scratch/'examples').mkdir();(scratch/'index.html').write_text(landing);(scratch/'examples/index.html').write_text(gallery)
        _insert_landing_link(scratch,route+'-archive',route+'/index.html','Complete scalar optimizer families, actual query observations and 2D example')
        (example_card_writer or _example_card)(scratch,route+'-scalar-example',card)
        staged_landing=(scratch/'index.html').read_bytes();staged_gallery=(scratch/'examples/index.html').read_bytes()
        require(route+'/index.html#scalar-2d' in staged_gallery.decode(),'example helper did not retain REVIEW-05 discovery link')
        archive_path=scratch/(route+'.zip')
        with zipfile.ZipFile(archive_path,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            for name,content in sorted(generated.items()):
                entry=zipfile.ZipInfo(route+'/'+name,date_time=(2026,1,1,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED;entry.external_attr=0o100644<<16
                archive.writestr(entry,content)
        destination=site/route;destination.mkdir()
        for name,content in generated.items():
            target=destination.joinpath(*_name(name).parts);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
        with (site/(route+'.zip')).open('xb') as output:output.write(archive_path.read_bytes())
        (site/'index.html').write_bytes(staged_landing);(site/'examples/index.html').write_bytes(staged_gallery)
    _write_historical_route_aliases(site,historical_readme,historical_metadata)
    return route


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--site',required=True,type=Path)
    parser.add_argument('--query-source',type=Path,default=QUERY_SOURCE);parser.add_argument('--phase-source',type=Path,default=PHASE_SOURCE)
    args=parser.parse_args();print(stage(args.site,args.query_source,args.phase_source))
