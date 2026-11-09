"""Render three saved controller variants after their independent saved checks."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/reports'))
from figure_style import configure_numeric_axis, STYLE_ID


def read(path):
    return json.loads(path.read_text())


def bind_pilot_archives(bundles):
    archives = {'affine': 'affine-pilot-b3978a98', 'nonlinear': 'nonlinear-pilot-0092081b',
                'nmpc': 'nmpc-pilot-55f65110'}
    bindings = {}
    for name, bundle in bundles.items():
        archive = Path(__file__).parent/'evidence'/archives[name]/'capture.zip'
        with zipfile.ZipFile(archive) as saved:
            members = [info for info in saved.infolist() if info.filename.startswith('accepted/') and not info.is_dir()]
            expected = {info.filename.removeprefix('accepted/'): saved.read(info) for info in members}
            if len(expected) != len(members):
                raise ValueError('duplicate archived input')
            actual = {path.relative_to(bundle).as_posix(): path.read_bytes()
                      for path in bundle.rglob('*') if path.is_file()}
            if actual != expected:
                raise ValueError(name+': input differs from immutable pilot archive')
        bindings[name] = {'archive': archive.relative_to(ROOT).as_posix(),
                          'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                          'capture_source': read(bundle/'manifest.json')['source_revision']}
    return bindings


def checked_inputs(affine, nonlinear, nmpc):
    receipts = {}
    for name, bundle in [('affine', affine), ('nonlinear', nonlinear), ('nmpc', nmpc)]:
        result = subprocess.run([sys.executable, str(Path(__file__).with_name(f'check_{name}_saved.py')),
                                 '--bundle', str(bundle)], capture_output=True, text=True, check=True)
        payload = result.stdout[result.stdout.index('['):]
        reports = json.loads(payload)
        expected = 'verified-numerical-witness' if name == 'affine' else 'complete'
        complete = (all(all(status == 'complete' for status in row['statuses'].values())
                        and all(status == 'completed' for status in row['process_statuses'].values()) for row in reports)
                    if name == 'nonlinear' else all(row['status'] == expected for row in reports))
        if not reports or not complete:
            raise ValueError(f'{name}: incomplete evidence cannot produce complete comparison')
        receipts[name] = reports
    return receipts


def render(affine: Path, nonlinear: Path, nmpc: Path, output: Path):
    if output.exists():
        raise ValueError('output must be a new directory')
    archives = bind_pilot_archives({'affine': affine, 'nonlinear': nonlinear, 'nmpc': nmpc})
    checks = checked_inputs(affine, nonlinear, nmpc)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np

    cases = []
    bindings = {}
    for slug in ('syn-nl-lv-01', 'syn-nl-fuel-01'):
        paths = {'scenario': nmpc/slug/'scenario.json', 'affine': affine/slug/'check.json',
                 'nonlinear': nonlinear/slug/'cvodes/record.json', 'nmpc': nmpc/slug/'attempt.json'}
        records = {key: read(path) for key, path in paths.items()}
        scenario = records['scenario']
        if scenario != read(nonlinear/slug/'source/scenario.json') or scenario != read(affine/slug/'scenario.json'):
            raise ValueError('different scenario definitions')
        a, nl, nm = (records[key] for key in ('affine', 'nonlinear', 'nmpc'))
        if a != read(nonlinear/slug/'affine-witness.json'):
            raise ValueError('affine plotted witness differs from independently rebuilt witness')
        variants = [dict(label='Affine prediction', times=scenario['time']['grid'],
                         states=a['affine_replay_states'], controls=a['physical_controls']),
                    dict(label='Affine controls on nonlinear plant', times=nl['times'],
                         states=nl['physical_states'], controls=a['physical_controls']),
                    dict(label='Shrinking-horizon NMPC execution', times=nm['times'],
                         states=nm['physical_states'], controls=nm['controls'])]
        for v in variants:
            if len(v['states']) != len(v['times']) or len(v['controls']) != scenario['time']['intervals']:
                raise ValueError('incomplete trajectory')
            if any(len(row) != len(scenario['states']) or any(not math.isfinite(x) for x in row) for row in v['states']):
                raise ValueError('invalid state array')
        for key, path in paths.items():
            bindings[f'{slug}/{key}'] = hashlib.sha256(path.read_bytes()).hexdigest()
        cases.append((slug, scenario, variants))
    output.mkdir(parents=True)
    colors = ['#0072B2', '#D55E00', '#009E73']
    styles = ['--', '-.', '-']
    for slug, s, variants in cases:
        names = [state['name'] for state in s['states']]
        pair_names = [('P', 'R')] if len(names) == 2 else [('m_ox', 'q_ox'), ('m_f', 'q_f')]
        pairs = [(names.index(x), names.index(y)) for x, y in pair_names]
        fig, axes = plt.subplots(1, len(pairs), figsize=(7*len(pairs), 5), squeeze=False)
        for ax, (i, j) in zip(axes[0], pairs):
            for v, color, style in zip(variants, colors, styles):
                points = np.asarray(v['states'])
                ax.plot(points[:, i], points[:, j], style, color=color, label=v['label'])
                ax.plot(points[0, i], points[0, j], 'o', color=color)
                ax.plot(points[-1, i], points[-1, j], 's', color=color)
                for fraction in (.25, .5, .75):
                    k = min(range(len(v['times'])), key=lambda k: abs(v['times'][k]-s['time']['final']*fraction))
                    ax.plot(points[k, i], points[k, j], '.', color=color)
                    ax.annotate(f"{v['times'][k]:.2g}", (points[k, i], points[k, j]), fontsize=7, color=color)
            target = s['objective']['terminal_target']
            ax.plot(target[i], target[j], '*', color='black', markersize=12, label='Terminal target')
            ax.set_xlabel(f"{s['states'][i]['name']} ({s['states'][i]['unit']})")
            ax.set_ylabel(f"{s['states'][j]['name']} ({s['states'][j]['unit']})")
            configure_numeric_axis(ax)
        axes[0, 0].legend(fontsize=8)
        fig.suptitle(f"{s['case_id']} — individual trajectories; time labels in {s['time']['unit']}\nCircle: initial; square: final. No reachable-set enclosure.", fontsize=10)
        fig.tight_layout()
        for ext in ('svg', 'png'):
            fig.savefig(output/f'{slug}-phase.{ext}', dpi=160, metadata={'Date': None} if ext == 'svg' else None)
        plt.close(fig)
        fig, axes = plt.subplots(len(s['states'])+len(s['controls']), 1, figsize=(10, 2.1*(len(s['states'])+len(s['controls']))), sharex=True, squeeze=False)
        for v, color, style in zip(variants, colors, styles):
            points = np.asarray(v['states'])
            for i, state in enumerate(s['states']):
                ax = axes[i, 0]
                ax.plot(v['times'], points[:, i], style, color=color, label=v['label'])
                ax.set_ylabel(f"{state['name']}\n{state['unit']}")
            controls = np.asarray(v['controls'])
            for i, control in enumerate(s['controls']):
                ax = axes[len(s['states'])+i, 0]
                ax.step(s['time']['grid'], np.r_[controls[:, i], controls[-1, i]], where='post', linestyle=style, color=color)
                ax.set_ylabel(f"{control['name']}\n{control['unit']}")
        for ax in axes[:, 0]:
            configure_numeric_axis(ax)
        axes[0, 0].legend(fontsize=8)
        axes[-1, 0].set_xlabel(f"Time ({s['time']['unit']})")
        fig.suptitle(s['case_id']+' — states and zero-order held controls')
        fig.tight_layout()
        for ext in ('svg', 'png'):
            fig.savefig(output/f'{slug}-traces.{ext}', dpi=160, metadata={'Date': None} if ext == 'svg' else None)
        plt.close(fig)
        (output/f'{slug}-plotted-data.json').write_text(json.dumps({'scenario': s, 'variants': variants}, indent=2)+'\n')
    snapshot = output/'source'
    snapshot.mkdir()
    for source in [*Path(__file__).parent.glob('*.py'), ROOT/'scripts/reports/figure_style.py']:
        (snapshot/source.name).write_bytes(source.read_bytes())
    receipt = {'input_archives': archives, 'schema': 'csl.mpc11.figure-receipt/1', 'style': STYLE_ID, 'matplotlib': matplotlib.__version__,
               'input_sha256': bindings, 'saved_checks': checks, 'claim': 'saved individual numerical trajectories only; no set or performance guarantee'}
    receipt['tool_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in [Path(__file__).resolve(), ROOT/'scripts/reports/figure_style.py',
                                       *[Path(__file__).with_name('check_'+name+'_saved.py') for name in ('affine', 'nonlinear', 'nmpc')]]}
    receipt['bundle_manifest_sha256'] = {name: hashlib.sha256((bundle/'manifest.json').read_bytes()).hexdigest()
                                        for name, bundle in [('affine', affine), ('nonlinear', nonlinear), ('nmpc', nmpc)]}
    receipt['helper_snapshot_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(snapshot.iterdir())}
    receipt['output_sha256'] = {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.rglob('*')) if p.is_file()}
    (output/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('affine', 'nonlinear', 'nmpc', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    render(args.affine.resolve(), args.nonlinear.resolve(), args.nmpc.resolve(), args.output.resolve())
