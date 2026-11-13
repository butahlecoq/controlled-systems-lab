"""Freeze and render saved native parallelotope episodes; never execute a controller."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from html import escape
import json
from pathlib import Path
import shutil
import itertools
import re
import subprocess
import sys
import zipfile

if __package__:
    from .package_history_functional import archive_attempt
    from .native_fixed_tail_episode_report import checked_files
    from .figure_style import configure_numeric_axis
    from .recorded_closed_loop_figures import _convex_hull
else:
    from package_history_functional import archive_attempt
    from native_fixed_tail_episode_report import checked_files
    from figure_style import configure_numeric_axis
    from recorded_closed_loop_figures import _convex_hull

ROOT = Path(__file__).resolve().parents[2]
NAME = 'native-parallelotope-d6fc-v1'
SOURCE = 'd6fc399abcca49d4ac96fabeed9d8878d11cf326'
FRAME_SOURCE_SHA256 = '503bac686cf35038e6fd3d15be76438ed80ecd301fec5b894466a34d6ea8acba'
BUNDLE = ROOT / 'reports/closed-loop-history-functional' / NAME
TASKS = (('syn-nl-lv-01', 'Lotka–Volterra', 30, ((0, 1),)),
         ('earth-orbit', 'Earth orbit', 20, ((0, 1), (2, 3))),
         ('syn-nl-fuel-01', 'Fuel', 40, ((2, 0), (3, 1))))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def episode(archive):
    return json.loads(archive.read('attempt.json'))


def checked_archive(path, inventory):
    with zipfile.ZipFile(path) as archive:
        if len(archive.namelist()) != len(inventory) or set(archive.namelist()) != set(inventory):
            raise ValueError('raw archive member set differs')
        for name, expected in inventory.items():
            raw = archive.read(name)
            if len(raw) != expected['bytes'] or sha(raw) != expected['sha256']:
                raise ValueError('raw archive bytes differ: ' + name)


def frame(dimension):
    if dimension == 2:
        return [[1, 0], [0, 1]]
    if dimension == 4:
        return [[1, 1, 0, 0], [0, 1, 1, 0], [0, 0, 1, 1], [0, 0, 0, 1]]
    raise ValueError('unsupported source frame dimension')


def physical_corners(bounds, matrix):
    dimension = len(matrix)
    return [[sum(matrix[i][j] * point[j] for j in range(dimension)) for i in range(dimension)]
            for point in itertools.product(*zip(bounds['lower'], bounds['upper']))]


def check_source_frame(bundle):
    receipt = json.loads((bundle / 'qualification/frame-receipt.json').read_bytes())
    raw = (bundle / 'qualification/finite_plan_parallelotope.cpp').read_bytes()
    text = raw.decode()
    if receipt['source_commit'] != SOURCE or receipt['source_sha256'] != sha(raw) or sha(raw) != FRAME_SOURCE_SHA256:
        raise ValueError('source frame provenance differs')
    match = re.search(r'constexpr int q\[4\]\[4\] =\s*\{(.*?)\};', text, re.S)
    if not match or list(map(int, re.findall(r'-?\d+', match.group(1)))) != sum(frame(4), []):
        raise ValueError('four-state frame differs from source')
    if 'Matrix{n, n, {1.0, 0.0, 0.0, 1.0}}' not in text:
        raise ValueError('planar identity frame differs from source')
    # Both frames are initialized once before propagation and never reassigned.
    if text.count('trace.frame') != 5:
        raise ValueError('review source frame assignments before accepting a new source')


def check(bundle):
    checked_files(bundle)
    check_source_frame(bundle)
    manifest = json.loads((bundle / 'manifest.json').read_bytes())
    if manifest['source_commit'] != SOURCE:
        raise ValueError('unexpected source revision')
    qualification = json.loads((bundle / 'qualification/qualification-receipt.json').read_bytes())
    if qualification['head'] != SOURCE:
        raise ValueError('qualification source differs')
    for name, _, horizon, _ in TASKS:
        row = manifest['tasks'][name]
        checked_archive(bundle / name / 'raw.zip', row['archive_members'])
        with zipfile.ZipFile(bundle / name / 'raw.zip') as archive:
            a = episode(archive)
            if a['completed_holds'] != horizon or a['original_intervals'] != horizon:
                raise ValueError('episode horizon differs')
            if any(a[k] != 'complete' for k in ('algorithm_status', 'postcheck_status', 'render_status', 'overall_status')):
                raise ValueError('episode is incomplete')
            task = json.loads((bundle / name / 'task.json').read_bytes())
            task_hash = sha(json.dumps(task, sort_keys=True, separators=(',', ':'), allow_nan=False).encode())
            if task_hash != a['task_sha256'] or a['controller_id'] != 'native-parallelotope-fixed-plan-mpc/1':
                raise ValueError('task or controller identity differs')
            if a['preparation_receipt']['adapter_receipt']['executable_sha256'] != qualification['new_binaries']['history_policy']:
                raise ValueError('native executable identity differs')
            if json.loads(archive.read('request.json'))['source_commit'] != SOURCE:
                raise ValueError('request source differs')
            if a['physical_objective'] != row['physical_objective']:
                raise ValueError('objective differs')
            for i in range(horizon):
                stage = json.loads(archive.read(f'stage-{i:03d}.json'))
                raw = json.loads(archive.read(f'native-query-{i:03d}-response.jsonl'))
                if raw['build_backend_profile'] != qualification['runtime_profile']:
                    raise ValueError('runtime profile differs')
                if raw != stage['query_receipt']['bridge_response'] or raw['status'] != 'accepted':
                    raise ValueError('stage response differs')
                if len(raw['predicted_sets']) != 1 or len(raw['predicted_sets'][0]['stages']) != horizon-i+1:
                    raise ValueError('missing predicted stages')
            data = json.loads((bundle / name / 'figure-data.json').read_bytes())
            if data != figure_data(archive):
                raise ValueError('figure data differ from saved episode')
            check_physical_sets(data)
    return manifest


def check_physical_sets(data):
    import numpy as np
    matrix = np.asarray(data['source_derived_frame'], dtype=float)
    inverse = np.linalg.inv(matrix)
    for query in data['queries']:
        for bounds, state in zip(query['sets'][0]['stages'], query['plan']['states']):
            # A selected affine path must lie in the corresponding transported frame box.
            y = inverse @ np.asarray(state)
            tolerance = 1e-10 + 1e-12 * max(abs(v) for v in y)
            if any(v < lo-tolerance or v > hi+tolerance
                   for v,lo,hi in zip(y,bounds['lower'],bounds['upper'])):
                raise ValueError('selected affine path lies outside source-derived frame bounds')
            for corner in physical_corners(bounds, data['source_derived_frame']):
                recovered = inverse @ np.asarray(corner)
                if any(v < lo-tolerance or v > hi+tolerance
                       for v,lo,hi in zip(recovered,bounds['lower'],bounds['upper'])):
                    raise ValueError('physical corner does not recover its raw frame box')


def figure_data(archive):
    a = episode(archive)
    queries = []
    for i in range(a['completed_holds']):
        filename = f'native-query-{i:03d}-response.jsonl'
        raw = archive.read(filename)
        response = json.loads(raw)
        queries.append({'update': i, 'source': filename, 'sha256': sha(raw),
                        'sets': response['predicted_sets'], 'plan': response['selected_plan'],
                        'coverage': response['query_receipt']['search_coverage']})
    return {'source_derived_frame': frame(len(a['physical_states'][0])),
            'frame_provenance': 'qualification/finite_plan_parallelotope.cpp at ' + SOURCE,
            'attempt_sha256': sha(archive.read('attempt.json')), 'states': a['physical_states'],
            'controls': a['controls'], 'queries': queries}


def freeze(episodes, qualification, output):
    if output.exists():
        raise ValueError('freeze destination already exists')
    output.mkdir(parents=True)
    manifest = {'schema': 'csl.native-parallelotope-functional-publication/1', 'source_commit': SOURCE,
                'scope': 'Saved numerical functional episodes; bounded finite-candidate search; no performance claim',
                'tasks': {}}
    for name, _, horizon, _ in TASKS:
        attempts = list((episodes / name / 'attempts').glob('*/attempt.json'))
        if len(attempts) != 1:
            raise ValueError('expected one saved episode per task')
        directory = output / name
        directory.mkdir()
        inventory = archive_attempt(attempts[0].parent, directory / 'raw.zip')
        with zipfile.ZipFile(directory / 'raw.zip') as archive:
            a = episode(archive)
            if json.loads(archive.read('request.json'))['source_commit'] != SOURCE:
                raise ValueError('episode source differs')
            write_json(directory / 'figure-data.json', figure_data(archive))
            manifest['tasks'][name] = {'attempt_id': a['attempt_id'], 'task_sha256': a['task_sha256'],
                'graph_id': a['resolved_graph']['graph_id'], 'graph_fingerprint': a['resolved_graph']['graph_fingerprint'],
                'physical_objective': a['physical_objective'], 'completed_holds': a['completed_holds'],
                'replay': a['independent_replay'], 'archive_members': inventory}
    for path in sorted(episodes.glob('*.json')):
        shutil.copyfile(path, output / path.name)
    target = output / 'qualification'
    target.mkdir()
    for path in sorted(qualification.glob('*.json')):
        shutil.copyfile(path, target / path.name)
    source_path = 'src/reachability/finite_plan_parallelotope.cpp'
    raw_source = subprocess.check_output(['git', 'show', f'{SOURCE}:{source_path}'], cwd=ROOT)
    (target / 'finite_plan_parallelotope.cpp').write_bytes(raw_source)
    write_json(target / 'frame-receipt.json', {'source_commit': SOURCE, 'source_path': source_path,
        'source_sha256': sha(raw_source), 'planar_frame': frame(2), 'four_state_frame': frame(4),
        'interpretation': 'x=Qy; saved lower/upper bound y; Q is fixed across all stages in each source route'})
    for name in ('history_policy.map', 'nonlinear_replay.map', 'installed-targets.tsv', 'CMakeCache.txt'):
        shutil.copyfile(qualification / 'build' / name, target / name)
    write_json(output / 'manifest.json', manifest)
    sys.path.insert(0, str(ROOT / 'benchmarks/reporting/closed_loop'))
    from contracts import load_task
    for name, *_ in TASKS:
        write_json(output / name / 'task.json', load_task(name))
    shutil.copyfile(Path(__file__), output / 'render-source.py')
    render(output)
    sums = ''.join(f'{sha(p.read_bytes())}  {p.relative_to(output).as_posix()}\n'
                   for p in sorted(output.rglob('*')) if p.is_file() and p.name != 'files.sha256')
    (output / 'files.sha256').write_text(sums)
    check(output)


def render(bundle):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon
    import numpy as np
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'svg.hashsalt': NAME})
    manifest = json.loads((bundle / 'manifest.json').read_bytes())
    sections, table = [], []
    for name, title, horizon, planes in TASKS:
        directory = bundle / name
        task = json.loads((directory / 'task.json').read_bytes())
        data = json.loads((directory / 'figure-data.json').read_bytes())
        states = np.asarray(data['states'])
        dt = task['episode']['dt']
        labels = [f"{f['name']} ({f['unit']})" for f in task['model']['states']]
        figures = []
        for x, y in planes:
            fig, ax = plt.subplots(figsize=(9, 7), layout='constrained')
            fig.patch.set_facecolor('#16161e'); ax.set_facecolor('#16161e')
            for spine in ax.spines.values(): spine.set_color('#908caa')
            ax.tick_params(colors='#e0def4')
            # Every slice from every observed query, including initial and terminal states.
            for query in data['queries']:
                color = plt.colormaps['viridis'](query['update'] / max(horizon-1, 1))
                plan = np.asarray(query['plan']['states'])
                ax.plot(plan[:, x], plan[:, y], color=color, alpha=.32, linewidth=.8)
                for bounds in query['sets'][0]['stages']:
                    corners = physical_corners(bounds, data['source_derived_frame'])
                    polygon = _convex_hull([(point[x], point[y]) for point in corners])
                    if len(polygon) >= 3:
                        ax.add_patch(Polygon(polygon, closed=True, fill=False, edgecolor=color, linewidth=.6, alpha=.6))
                    elif polygon:
                        ax.plot([point[0] for point in polygon], [point[1] for point in polygon], color=color, linewidth=.6, alpha=.6)
            ax.plot(states[:, x], states[:, y], color='#f6c177', linewidth=2, label='Nonlinear execution')
            ax.scatter(states[0,x], states[0,y], marker='o', color='#9ccfd8', label='Initial state', zorder=5)
            ax.scatter(states[-1,x], states[-1,y], marker='s', color='#eb6f92', label='Final state', zorder=5)
            ax.set_xlabel(labels[x], color='#e0def4'); ax.set_ylabel(labels[y], color='#e0def4')
            ax.set_title(f'{title} · native parallelotope finite-plan MPC\nAll {horizon} queries and complete remaining-horizon sets', color='#e0def4')
            configure_numeric_axis(ax)
            legend = ax.legend(facecolor='#24243a', labelcolor='#e0def4')
            for text in legend.get_texts(): text.set_fontsize(10)
            colorbar = fig.colorbar(plt.cm.ScalarMappable(norm=plt.Normalize(0,horizon-1), cmap='viridis'), ax=ax)
            colorbar.set_label('Observed query index', color='#e0def4'); colorbar.ax.tick_params(colors='#e0def4')
            stem = f'all-queries-{x}-{y}'
            for extension in ('svg','png'):
                fig.savefig(directory / f'{stem}.{extension}', dpi=150, metadata={'Date': None} if extension=='svg' else {})
            plt.close(fig)
            figures.append(f'<figure><a href="{name}/{stem}.svg"><img src="{name}/{stem}.png" alt="{escape(title)}: all source-derived physical query-stage polygons, selected affine paths and nonlinear executed trajectory"></a><figcaption>Physical coordinates ({x}, {y}); {horizon} queries, every remaining stage. <a href="{name}/{stem}.svg">Full-size SVG</a>.</figcaption></figure>')
        # Derive correctly labelled state and control traces; leave historical PNGs untouched.
        fig, axes = plt.subplots(len(labels)+1, 1, figsize=(10, 2.3*(len(labels)+1)), sharex=True, layout='constrained')
        for i, label in enumerate(labels):
            axes[i].plot(np.arange(horizon+1)*dt, states[:,i]); axes[i].set_ylabel(label); configure_numeric_axis(axes[i])
        axes[-1].step(np.arange(horizon+1)*dt, data['controls'] + [data['controls'][-1]], where='post'); axes[-1].set_ylabel('Control (task units)')
        axes[-1].set_xlabel(f"Time ({task['episode']['time_unit']})"); configure_numeric_axis(axes[-1])
        fig.suptitle(f'{title} · native parallelotope finite-plan MPC · {horizon}/{horizon} holds')
        fig.savefig(directory / 'traces.png', dpi=150); plt.close(fig)
        row = manifest['tasks'][name]
        coverage = Counter(q['coverage'] for q in data['queries'])
        replay = max(max(r['hold_endpoint_max_abs_difference']) for r in row['replay'].values())
        total = row['physical_objective']['total']
        table.append(f'<tr><th><a href="#{name}">{title}</a></th><td>{horizon}/{horizon}</td><td>{coverage["incomplete"]} / {coverage["complete"]}</td><td>{total:.16g}</td><td>{replay:.3g}</td></tr>')
        initial = data['queries'][0]['plan']['states']
        first_step = f'<p>First-query check: x₀ = {data["states"][0]}, u₀ = {data["controls"][0]}; the recorded affine recurrence gives x₁ = {initial[1]}, while the nonlinear held execution gives {data["states"][1]}. The raw query contains A, B and c to recompute the prediction.</p>'
        sections.append(f'<section id="{name}"><h2>{title}</h2><p>State dimension {len(labels)}; original horizon {horizon}, hold length {dt:g} {task["episode"]["time_unit"]}. Attempt <code>{row["attempt_id"]}</code>. All algorithm, postcheck and rendering statuses complete; both common and tight replays complete.</p><p><a href="{name}/raw.zip">Original raw attempt ZIP</a> · <a href="{name}/task.json">Complete mathematical task</a> · <a href="{name}/figure-data.json">All plotted numerical values and raw response hashes</a> · <a href="{name}/traces.png">State and control traces</a></p>{first_step}{"".join(figures)}</section>')
    page = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Native parallelotope finite-plan MPC: three saved functional episodes</title><link rel="stylesheet" href="../../examples/examples.css"><style>.page-content{max-width:1100px;margin:auto;padding:2rem}nav{display:flex;flex-wrap:wrap;gap:.7rem}h1{font-size:clamp(2rem,5vw,3.6rem)}img{max-width:100%;height:auto;max-height:none}code{overflow-wrap:anywhere}td,th{padding:.6rem}table{display:block;overflow-x:auto}@media(max-width:600px){.page-content{padding:1rem}h2{font-size:1.6rem}}</style></head><body><main class="page-content"><nav><a href="../index.html">Control functional evidence</a> · <a href="../../examples/index.html">Visual gallery</a></nav><h1>Native parallelotope finite-plan MPC</h1><p>Three source-qualified saved episodes: 90 accepted native queries, with 79 incomplete and 11 complete searches over the remaining finite action product. Each task keeps its original horizon, actions and objective. This is numerical functional evidence from one sequential attempt per task.</p>
<h2>What the controller computes</h2><p>At observed state x<sub>k</sub>, the affine predictor follows x<sub>j+1</sub> = A<sub>j</sub>x<sub>j</sub> + B<sub>j</sub>u<sub>j</sub> + c<sub>j</sub>. The native <code>parallelotope-plan-select</code> operation evaluates declared full-remaining-horizon action histories and selects the minimum recorded numerical terminal estimate plus running cost. Only the first action is held on the nonlinear plant; the next observation starts a new query. The existing candidate budget is at most 512 plans. Complete search coverage at a late short horizon does not imply global nonlinear feedback optimality.</p><p>Each linked task gives the full nonlinear model, units, original state/input bounds, action catalogue, predictor and source cost. Every raw request records the actual affine matrices, objective schedule and candidate histories. This planner is separate from the earlier continuous-action fixed-tail and F/B/I controllers.</p>
<h2>How to read the geometry</h2><p>Colored lines are selected affine plan paths, colored by observed query. Polygons project x = Qy for every state stage of every query, including initial and final stages. The saved lower/upper bounds constrain frame coordinates y. The raw bridge omitted Q; this derived figure recovers the fixed frame from the exact committed source, with its snapshot and hash retained. The source labels their role <code>fixed-plan-trajectory-enclosure</code>, representation parallelotope, relation outer and assurance numerical. For the two-state Lotka route Q is the identity. For the four-state orbit and fuel routes Q = [[1,1,0,0],[0,1,1,0],[0,0,1,1],[0,0,0,1]] and is fixed across all stages. We transform all 2ⁿ corners in full state space before taking their 2D convex hull. This reconstructs the source-defined fixed-plan parallelotopes from saved bounds; it does not construct F/B/I geometry or a nonlinear reachable tube. Singleton initial states and fixed controls make most polygons too narrow to see at this scale; their numerical widths remain in the figure data. The gold line is the actual nonlinear execution, which need not stay inside affine prediction bounds. A 2D projection of the orbit or fuel model still represents a four-state problem.</p>
<h2>Functional outcomes</h2><table><thead><tr><th>Task</th><th>Holds</th><th>Incomplete / complete queries</th><th>Nonlinear task objective</th><th>Max replay endpoint difference</th></tr></thead><tbody>''' + ''.join(table) + '''</tbody></table><p>Endpoint differences are maxima across coordinates with different task units; inspect per-coordinate values in <a href="manifest.json">the manifest</a>. Independent review reproduced all six common/tight replay requests with the qualified replay ELF, checked all 90 nested raw hashes, original task/action/horizon/graph identities, affine recurrences, candidate-list minima and source costs. Sampled state and control bound violations were zero. These are binary64 numerical and sampled diagnostics, with no validated enclosure, continuous safety, global optimality or performance conclusion.</p>''' + ''.join(sections) + '''<h2>Source and installed-component qualification</h2><p>Controller source <a href="https://github.com/butahlecoq/controlled-systems-lab/tree/''' + SOURCE + '''"><code>''' + SOURCE + '''</code></a>. Five components (model, polyhedral, nominal_forward, nominal_tube and finite_plan_parallelotope) were selectively rebuilt, then copied into an isolated installed prefix. The remaining imported closure reuses source-equivalent archives from SDK producer <code>3d7fff0c01ac346000ca6a97ad8d9fc654f38032</code>; header and object-input equality or recorded formatting-token parity qualify that reuse. This is an actual selected component overlay with fresh bridge/replay consumers, not a fresh whole SDK build. The 48-target / 47-archive imported closure, link maps, source inputs, compiler/binary/library hashes and runtime readback are retained below.</p><p>Runtime readback: Release, HiGHS and Qhull enabled, CasADi disabled. Availability flags do not establish that those optional solvers were invoked; these queries record the public native finite-plan operation. All BLAS/OpenMP threads were one; the supervised worker used a 300-second wall/CPU budget. That worker budget excludes replay, checks and rendering. Address-space limits are not physical RAM limits. Successful shared worker stderr was empty; these episodes do not themselves test failed-query stderr retention.</p><p><a href="qualification/frame-receipt.json">Derived fixed-frame receipt</a> · <a href="qualification/finite_plan_parallelotope.cpp">Exact source frame snapshot</a> · <a href="qualification/qualification-receipt.json">Qualification receipt and executable hashes</a> · <a href="qualification/source-inputs.json">Source equivalence inventory</a> · <a href="qualification/closure.json">Imported closure</a> · <a href="qualification/libraries.json">Library hashes</a> · <a href="qualification/runtime-profile-readback.json">Raw runtime readback, including the failed protocol probe</a> · <a href="qualification/history_policy.map">Actual policy link map</a> · <a href="qualification/nonlinear_replay.map">Actual replay link map</a></p>
<h2>Reproduce these figures without running a controller</h2><pre><code>python scripts/reports/native_parallelotope_functional.py --check
python scripts/reports/native_parallelotope_functional.py --render --output /tmp/native-parallelotope-figures</code></pre><p>The reader verifies the frozen member hashes and renders only saved data. Original attempt ZIPs preserve every original file, including the Orbit PNG whose title incorrectly said “backend not recorded”. The new figures above give the actual native operation a correct title without changing the old raw bytes. Prior captures and failed attempts remain retained separately. Data-only publication changes no public API, dependency, installation or native executable; no package release is needed. Review, exact-head CI, main-only Pages deployment and live URL/hash verification remain separate publication gates.</p><p><a href="manifest.json">Bundle manifest and member hashes</a> · <a href="files.sha256">Frozen file hashes</a> · <a href="render-source.py">Saved-data renderer source</a></p></main></body></html>'''
    (bundle / 'index.html').write_text(page)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, default=BUNDLE)
    parser.add_argument('--episodes', type=Path)
    parser.add_argument('--qualification', type=Path)
    parser.add_argument('--render', action='store_true')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.episodes:
        if not args.qualification:
            parser.error('--episodes requires --qualification')
        freeze(args.episodes, args.qualification, args.bundle)
    else:
        check(args.bundle)
        if args.render:
            if not args.output or args.output.exists():
                parser.error('--render requires a new --output directory')
            shutil.copytree(args.bundle, args.output)
            render(args.output)
    print('Verified saved native parallelotope functional bundle')


if __name__ == '__main__':
    main()
