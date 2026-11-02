import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import time

base = Path('/home/butahlecoq/.local/share/codex/captures/mpc01-resource-20261102')
source = Path('/home/butahlecoq/.local/share/codex/worktrees/mpc01-external-capture-20261102')
binary = Path('/home/butahlecoq/.local/share/codex/build/mpc01-external-capture-20261102/csl_mpc01_report')
records = base / 'comparison-records.jsonl'
command = [
    '/usr/bin/taskset', '-c', '0', str(binary),
    'examples/scenarios/double-integrator-generality.json',
    'docs/research/evidence/b04-reference-v1/canonical-case.json',
    '--repetitions', '5', '--records', str(records),
]
if records.exists():
    raise SystemExit(f'refusing existing output: {records}')

cgroup = None
for line in Path('/proc/self/cgroup').read_text().splitlines():
    hierarchy, controllers, path = line.split(':', 2)
    if hierarchy == '0' and not controllers:
        cgroup = Path('/sys/fs/cgroup') / path.lstrip('/')
        break
if cgroup is None:
    raise SystemExit('capture is not running in cgroup v2')
limit = int((cgroup / 'memory.max').read_text().strip())
swap_limit = int((cgroup / 'memory.swap.max').read_text().strip())
if limit != 8 * 1024**3 or swap_limit != 0:
    raise SystemExit(f'unexpected limits: memory.max={limit}, memory.swap.max={swap_limit}')
if not Path('/proc/self/status').read_text().split('Cpus_allowed_list:\t', 1)[1].splitlines()[0].startswith('0'):
    raise SystemExit('capture supervisor is not allowed on CPU 0')

started = time.monotonic_ns()
load_before = os.getloadavg()
process = subprocess.Popen(command, cwd=source, text=True, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, start_new_session=True)
status = 'failed'
try:
    stdout, stderr = process.communicate(timeout=300)
    status = 'completed' if process.returncode == 0 else 'failed'
except subprocess.TimeoutExpired:
    status = 'timed_out'
    os.killpg(process.pid, signal.SIGTERM)
    try:
        stdout, stderr = process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
elapsed = time.monotonic_ns() - started
(base / 'runner.stdout.jsonl').write_text(stdout, encoding='utf-8')
(base / 'runner.stderr.log').write_text(stderr, encoding='utf-8')
profile = {
    'schema': 'csl.mpc01-resource-profile/2',
    'profile': 'enforced-cgroup-v2-process-tree',
    'status': status,
    'command': command,
    'timeout_scope': 'entire seven-fixture capture invocation; solver attempts are sequential and each is retained in the native event stream',
    'elapsed_wall_time_ns': elapsed,
    'requested_limits': {'process_tree_wall_time_seconds': 300, 'process_tree_memory_bytes': 8 * 1024**3,
                         'maximum_concurrent_jobs': 1, 'solver_threads': 1},
    'enforced_limits': {'process_tree_wall_time': True, 'process_tree_memory': True,
                        'wall_mechanism': 'Python watchdog; SIGTERM then SIGKILL to supervised process group',
                        'memory_mechanism': 'systemd user scope on Linux cgroup v2, memory.max',
                        'memory_max_bytes': limit, 'memory_swap_max_bytes': swap_limit,
                        'cpu_affinity': 'CPU 0'},
    'observed': {'process_tree_peak_memory_bytes': int((cgroup / 'memory.peak').read_text().strip()),
                 'memory_events': (cgroup / 'memory.events').read_text().splitlines(),
                 'cpu_stat': (cgroup / 'cpu.stat').read_text().splitlines(),
                 'timed_out': status == 'timed_out', 'exit_code': process.returncode},
    'host': {'system': platform.system(), 'release': platform.release(), 'machine': platform.machine(),
             'logical_cpu_count': os.cpu_count(), 'load_average_before': load_before,
             'load_average_after': os.getloadavg()},
}
(base / 'resource-profile.json').write_text(json.dumps(profile, indent=2, sort_keys=True) + '\n', encoding='utf-8')
if status != 'completed':
    raise SystemExit(f'capture status: {status}, exit={process.returncode}')

attempt_rows = [json.loads(line) for line in stdout.splitlines() if line]
records_rows = [json.loads(line) for line in records.read_text(encoding='utf-8').splitlines() if line]
if len(attempt_rows) != 140 or len(records_rows) != 7 or any(len(row.get('attempts', [])) != 20 for row in records_rows):
    raise SystemExit(f'incomplete capture: stdout attempts={len(attempt_rows)}, records={len(records_rows)}')
(base / 'capture-summary.json').write_text(json.dumps({
    'status': status, 'attempt_rows': len(attempt_rows), 'case_records': len(records_rows),
    'attempts_per_case_record': [len(row['attempts']) for row in records_rows],
    'process_tree_peak_memory_bytes': profile['observed']['process_tree_peak_memory_bytes'],
    'elapsed_wall_time_ns': elapsed,
}, indent=2, sort_keys=True) + '\n', encoding='utf-8')
print(json.dumps({'status': status, 'attempt_rows': len(attempt_rows), 'case_records': len(records_rows),
                  'peak_bytes': profile['observed']['process_tree_peak_memory_bytes'],
                  'elapsed_ns': elapsed}, sort_keys=True))
