"""Validate and stage the complete MPC-06 source/report artifact, never a binary."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.reports.mpc06_delivery import records,figures

SOURCE=ROOT/'reports/algorithm-results/mpc06-completion-v2'


def digest(data):return hashlib.sha256(data).hexdigest()


def validate(source):
    contents=records.inventory(source)
    records.validate(source/'input')
    with tempfile.TemporaryDirectory(prefix='mpc06-publication-check-') as temporary:
        generated=Path(temporary)/'report';figures.render(source/'input',generated)
        expected={path.relative_to(generated).as_posix():path.read_bytes() for path in generated.rglob('*') if path.is_file()}
        if contents!=expected:raise ValueError('saved MPC-06 publication differs from checked-data rendering')
    return contents


def stage(source,site):
    contents=validate(source)
    if site.is_symlink() or not site.is_dir():raise ValueError('publication site must be a regular directory')
    landing=site/'index.html'
    if landing.is_symlink() or not landing.is_file():raise ValueError('publication landing page is missing')
    page=landing.read_text(encoding='utf-8')
    if page.count('</body>')!=1:raise ValueError('publication landing insertion point differs')
    identities={name:digest(data) for name,data in sorted(contents.items())}
    route='mpc06-complete-'+digest(json.dumps(identities,sort_keys=True,separators=(',',':')).encode())[:20]
    destination=site/route;archive_path=site/(route+'.zip')
    if destination.exists() or archive_path.exists():raise ValueError('immutable MPC-06 publication destination already exists')
    generated=dict(contents)
    record=json.loads(contents['input/result.json'])
    manifest=dict(schema='csl.mpc06-completion-publication/1',report_id=route,source_report_id=source.name,
        source_commit=record['source_commit'],native_source_commit=record['native_source_commit'],
        source_files=identities,published_files={name:digest(data) for name,data in sorted(generated.items()) if name!='SHA256SUMS'},
        evidence_scope='exact fixed-policy N3 class minima and matched held-native plans; receding-prefix cost remains separate; no causal optimum')
    generated['publication-manifest.json']=(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode()
    generated['SHA256SUMS']=''.join(f'{digest(data)}  {name}\n' for name,data in sorted(generated.items()) if name!='SHA256SUMS').encode()
    destination.mkdir()
    for name,data in generated.items():
        target=destination/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    with zipfile.ZipFile(archive_path,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(generated.items()):
            item=zipfile.ZipInfo(route+'/'+name,date_time=(2026,1,1,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED;item.external_attr=0o100644<<16
            archive.writestr(item,data)
    link=(f'<section><h2>Tube MPC and exact tiny policy references</h2><p>Matched robust checks, actual online QPs, '
          f'fixed-open-loop and prescribed-feedback finite-horizon minimax references, and independently checked invariant/tightening figures. '
          f'No general causal optimum or universal performance winner is claimed. <a href="{route}/index.html">Open the report</a> · '
          f'<a href="{route}.zip">Download the offline source/report bundle</a>.</p></section>')
    landing.write_text(page.replace('</body>',link+'</body>'),encoding='utf-8')
    return route


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',type=Path,default=SOURCE);parser.add_argument('--site',required=True,type=Path);args=parser.parse_args();print(stage(args.source,args.site))
