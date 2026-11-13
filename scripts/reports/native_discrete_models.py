"""Independently check and draw frozen native catalogue/MPC functional outputs."""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
from pathlib import Path

import figure_style
from plot import normalize_owned_svg
from report_data import require

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / 'reports/algorithm-results/native-discrete-models-v1'
SOURCE = '856d7a77c49fca0c6f6cdb8c1a1db9a651da85cb'
Q = [0, 0, 10, 10, 10, 10, 0, 0, 0, 5, 5, 5]
REFERENCE = [0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0]


def read_saved(root: Path):
    models = {}
    with (root / 'raw/models.csv').open(newline='') as stream:
        for row in csv.DictReader(stream):
            key = (row['kind'], int(row['row']), int(row['column']))
            model = models.setdefault(row['model'], {})
            require(key not in model, 'duplicate model coordinate')
            value = float(row['value'])
            require(math.isfinite(value), 'nonfinite model value')
            model[key] = value
    require(set(models) == {f'catalogue-2026/model-{i}/1' for i in range(1, 36)},
            'expected all 35 models')
    data = {}
    with (root / 'raw/plans.csv').open(newline='') as stream:
        for row in csv.DictReader(stream):
            key = (int(row['replan']), row['kind'], int(row['stage']), int(row['coordinate']))
            require(key not in data, 'duplicate plan coordinate')
            value = float(row['value'])
            require(math.isfinite(value), 'nonfinite plan value')
            data[key] = value
    layout = {'predicted_state': (11, 12), 'predicted_control': (10, 4),
              'observed_state': (1, 12), 'applied_control': (1, 4),
              'observed_next_state': (1, 12), 'independent_plan_cost': (1, 1),
              'program_plan_cost': (1, 1), 'realized_running_cost': (1, 1)}
    expected = {(r, kind, stage + (kind == 'observed_next_state'), c)
                for r in range(15) for kind, (count, dimension) in layout.items()
                for stage in range(count) for c in range(dimension)}
    require(set(data) == expected, 'incomplete or unexpected plan coordinates')
    def vector(r, kind, stage, size):
        return [data[r, kind, stage, i] for i in range(size)]
    plans = []
    for r in range(15):
        plans.append({'states': [vector(r, 'predicted_state', k, 12) for k in range(11)],
                      'controls': [vector(r, 'predicted_control', k, 4) for k in range(10)],
                      'observed': vector(r, 'observed_state', 0, 12),
                      'applied': vector(r, 'applied_control', 0, 4),
                      'next': vector(r, 'observed_next_state', 1, 12)})
    return models, data, plans


def check(root: Path) -> dict:
    models, data, plans = read_saved(root)
    model = models['catalogue-2026/model-21/1']
    def step(x, u):
        return [sum(model['A', i, j] * x[j] for j in range(12)) +
                sum(model['B', i, j] * u[j] for j in range(4)) for i in range(12)]
    errors = {'objective': 0.0, 'dynamics': 0.0, 'feedback': 0.0}
    previous = [0.0] * 12
    running = 0.0
    for r, plan in enumerate(plans):
        x, u = plan['states'], plan['controls']
        for left, right in ((previous, plan['observed']), (x[0], plan['observed']),
                            (u[0], plan['applied']), (step(plan['observed'], plan['applied']), plan['next'])):
            errors['feedback'] = max(errors['feedback'], *(abs(a-b) for a, b in zip(left, right, strict=True)))
        for k in range(10):
            errors['dynamics'] = max(errors['dynamics'], *(abs(a-b) for a, b in zip(step(x[k], u[k]), x[k+1], strict=True)))
        require(all(abs(s[0]) <= math.pi/6 + 2e-7 and abs(s[1]) <= math.pi/6 + 2e-7
                    and s[5] >= -1 - 2e-7 for s in x), 'state bound failed')
        require(all(-.9916 - 2e-7 <= v <= 2.4084 + 2e-7 for row in u for v in row), 'input bound failed')
        cost = sum(sum(q*(v-ref)**2 for q, v, ref in zip(Q, state, REFERENCE, strict=True)) for state in x)
        cost += .1 * sum(v*v for row in u for v in row)
        for kind in ('program_plan_cost', 'independent_plan_cost'):
            errors['objective'] = max(errors['objective'], abs(cost-data[r, kind, 0, 0]))
        stage_cost = sum(q*(v-ref)**2 for q, v, ref in zip(Q, plan['observed'], REFERENCE, strict=True)) + .1*sum(v*v for v in plan['applied'])
        running += stage_cost
        require(abs(stage_cost-data[r, 'realized_running_cost', 0, 0]) < 1e-5, 'realized cost failed')
        previous = plan['next']
    require(errors['objective'] < 1e-5 and errors['dynamics'] < 2e-6 and errors['feedback'] < 2e-7,
            'independent replay residual failed')
    return {'replans': 15, 'horizon': 10, 'state_dimension': 12, 'control_dimension': 4,
            'max_absolute_residual': errors, 'realized_running_cost_no_terminal': running,
            'scope': 'Numerical saved-data check; no stationarity, optimality, or safety certificate.'}


