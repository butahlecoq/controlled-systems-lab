#!/usr/bin/env python3
"""Render correctly labeled views from a completed saved history episode."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'benchmarks/reporting/closed_loop'))
from contracts import load_task, manifest_sha256
from run_closed_loop import render_attempt


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def render(attempt: Path, output: Path, producer_commit: str) -> Path:
    if attempt.is_symlink() or output.is_symlink():
        raise ValueError('attempt and output may not be symlinks')
    attempt = attempt.resolve(strict=True)
    output = output.parent.resolve(strict=True) / output.name
    if output.exists() or output.is_relative_to(attempt) or attempt.is_relative_to(output):
        raise ValueError('render output must be new and separate from the source attempt')
    raw = (attempt / 'attempt.json').read_bytes()
    episode = json.loads(raw)
    if episode.get('overall_status') != 'complete' or episode.get('completed_holds') != episode.get('original_intervals'):
        raise ValueError('only a complete episode may be rendered')
    case = episode['task_id'].split('/')[0]
    task_name = 'earth-orbit' if case.startswith('env717-earth-orbit') else case
    task = load_task(task_name)
    if (manifest_sha256(task) != episode['task_sha256']
            or task['episode']['intervals'] != episode['original_intervals']
            or len(episode['physical_states']) != episode['original_intervals'] + 1
            or len(episode['controls']) != episode['original_intervals']):
        raise ValueError('saved episode differs from the source task')
    if (episode.get('resolved_graph', {}).get('controller', {}).get('adapter') != 'continuous_history'
            or episode['resolved_graph']['controller']['id'] != episode['controller_id']):
        raise ValueError('expected a continuous affine-history controller')
    stage_paths = sorted(attempt.glob('stage-[0-9][0-9][0-9].json'))
    if len(stage_paths) != episode['original_intervals']:
        raise ValueError('saved stage inventory differs from the original horizon')
    stages = []
    providers = set()
    for index, path in enumerate(stage_paths):
        if path.is_symlink():
            raise ValueError('stage source may not be a symlink')
        data = path.read_bytes()
        stage = json.loads(data)
        if (stage.get('update_index') != index or stage.get('status') != 'applied-and-observed'
                or stage.get('original_task_sha256') != episode['task_sha256']):
            raise ValueError('stage order or status is invalid')
        providers.update(call['provider'] for call in stage.get('controller_invocations', [])
                         if call.get('operation') == 'controller.solve' and call.get('provider'))
        stages.append({'path': path.name, 'sha256': digest(data)})
    if len(providers) != 1 or next(iter(providers)) not in {'csl.convex.highs', 'casadi-ipopt'}:
        raise ValueError('saved stages do not identify one supported actual solver')
    output.mkdir(parents=False, exist_ok=False)
    (output / 'stage-000.json').write_bytes(stage_paths[0].read_bytes())
    result = copy.deepcopy(episode)
    render_attempt(task, result, output)
    plots = {name: digest((output / name).read_bytes()) for name in ('trajectory.png', 'controls.png', 'phase.png')}
    receipt = {'schema': 'csl.closed-loop.history-corrected-render/1', 'producer_commit': producer_commit,
        'renderer_source_sha256': digest((ROOT / 'benchmarks/reporting/closed_loop/run_closed_loop.py').read_bytes()),
        'generator_source_sha256': digest(Path(__file__).read_bytes()), 'task_sha256': episode['task_sha256'],
        'attempt_sha256': digest(raw), 'controller_id': episode['controller_id'],
        'actual_provider': next(iter(providers)), 'stage_sources': stages, 'plots': plots,
        'correction': 'The original trajectory PNG title and generic geometry/coverage text said NMPC; the saved controller is affine-history MPC. Original files remain unchanged in the raw archive.'}
    (output / 'render-receipt.json').write_text(json.dumps(receipt, sort_keys=True, indent=2) + '\n')
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    for filename in ('scripts/reports/render_history_functional.py', 'benchmarks/reporting/closed_loop/run_closed_loop.py'):
        if subprocess.check_output(['git', 'show', f'{commit}:{filename}'], cwd=ROOT) != (ROOT / filename).read_bytes():
            raise ValueError('render generator and renderer must match the committed source')
    print(json.dumps({'status': 'complete', 'output': str(render(args.attempt, args.output, commit))}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
