"""Stage immutable native episode records and saved full-state projections."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = 'reports/closed-loop-native-fixed-tail/a6-v1'
ROUTE = 'native-fixed-tail-episodes-a6'
TASKS = (('syn-nl-lv-01', 'Lotka–Volterra', 30), ('syn-nl-fuel-01', 'Fuel', 40), ('earth-orbit', 'Orbit', 20))
FAMILIES = ('polytope', 'box', 'zonotope', 'parallelotope', 'ellipsoid')


def checked_files(source):
    if source.is_symlink() or not source.is_dir():
        raise ValueError('native episode bundle is missing or symlinked')
    files = {}
    for line in (source / 'files.sha256').read_text().splitlines():
        digest, name = line.split('  ', 1)
        parts = Path(name).parts
        path = source / name
        if (name in files or not parts or '..' in parts or Path(name).is_absolute()
                or not path.resolve().is_relative_to(source.resolve())
                or any(source.joinpath(*parts[:i]).is_symlink() for i in range(1, len(parts)+1))):
            raise ValueError('unsafe native episode manifest path')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('native episode bytes differ from frozen manifest: ' + name)
        files[name] = raw
    actual = {p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file() and p.name != 'files.sha256'}
    if actual != set(files):
        raise ValueError('native episode manifest file set differs')
    files['files.sha256'] = (source / 'files.sha256').read_bytes()
    return files


def check_zip(path, receipt):
    if hashlib.sha256(path.read_bytes()).hexdigest() != receipt['raw_zip_sha256']:
        raise ValueError('native episode ZIP hash differs from its receipt')
    with zipfile.ZipFile(path) as archive:
        if set(archive.namelist()) != set(receipt['archive_members']):
            raise ValueError('native episode ZIP members differ from the verified export')
        for name, member in receipt['archive_members'].items():
            info = archive.getinfo(name)
            if info.file_size != member['bytes'] or f'{info.CRC:08x}' != member['crc32']:
                raise ValueError('native episode ZIP size/CRC differs from the verified export')
        episode = json.loads(archive.read('attempt.json'))
        for field in ('task_id', 'task_sha256', 'objective_id', 'action_profile_id', 'controller_id', 'completed_holds', 'original_intervals'):
            if episode[field] != receipt[field]:
                raise ValueError('native archive identity differs from its receipt: ' + field)
        if (episode['resolved_graph']['graph_id'] != receipt['graph_id'] or
                episode['resolved_graph']['graph_fingerprint'] != receipt['graph_fingerprint']):
            raise ValueError('native archive graph differs from its receipt')
        if episode['physical_objective'] != receipt['physical_objective']:
            raise ValueError('native episode cost differs between archive and receipt')
        if 'worker-stderr.txt' not in archive.namelist():
            raise ValueError('native episode shared process stderr is missing')
        return episode


def page(records, provenance):
    cells = {row['name']: row for row in records}
    table = ''.join('<tr><th scope="row"><a href="#' + name + '">' + title + f' ({horizon})</a></th>' +
        ''.join(f'<td>{cells[name+"-"+family]["physical_objective"]["total"]:.6g}</td>' for family in FAMILIES) + '</tr>'
        for name, title, horizon in TASKS)
    sections = []
    for name, title, horizon in TASKS:
        planes = 1 if name == 'syn-nl-lv-01' else 2
        downloads = ' · '.join(f'<a href="records/{name}-{family}/raw.zip">{family} raw ZIP</a> / <a href="records/{name}-{family}/receipt.json">receipt</a>' for family in FAMILIES)
        figures = []
        for plane in range(1, planes+1):
            family_views = ''.join(f'<details><summary>{family}: enlarge this projection</summary><img src="figures/{name}/{family}-plane-{plane}.svg" alt="{title} {family}: all initial-query physical stage regions and actual nonlinear trajectory"></details>' for family in FAMILIES)
            figures.append(f'<figure><a href="figures/{name}/plane-{plane}.svg"><img src="figures/{name}/plane-{plane}.svg" alt="{title}: all five physical families, every initial-query stage, and actual nonlinear closed-loop trajectories"></a><figcaption>Projection {plane}; all {horizon+1} state stages from query 0. The gold path is the actual nonlinear episode. Open the overview or an individual family view to enlarge.</figcaption></figure>{family_views}')
        mapping = ('<p>Oxidizer: (m<sub>ox</sub>, q<sub>ox</sub>), stored indices (0, 2). Fuel: (m<sub>f</sub>, q<sub>f</sub>), stored indices (1, 3). The stored four-state order remains (m<sub>ox</sub>, m<sub>f</sub>, q<sub>ox</sub>, q<sub>f</sub>). Every set is formed in 4D before projection.</p>' if name == 'syn-nl-fuel-01' else '')
        sections.append(f'<section id="{name}"><h2>{title}: {horizon} original holds</h2><p>State dimension {2 if name == "syn-nl-lv-01" else 4}; continuous input dimension {1 if name == "syn-nl-lv-01" else 2}; one player. Every displayed stage uses the original physical coordinates.</p>{mapping}{"".join(figures)}<p>{downloads}</p><p><a href="figures/{name}/projection-receipt.json">Projection data and source hashes</a></p></section>')
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Native fixed-tail control: three tasks, five families</title><link rel="stylesheet" href="../examples.css"></head><body><a class="skip" href="#main">Skip to evidence</a><main id="main" class="page-content"><nav class="breadcrumbs" aria-label="Breadcrumb"><ol><li><a href="../../index.html">Learn</a></li><li><a href="../index.html">Examples</a></li><li aria-current="page">Native fixed-tail episodes</li></ol></nav>
<p class="eyebrow">Saved functional evidence · source a6b7d1cb</p><h1>One native controller, three nonlinear tasks, five physical families</h1>
<p>All 15 single-player episodes completed their original horizons with independent replay, checks and rendering complete. The C++ controller optimizes the current continuous action using a feasible fixed future tail and every selected physical state region. <a href="../native-fixed-tail-2d.html">Start with the compact 2D mathematical example</a>.</p>
<div class="scroll" role="region" aria-label="Complete physical source cost by task and physical family" tabindex="0"><table style="min-width:760px"><thead><tr><th>Task (holds)</th>{''.join('<th>'+family+'</th>' for family in FAMILIES)}</tr></thead><tbody>{table}</tbody></table></div>
<p>Each cell is the complete original physical terminal-plus-running cost J for one recorded episode. Compare within a row. These are numerical functional outcomes, with no comparative performance ranking or global-policy optimality claim.</p>
<p><a href="#syn-nl-lv-01">Lotka–Volterra</a> · <a href="#syn-nl-fuel-01">Fuel</a> · <a href="#earth-orbit">Orbit</a> · <a href="independent-audit.json">Read-only saved-record audit</a> · <a href="provenance.json">Source and scope</a></p>
<h2>Read the sets and trajectories together</h2><p>Pale outlines are finite all-control axis carriers. Coloured outlines are admitted physical regions B conditional on the feasible fixed tail; carrier constraints participate in B admission, so carrier ∩ B = B here. Purple to yellow identifies successive stages. The dashed path is the initial affine recovered history, the gold path is the actual nonlinear closed loop, the red point is the initial state, the gold star is the final observed point, and a white cross is a soft objective reference where both plotted coordinates have one.</p>
<p>The policy recomputes its regions after every observed hold. Initial-query sets do not certify the subsequent nonlinear trajectory. These conditional regions are not global backward reachable sets. Sampled replay checks are numerical evidence, not continuous-time safety certificates.</p>
{''.join(sections)}
<h2>Keep source revisions separate</h2><p>All full episodes use source <a href="https://github.com/butahlecoq/controlled-systems-lab/commit/{provenance['episode_source_commit']}">{provenance['episode_source_commit']}</a>, with native C++ build <a href="https://github.com/butahlecoq/controlled-systems-lab/commit/{provenance['native_cpp_source_commit']}">{provenance['native_cpp_source_commit']}</a>. The read-only audit checks 450 native queries and 7,925 physical-region instances against original source H/J, literal shifted histories, supplied zero duals, exact command bounds, raw-reference hashes and complete physical costs. Native stderr is retained in the shared supervised worker/native process stream.</p>
<p class="note">The a6 campaign predates the finer construction-role event trace. Its numerical, warm and stream evidence remains tied to that source; it does not establish current construction-role coverage. Separate <a href="current-role-probe-audit.json">f940 initial-query probes</a> validate declared versus native-observed reference construction, discarded polytope anchor admission and retained family-template construction across all 15 profiles. These probes are not full episodes and do not relabel earlier captures. <a href="current-role-probes.zip">Download their raw records</a>.</p>
<p>The preserved <a href="historical-orbit-polytope-prefix/raw.zip">historical orbit polytope prefix</a> stopped after 1/20 holds when the raw optimizer missed an actuator bound by about 6×10⁻¹³. Native guarded endpoint recovery fixed that execution failure. The historical recorder discarded separate native stderr; those bytes cannot be reconstructed. <a href="historical-orbit-polytope-prefix/qualification.json">Read its qualification</a>.</p>
<h2>Reproduce the reading layer</h2><p>Each raw ZIP preserves the original attempt, stage records, requests, responses, solver diagnostics, shared stderr, graph identity, replay and postcheck outputs. Receipts retain source/binary hashes and every archive member hash. No native executable is distributed in these data archives.</p><p><a href="source-build-receipt.json">Original build receipt</a> · <a href="audit-source.py">Audit source snapshot</a> · <a href="render-source.py">Saved-data renderer</a> · <a href="role-audit-source.py">Role-probe audit source</a> · <a href="files.sha256">Frozen file hashes</a></p>
<p>Regenerate projections from the saved a6 attempt tree and its source checkout with the renderer’s <code>--source-root</code>, <code>--root</code>, <code>--task</code> and <code>--output</code> arguments. The producer reads saved data and executes no controller. Full module-composition coverage, review and deployed URL/hash verification remain separate gates.</p></main></body></html>'''.encode()


def build(root=ROOT):
    source = root / SOURCE
    files = checked_files(source)
    records = json.loads(files['records.json'])
    expected = {name+'-'+family for name, _, _ in TASKS for family in FAMILIES}
    if len(records) != 15 or {row['name'] for row in records} != expected:
        raise ValueError('native episode task/family matrix differs')
    for record in records:
        if record['receipt'] != f"records/{record['name']}/receipt.json" or record['raw'] != f"records/{record['name']}/raw.zip":
            raise ValueError('native record path differs from its named profile')
        receipt = json.loads(files[record['receipt']])
        episode = check_zip(source / record['raw'], receipt)
        name, family = record['name'].rsplit('-', 1)
        horizon = next(count for task, _, count in TASKS if task == name)
        if (episode['original_intervals'] != horizon or episode['controller_id'] != f'native-fixed-tail-{family}-ipopt/1'
                or episode['resolved_graph']['role_bindings']['representation']['id'] != family
                or episode['completed_holds'] != episode['original_intervals']
                or any(episode[field] != 'complete' for field in ('algorithm_status', 'postcheck_status', 'render_status'))
                or episode['resolved_graph']['controller']['adapter'] != 'native_fixed_tail'
                or episode['physical_objective'] != record['physical_objective']):
            raise ValueError('native episode does not match its completed source-qualified record')
    audit = json.loads(files['independent-audit.json'])
    roles = json.loads(files['current-role-probe-audit.json'])
    if not audit['all_accepted'] or audit['queries'] != 450 or audit['physical_regions_checked'] != 7925 or not roles['all_accepted']:
        raise ValueError('native episode or separate role-probe audit is incomplete')
    assets = {ROUTE+'/'+name: value for name, value in files.items()}
    provenance = json.loads(files['provenance.json'])
    assets[ROUTE+'/index.html'] = page(records, provenance)
    entry = {'family': 'Native set-based control', 'title': 'Three nonlinear tasks × five physical families',
        'status': 'saved-data-companion', 'anchor': ROUTE, 'page': ROUTE+'/index.html',
        'figure': ROUTE+'/figures/syn-nl-lv-01/plane-1.svg',
        'source_page': 'https://github.com/butahlecoq/controlled-systems-lab/commit/'+provenance['episode_source_commit'],
        'raw_record': ROUTE+'/independent-audit.json'}
    card = f'<article class="saved-figure" id="{ROUTE}"><h3>Native fixed-tail control: 15 nonlinear episodes</h3><a href="{entry["page"]}"><img src="{entry["figure"]}" alt="Five physical families with every initial-query stage and actual Lotka–Volterra trajectories"></a><p>Lotka–Volterra, fuel and orbit retain their original horizons, complete source costs and immutable raw records.</p><p><a href="{entry["page"]}">Open the source-qualified episodes →</a></p></article>'
    return assets, entry, card