def draw(root: Path) -> dict[str, bytes]:
    check(root)
    _, _, plans = read_saved(root)
    import matplotlib
    require(matplotlib.__version__ == '3.11.2', 'Matplotlib 3.11.2 required')
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    executed = [p['observed'] for p in plans] + [plans[-1]['next']]
    assets = {}
    for theme in ('screen', 'print'):
        background, foreground = ('#272822', '#f8f8f2') if theme == 'screen' else ('white', '#172235')
        actual = '#a6e22e' if theme == 'screen' else '#166534'
        prediction = '#66d9ef' if theme == 'screen' else '#2563a6'
        with matplotlib.rc_context({'font.family': 'DejaVu Sans', 'font.size': 10,
                                    'svg.hashsalt': 'native-discrete-models-v1', 'svg.fonttype': 'none',
                                    'figure.facecolor': background, 'axes.facecolor': background,
                                    'text.color': foreground, 'axes.labelcolor': foreground,
                                    'axes.edgecolor': foreground, 'xtick.color': foreground, 'ytick.color': foreground}):
            figures = []
            for a, b in ((0, 1), (2, 5)):
                fig, ax = plt.subplots(figsize=(7.8, 5.3), layout='constrained')
                for r, plan in enumerate(plans):
                    ax.plot([x[a] for x in plan['states']], [x[b] for x in plan['states']],
                            color=prediction, alpha=.30, linewidth=1, marker='.', markersize=2,
                            label='15 predicted paths (11 states each)' if r == 0 else None)
                ax.plot([x[a] for x in executed], [x[b] for x in executed], color=actual,
                        linewidth=2, marker='o', markersize=3, label='Executed states 0–15')
                for state, marker, label, color in ((executed[0], 's', 'Initial', '#f92672'),
                                                     (executed[-1], 'D', 'Final executed', actual),
                                                     (REFERENCE, '*', 'Reference projection', '#fd971f')):
                    ax.scatter(state[a], state[b], marker=marker, s=95, color=color, label=label, zorder=5)
                ax.set(xlabel=f'x{a+1} (unit unspecified)', ylabel=f'x{b+1} (unit unspecified)',
                       title=f'Source21 MPC · indexed plane (x{a+1}, x{b+1})')
                if (a, b) == (0, 1):
                    ax.set_xlim(-math.pi/6, math.pi/6)
                    ax.set_ylim(-math.pi/6, math.pi/6)
                figure_style.configure_numeric_axis(ax)
                ax.legend(fontsize=8, facecolor=background, labelcolor=foreground)
                fig.supxlabel('Independent axis scales · numerical trajectories, no reachable sets', fontsize=9)
                figures.append((f'phase-x{a+1}-x{b+1}', fig))
            for kind, shape in (('states', (4, 3)), ('controls', (2, 2))):
                fig, axes = plt.subplots(*shape, figsize=(11, 10 if kind == 'states' else 6), layout='constrained')
                for c, ax in enumerate(axes.flat):
                    for r, plan in enumerate(plans):
                        values = [row[c] for row in plan[kind]]
                        stages = list(range(r, r+len(values)))
                        if kind == 'controls':
                            ax.step(stages+[stages[-1]+1], values+[values[-1]], where='post', color=prediction, alpha=.25)
                        else:
                            ax.plot(stages, values, color=prediction, alpha=.25, linewidth=1)
                    if kind == 'states':
                        ax.plot(range(16), [x[c] for x in executed], color=actual, marker='.', linewidth=2)
                        ax.axhline(REFERENCE[c], color='#fd971f', linestyle=':', linewidth=1)
                    else:
                        values = [p['applied'][c] for p in plans]
                        ax.step(range(16), values+[values[-1]], where='post', color=actual, linewidth=2)
                        ax.axhline(-.9916, color='#fd971f', linestyle=':', linewidth=1)
                        ax.axhline(2.4084, color='#fd971f', linestyle=':', linewidth=1)
                    ax.set(xlabel='Absolute stage (owner grid: 0.1 s)', ylabel=f'{"x" if kind == "states" else "u"}{c+1} (unit unspecified)')
                    figure_style.configure_numeric_axis(ax)
                    extent = max(abs(row[c]) for plan in plans for row in plan[kind])
                    if 0 < extent < 1e-6:
                        from matplotlib.ticker import FuncFormatter
                        exponent = math.floor(math.log10(extent))
                        scale = 10.0 ** exponent
                        ax.yaxis.set_major_formatter(FuncFormatter(
                            lambda value, _position, axis=ax, factor=scale:
                            figure_style.format_tick(value/factor,
                                [v/factor for v in axis.yaxis.get_majorticklocs()])))
                        ax.set_title(f'Y ticks × 10^{exponent}', loc='left', fontsize=9)
                fig.suptitle('All 15 predictions (blue) and executed values (green) · '+kind)
                fig.supxlabel('Dotted: reference states / input bounds · predictions extend beyond executed stage 15', fontsize=9)
                figures.append((kind, fig))
            for name, fig in figures:
                try:
                    out = io.StringIO()
                    fig.savefig(out, format='svg', metadata={'Date': None, 'Format': None, 'Type': None, 'Creator': None})
                    assets[f'{name}-{theme}.svg'] = normalize_owned_svg(out.getvalue())
                    raster = io.BytesIO()
                    fig.savefig(raster, format='png', dpi=150, metadata={'Software': 'CSL saved-data example'})
                    assets[f'{name}-{theme}.png'] = raster.getvalue()
                finally:
                    plt.close(fig)
    return assets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='verify saved figures byte-for-byte')
    args = parser.parse_args()
    if args.check:
        from stage_native_discrete_models import build
        build(ROOT)
    result = check(BUNDLE)
    assets = draw(BUNDLE)
    assets['check.json'] = (json.dumps(result, indent=2) + '\n').encode()
    for name, content in assets.items():
        target = BUNDLE / name
        if args.check:
            require(target.read_bytes() == content, 'saved rendering differs: ' + name)
        else:
            target.write_bytes(content)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
