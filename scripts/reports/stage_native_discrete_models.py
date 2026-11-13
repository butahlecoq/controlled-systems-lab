"""Stage a frozen native model-data and observed-state MPC learning bundle."""
from __future__ import annotations

import hashlib
import json
import zipfile
from html import escape
from pathlib import Path

from report_data import require
from stage_native_model_catalogue import _file

ROUTE = 'native-discrete-models-v1'
SOURCE = '856d7a77c49fca0c6f6cdb8c1a1db9a651da85cb'
MANIFEST_SHA256 = '9d0cdfc6853cab2ada99c311fdfa455ebd2d040300cb0d7d5b37288f6990ca6f'
PAGES = ('native-discrete-models.html', 'native-quadcopter-mpc.html')


def build(repository_root: Path) -> tuple[dict[str, bytes], list[dict[str, str]], str]:
    repository_root = Path(repository_root)
    root = repository_root
    for part in ('reports', 'algorithm-results', ROUTE):
        root /= part
        require(not root.is_symlink(), 'native discrete bundle ancestor is symlinked')
    manifest_bytes = _file(root, 'manifest.json').read_bytes()
    require(hashlib.sha256(manifest_bytes).hexdigest() == MANIFEST_SHA256,
            'native discrete manifest differs from frozen publication identity')
    manifest = json.loads(manifest_bytes)
    require(manifest['source_commit'] == SOURCE and
            manifest['schema'] == 'csl.native-discrete-models.functional/1', 'native discrete source differs')
    files = {'manifest.json': manifest_bytes}
    for name, expected in manifest['files_sha256'].items():
        content = _file(root, name).read_bytes()
        require(hashlib.sha256(content).hexdigest() == expected, 'native discrete digest differs: '+name)
        files[name] = content
    pages = {}
    for name, expected in manifest['lesson_sha256'].items():
        content = _file(repository_root / 'docs/examples', name).read_bytes()
        require(hashlib.sha256(content).hexdigest() == expected, 'native discrete lesson differs: '+name)
        pages[name] = content
    require(set(pages) == set(PAGES), 'native discrete lesson inventory differs')
    expected_archive = {ROUTE+'/'+name: content for name, content in files.items()} | pages
    expected_archive['examples.css'] = files['offline-examples.css']
    archive_name = ROUTE+'.zip'
    archive_bytes = _file(root, archive_name).read_bytes()
    with zipfile.ZipFile(_file(root, archive_name)) as archive:
        require(len(archive.namelist()) == len(expected_archive) and
                set(archive.namelist()) == set(expected_archive) and archive.testzip() is None,
                'native discrete archive members differ')
        for name, content in expected_archive.items():
            require(archive.read(name) == content, 'native discrete archive bytes differ: '+name)
    files[archive_name] = archive_bytes
    checksum = _file(root, archive_name+'.sha256').read_bytes()
    require(checksum.decode().strip() == hashlib.sha256(archive_bytes).hexdigest()+'  '+archive_name,
            'native discrete archive checksum differs')
    files[archive_name+'.sha256'] = checksum
    paths = list(root.rglob('*'))
    require(all(not path.is_symlink() for path in paths), 'native discrete asset is symlinked')
    require({path.relative_to(root).as_posix() for path in paths if path.is_file()} == set(files),
            'native discrete bundle contains unlisted files')
    outputs = {ROUTE+'/'+name: content for name, content in files.items()} | {name: pages[name] for name in PAGES}
    title = '35 native models and a complete 12-state MPC example'
    entry = {'family': 'Native mathematical models', 'title': title, 'status': 'educational-example',
             'anchor': 'native-quadcopter-mpc', 'page': PAGES[1],
             'figure': ROUTE+'/phase-x3-x6-screen.svg',
             'source_page': 'https://github.com/butahlecoq/controlled-systems-lab/tree/'+SOURCE,
             'raw_record': ROUTE+'/manifest.json'}
    card = ('<article class="saved-figure" id="native-quadcopter-mpc"><p class="eyebrow">Native C++ · observed-state MPC</p>'
            f'<h3><a href="{PAGES[1]}">{escape(title)}</a></h3>'
            f'<a href="{PAGES[1]}"><img src="{entry["figure"]}" alt="All 15 predicted paths and the executed 12-state MPC path in indexed plane x3-x6"></a>'
            '<p>A ten-stage HiGHS problem, all saved predictions, all state/input traces, and source-qualified native model data.</p>'
            f'<p><a href="{PAGES[1]}">Read the MPC lesson →</a> · <a href="{PAGES[0]}">Browse all 35 models</a></p></article>')
    return outputs, [entry], card
