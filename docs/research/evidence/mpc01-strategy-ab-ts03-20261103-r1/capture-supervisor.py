#!/usr/bin/env python3
"""Run one paired Strategy A/B capture under an existing cgroup-v2 scope."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import platform
import signal
import subprocess
import time


def process_cgroup() -> pathlib.Path:
    for line in pathlib.Path('/proc/self/cgroup').read_text().splitlines():
        hierarchy, controllers, path = line.split(':', 2)
        if hierarchy == '0' and not controllers:
            result = pathlib.Path('/sys/fs/cgroup') / path.lstrip('/')
            if result.is_dir():
                return result
    raise RuntimeError('capture must run inside a cgroup-v2 systemd scope')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=pathlib.Path, required=True)
    parser.add_argument('--scenario', type=pathlib.Path, required=True)
    parser.add_argument('--events', type=pathlib.Path, required=True)
    parser.add_argument('--resource-profile', type=pathlib.Path, required=True)
    parser.add_argument('--workdir', type=pathlib.Path, required=True)
    parser.add_argument('--memory-bytes', type=int, default=2 * 1024**3)
    parser.add_argument('--timeout-seconds', type=int, default=300)
    args = parser.parse_args()
    executable = args.executable.resolve(strict=True)
    scenario = args.scenario.resolve(strict=True)
    workdir = args.workdir.resolve(strict=True)
    events = args.events.resolve()
    profile_path = args.resource_profile.resolve()
    stdout_path = events.with_name(events.stem + '-stdout.jsonl')
    stderr_path = events.with_name(events.stem + '-stderr.log')
    for output in (events, profile_path, stdout_path, stderr_path):
        if output.exists():
            raise SystemExit(f'refusing to overwrite existing output: {output}')
    events.parent.mkdir(parents=True, exist_ok=True)
    profile_path.parent.mkdir(parents=True, exist_ok=True)

    cgroup = process_cgroup()
    memory_limit = int((cgroup / 'memory.max').read_text().strip())
    swap_limit = int((cgroup / 'memory.swap.max').read_text().strip())
    if memory_limit != args.memory_bytes or swap_limit != 0:
        raise SystemExit(f'unexpected cgroup limits memory={memory_limit} swap={swap_limit}')

    command = [str(executable), '--measure-profile', 'ts03_singular_integrator',
               str(scenario), str(events)]
    start = time.monotonic_ns()
    load_before = os.getloadavg()
    process = subprocess.Popen(command, cwd=workdir, text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=args.timeout_seconds)
        status = 'completed' if process.returncode == 0 else 'failed'
    except subprocess.TimeoutExpired:
        status = 'timed_out'
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
    elapsed = time.monotonic_ns() - start
    stdout_path.write_text(stdout, encoding='utf-8')
    stderr_path.write_text(stderr, encoding='utf-8')
    profile = {
        'schema': 'csl.mpc01-resource-profile/1',
        'profile': 'local-host-constrained-process-tree',
        'status': status,
        'command': command,
        'timeout_scope': 'one complete strategy A/B capture process group; suite invocation, not individual attempts',
        'elapsed_wall_time_ns': elapsed,
        'requested_limits': {
            'process_tree_wall_time_seconds': args.timeout_seconds,
            'process_tree_memory_bytes': memory_limit,
            'maximum_concurrent_jobs': 1,
        },
        'enforced_limits': {
            'process_tree_wall_time': True,
            'process_tree_memory': True,
            'wall_mechanism': 'Python watchdog; SIGTERM then SIGKILL to supervised process group',
            'memory_mechanism': 'systemd user scope on Linux cgroup v2, memory.max',
            'memory_max_bytes': memory_limit,
            'memory_swap_max_bytes': swap_limit,
        },
        'observed': {
            'process_tree_peak_memory_bytes': int((cgroup / 'memory.peak').read_text().strip()),
            'memory_events': (cgroup / 'memory.events').read_text().splitlines(),
            'memory_current_bytes': int((cgroup / 'memory.current').read_text().strip()),
            'timed_out': status == 'timed_out',
            'exit_code': process.returncode,
        },
        'host': {
            'system': platform.system(), 'release': platform.release(),
            'machine': platform.machine(), 'logical_cpu_count': os.cpu_count(),
            'load_average_before': load_before, 'load_average_after': os.getloadavg(),
        },
    }
    profile_path.write_text(json.dumps(profile, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    if status != 'completed':
        raise SystemExit(f'algorithm process status: {status}, exit={process.returncode}')

    rows = [json.loads(line) for line in events.read_text(encoding='utf-8').splitlines() if line]
    trials = [row for row in rows if row.get('event') == 'trial']
    if (len(rows) != 13 or len(trials) != 12 or
            any(row.get('status') != 'passed' for row in trials) or
            rows[0].get('profile') != 'ts03_singular_integrator' or
            events.read_bytes() != stdout_path.read_bytes()):
        raise SystemExit(f'capture validation failed: events={len(rows)}, trials={len(trials)}')
    print(json.dumps({
        'status': status, 'events': str(events), 'trials': len(trials),
        'peak_bytes': profile['observed']['process_tree_peak_memory_bytes'],
        'elapsed_ns': elapsed,
    }, sort_keys=True))


if __name__ == '__main__':
    main()
