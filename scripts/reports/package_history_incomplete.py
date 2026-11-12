#!/usr/bin/env python3
"""Preserve a timed-out history query without inferring a solver outcome."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

from package_history_functional import ROOT, archive_attempt, digest


def package(attempt: Path, output_root: Path, name: str, audit: Path, build: Path,
            sdk: Path, auditor: Path, producer_commit: str) -> Path:
    if attempt.is_symlink() or output_root.is_symlink():
        raise ValueError('source and output directories may not be symlinks')
    attempt, output_root = attempt.resolve(strict=True), output_root.resolve(strict=True)
    if not attempt.is_dir() or not output_root.is_dir() or not name or name in {'.', '..'} or Path(name).name != name:
        raise ValueError('invalid source or bundle destination')
    dest = output_root / name
    if dest.exists() or dest.is_symlink() or attempt == output_root or attempt.is_relative_to(output_root) or output_root.is_relative_to(attempt):
        raise ValueError('bundle destination must be new and separate from the source attempt')
    for path in attempt.rglob('*'):
        if path.is_symlink() or (not path.is_file() and not path.is_dir()):
            raise ValueError('source attempt contains a symlink or non-regular member')
    if any(path.is_symlink() or not path.is_file() for path in (audit, build, sdk, auditor)):
        raise ValueError('audit and provenance inputs must be regular files')
    episode = json.loads((attempt / 'attempt.json').read_bytes())
    run = json.loads((attempt / 'run-manifest.json').read_bytes())
    graph = json.loads((attempt / 'resolved-graph.json').read_bytes())
    audit_bytes, build_bytes, sdk_bytes, auditor_bytes = (p.read_bytes() for p in (audit, build, sdk, auditor))
    verified, provenance, sdk_manifest = map(json.loads, (audit_bytes, build_bytes, sdk_bytes))
    case = episode['task_id'].split('/')[0]
    check = verified['tasks'][case]
    completed, original = episode['completed_holds'], episode['original_intervals']
    if (episode.get('status') != 'incomplete' or episode.get('overall_status') != 'incomplete'
            or episode.get('algorithm_status') != 'incomplete' or episode.get('postcheck_status') != 'not_run'
            or episode.get('render_status') != 'not_run' or episode.get('physical_objective') is not None
            or episode.get('supervisor', {}).get('status') != 'timed_out' or not 0 <= completed < original
            or len(episode['controls']) != completed or len(episode['physical_states']) != completed + 1
            or check.get('audit_status') != 'incomplete-or-failed' or check.get('errors')
            or check['completed_holds'] != completed or check['expected_holds'] != original):
        raise ValueError('expected a terminal incomplete timeout with an audited partial episode')
    native_hash = episode['preparation_receipt']['adapter_receipt']['executable_sha256']
    physical_hash = run['bridge_sha256']
    if (run['source_commit'] != provenance['source_commit'] or verified['source_commit'] != run['source_commit']
            or episode['task_sha256'] != run['task_sha256'] or check['task_sha256'] != run['task_sha256']
            or episode['task_id'] != graph['task_id'] or episode['controller_id'] != graph['controller']['id']
            or run['graph_id'] != graph['graph_id'] or run['graph_fingerprint'] != graph['graph_fingerprint']
            or episode['action_profile_id'] != graph['action_profile_id'] or episode['objective_id'] != graph['objective_id']
            or provenance['artifacts']['native_policy']['sha256'] != native_hash
            or provenance['artifacts']['physical_bridge']['sha256'] != physical_hash
            or sdk_manifest['sdk_source_commit'] != provenance.get('sdk_source_commit', provenance['source_commit'])):
        raise ValueError('source, task, cost, action, SDK or binary evidence does not match')
    stage_path = attempt / f'stage-{completed:03d}.json'
    stage = json.loads(stage_path.read_bytes())
    ref = stage['native_query_capture']
    capture_path = attempt / ref['path']
    if Path(ref['path']).name != ref['path'] or capture_path.is_symlink():
        raise ValueError('invalid native capture path')
    capture_bytes = capture_path.read_bytes()
    if digest(capture_bytes) != ref['sha256']:
        raise ValueError('native capture metadata hash differs')
    capture = json.loads(capture_bytes)
    request_path = attempt / capture['request']['path']
    if Path(capture['request']['path']).name != capture['request']['path'] or request_path.is_symlink():
        raise ValueError('invalid native request path')
    request_bytes = request_path.read_bytes()
    request = json.loads(request_bytes)
    if (stage['update_index'] != completed or stage['status'] != 'started'
            or capture['update_index'] != completed or not capture['bridge_request_sent']
            or capture['response_parse_status'] != 'not_received' or capture['response'] is not None
            or digest(request_bytes) != capture['request']['sha256'] or digest(request_bytes) != capture['request_sha256']
            or request['absolute_update_index'] != completed or request['original_horizon'] != original
            or len(request['predictor_stages']) != original - completed
            or request['task_sha256'] != episode['task_sha256'] or request['action_profile_id'] != episode['action_profile_id']
            or request['controller_id'] != episode['controller_id']
            or request['observed_physical_state'] != episode['physical_states'][-1]):
        raise ValueError('timeout query capture does not match the remaining source problem')
    stage_dir = Path(tempfile.mkdtemp(prefix=f'.{name}.stage-', dir=output_root))
    archive = stage_dir / 'raw.zip'
    inventory = archive_attempt(attempt, archive)
    for filename, data in [('build-receipt.json', build_bytes), ('sdk-manifest.json', sdk_bytes), ('audit.py', auditor_bytes)]:
        (stage_dir / filename).write_bytes(data)
    receipt = {'schema': 'csl.closed-loop.history-incomplete-bundle/1', 'producer_commit': producer_commit,
        'producer_script': 'scripts/reports/package_history_incomplete.py', 'source_commit': run['source_commit'],
        'source_capsule_sha256': provenance['artifacts']['source_capsule']['sha256'],
        'sdk_source_commit': sdk_manifest['sdk_source_commit'], 'sdk_manifest_sha256': digest(sdk_bytes),
        'native_binary_sha256': native_hash, 'physical_binary_sha256': physical_hash,
        'binary_source_recorded_by_attempt': episode['preparation_receipt']['adapter_receipt'].get('binary_source', 'unknown'),
        'task_id': episode['task_id'], 'task_sha256': episode['task_sha256'], 'task_source_sha256': episode['source_sha256'],
        'objective_id': episode['objective_id'], 'action_profile_id': episode['action_profile_id'],
        'controller_id': episode['controller_id'], 'graph_id': graph['graph_id'], 'graph_fingerprint': graph['graph_fingerprint'],
        'capability_manifest_sha256': run['capability_manifest_sha256'], 'original_intervals': original,
        'completed_holds': completed, 'observed_states': episode['physical_states'], 'applied_controls': episode['controls'],
        'supervisor_status': 'timed_out', 'resource_limits': episode['supervisor'], 'unfinished_stage': completed,
        'remaining_horizon': original - completed, 'request_sha256': digest(request_bytes),
        'solver_outcome': 'not returned', 'postcheck_status': 'not_run', 'independent_audit': check,
        'audit_source_sha256': digest(auditor_bytes), 'raw_zip_sha256': digest(archive.read_bytes()),
        'archive_format': 'ZIP deflate level 9; sorted members; fixed 1980 timestamp; original uncompressed bytes',
        'archive_members': inventory, 'scope': 'incomplete numerical attempt; timeout does not establish incompatibility or infeasibility'}
    (stage_dir / 'receipt.json').write_text(json.dumps(receipt, sort_keys=True, indent=2) + '\n')
    outputs = sorted(path for path in stage_dir.iterdir() if path.is_file())
    (stage_dir / 'SHA256SUMS').write_text(''.join(f'{digest(path.read_bytes())}  {path.name}\n' for path in outputs))
    if dest.exists() or dest.is_symlink():
        raise ValueError('bundle destination appeared during staging')
    os.rename(stage_dir, dest)
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('attempt', 'output-root', 'audit', 'build', 'sdk', 'auditor'):
        parser.add_argument('--' + arg, type=Path, required=True)
    parser.add_argument('--name', required=True)
    args = parser.parse_args()
    if args.output_root.is_symlink():
        raise ValueError('output root may not be a symlink')
    output = args.output_root.resolve(strict=True)
    if output != (ROOT / 'reports/closed-loop-history-functional').resolve() or not output.is_relative_to(ROOT.resolve()):
        raise ValueError('output root must be the repository history functional reports directory')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    for source in ('scripts/reports/package_history_incomplete.py', 'scripts/reports/package_history_functional.py'):
        if subprocess.check_output(['git', 'show', f'{commit}:{source}'], cwd=ROOT) != (ROOT / source).read_bytes():
            raise ValueError('bundle producer must match committed source')
    path = package(args.attempt, output, args.name, args.audit, args.build, args.sdk, args.auditor, commit)
    print(json.dumps({'status': 'complete', 'bundle': str(path), 'producer_commit': commit}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
