#!/usr/bin/env python3
"""Package completed history-MPC records without changing their raw bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[2]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def package(attempt: Path, output_root: Path, name: str, audit: Path, build: Path,
            sdk: Path, auditor: Path, producer_commit: str) -> Path:
    if attempt.is_symlink() or output_root.is_symlink():
        raise ValueError("source and output directories may not be symlinks")
    attempt, output_root = attempt.resolve(strict=True), output_root.resolve(strict=True)
    if not attempt.is_dir() or not output_root.is_dir():
        raise ValueError("attempt and output root must be directories")
    if not name or name in {".", ".."} or Path(name).name != name:
        raise ValueError("bundle name must be a single path component")
    dest = output_root / name
    if dest.exists() or dest.is_symlink() or attempt == output_root or attempt.is_relative_to(output_root) or output_root.is_relative_to(attempt):
        raise ValueError("bundle destination must be new and separate from the source attempt")
    for path in attempt.rglob('*'):
        if path.is_symlink():
            raise ValueError("source attempt may not contain symlinks")
        if not path.is_file() and not path.is_dir():
            raise ValueError("source attempt contains a non-regular member")
    if any(path.is_symlink() or not path.is_file() for path in (audit, build, sdk, auditor)):
        raise ValueError("audit and provenance inputs must be regular files")
    episode = json.loads((attempt / 'attempt.json').read_bytes())
    run = json.loads((attempt / 'run-manifest.json').read_bytes())
    graph = json.loads((attempt / 'resolved-graph.json').read_bytes())
    audit_bytes, build_bytes, sdk_bytes, auditor_bytes = (p.read_bytes() for p in (audit, build, sdk, auditor))
    verified, provenance, sdk_manifest = map(json.loads, (audit_bytes, build_bytes, sdk_bytes))
    case = episode['task_id'].split('/')[0]
    case_key = 'earth-orbit' if case.startswith('env717-earth-orbit') else case
    check = verified['tasks'][case_key]
    if (episode.get('status') != 'complete' or episode.get('overall_status') != 'complete'
            or any(episode.get(key) != 'complete' for key in ('algorithm_status', 'postcheck_status', 'render_status'))
            or episode['completed_holds'] != episode['original_intervals']
            or any(episode['independent_replay'][kind]['status'] != 'complete' for kind in ('common', 'tight'))
            or check.get('audit_status') != 'pass' or check.get('errors')
            or check['completed_holds'] != episode['completed_holds'] or check['expected_holds'] != episode['original_intervals']):
        raise ValueError('only fully complete, independently audited episodes may be packaged')
    native_hash = episode['preparation_receipt']['adapter_receipt']['executable_sha256']
    physical_hash = run['bridge_sha256']
    if (run['source_commit'] != provenance['source_commit'] or verified['source_commit'] != run['source_commit']
            or episode['task_sha256'] != run['task_sha256'] or check['task_sha256'] != run['task_sha256']
            or episode['task_id'] != graph['task_id'] or episode['controller_id'] != graph['controller']['id']
            or run['graph_id'] != graph['graph_id'] or run['graph_fingerprint'] != graph['graph_fingerprint']
            or episode['action_profile_id'] != graph['action_profile_id']
            or episode['objective_id'] != graph['objective_id']
            or provenance['artifacts']['native_policy']['sha256'] != native_hash
            or provenance['artifacts']['physical_bridge']['sha256'] != physical_hash
            or sdk_manifest['sdk_source_commit'] != provenance.get('sdk_source_commit', provenance['source_commit'])
            or any(not math.isclose(episode['physical_objective'][key], check['applied_original_objective'][key],
                                    rel_tol=1e-12, abs_tol=1e-12) for key in ('terminal', 'running', 'total'))):
        raise ValueError('source, task, cost, action, SDK or binary evidence does not match')
    files = sorted(path for path in attempt.rglob('*') if path.is_file())
    stage = Path(tempfile.mkdtemp(prefix=f'.{name}.stage-', dir=output_root))
    archive_path = stage / 'raw.zip'
    inventory = {}
    with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            relative = path.relative_to(attempt).as_posix()
            before = path.stat()
            data = path.read_bytes()
            if re.search(rb'(ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-proj-[A-Za-z0-9_-]{20,}|BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY)', data):
                raise ValueError(f'possible credential in source member: {relative}')
            after = path.stat()
            if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
                raise ValueError(f'source changed during archive: {relative}')
            info = zipfile.ZipInfo(relative, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
            inventory[relative] = {'bytes': len(data), 'sha256': digest(data), 'crc32': f'{zlib.crc32(data):08x}'}
    with zipfile.ZipFile(archive_path) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(inventory):
            raise ValueError('archive CRC or member inventory mismatch')
        for member, expected in inventory.items():
            data = archive.read(member)
            source = attempt / member
            if (source.is_symlink() or len(data) != expected['bytes'] or digest(data) != expected['sha256']
                    or f'{archive.getinfo(member).CRC:08x}' != expected['crc32']
                    or digest(source.read_bytes()) != expected['sha256']):
                raise ValueError(f'archive or source verification failed: {member}')
    for filename, data in [('build-receipt.json', build_bytes), ('sdk-manifest.json', sdk_bytes), ('audit.py', auditor_bytes)]:
        (stage / filename).write_bytes(data)
    for filename in ('trajectory.png', 'controls.png', 'phase.png'):
        (stage / filename).write_bytes((attempt / filename).read_bytes())
    receipt = {'schema': 'csl.closed-loop.history-functional-bundle/1', 'producer_commit': producer_commit,
        'producer_script': 'scripts/reports/package_history_functional.py', 'source_commit': run['source_commit'],
        'source_capsule_sha256': provenance['artifacts']['source_capsule']['sha256'],
        'sdk_source_commit': sdk_manifest['sdk_source_commit'], 'sdk_manifest_sha256': digest(sdk_bytes),
        'native_binary_sha256': native_hash, 'physical_binary_sha256': physical_hash,
        'binary_source_recorded_by_attempt': episode['preparation_receipt']['adapter_receipt'].get('binary_source', 'unknown'),
        'task_id': episode['task_id'], 'task_sha256': episode['task_sha256'], 'task_source_sha256': episode['source_sha256'],
        'objective_id': episode['objective_id'], 'action_profile_id': episode['action_profile_id'],
        'controller_id': episode['controller_id'], 'graph_id': graph['graph_id'], 'graph_fingerprint': graph['graph_fingerprint'],
        'capability_manifest_sha256': run['capability_manifest_sha256'], 'original_intervals': episode['original_intervals'],
        'completed_holds': episode['completed_holds'], 'physical_objective': episode['physical_objective'],
        'independent_replay': episode['independent_replay'], 'independent_audit': check,
        'audit_source_sha256': digest(auditor_bytes), 'raw_zip_sha256': digest(archive_path.read_bytes()),
        'archive_format': 'ZIP deflate level 9; sorted members; fixed 1980 timestamp; original uncompressed bytes',
        'archive_members': inventory, 'scope': 'functional numerical evidence; no benchmark, global optimum or validated safety claim'}
    (stage / 'receipt.json').write_text(json.dumps(receipt, sort_keys=True, indent=2) + '\n')
    outputs = sorted(p for p in stage.iterdir() if p.is_file())
    (stage / 'SHA256SUMS').write_text(''.join(f'{digest(p.read_bytes())}  {p.name}\n' for p in outputs))
    if dest.exists() or dest.is_symlink():
        raise ValueError('bundle destination appeared during staging')
    os.rename(stage, dest)
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('attempt', 'output-root', 'audit', 'build', 'sdk', 'auditor'):
        parser.add_argument('--' + arg, type=Path, required=True)
    parser.add_argument('--name', required=True)
    args = parser.parse_args()
    if args.output_root.is_symlink():
        raise ValueError("output root may not be a symlink")
    output_root = args.output_root.resolve(strict=True)
    allowed = (ROOT / 'reports/closed-loop-history-functional').resolve()
    if output_root != allowed or not output_root.is_relative_to(ROOT.resolve()):
        raise ValueError('output root must be the repository history functional reports directory')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    committed = subprocess.check_output(['git', 'show', f'{commit}:scripts/reports/package_history_functional.py'], cwd=ROOT)
    if committed != Path(__file__).read_bytes():
        raise ValueError('bundle producer must match the committed source')
    path = package(args.attempt, output_root, args.name, args.audit, args.build, args.sdk, args.auditor, commit)
    print(json.dumps({'status': 'complete', 'bundle': str(path), 'producer_commit': commit}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
