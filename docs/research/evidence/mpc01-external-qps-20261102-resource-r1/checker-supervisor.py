import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

base = Path('/home/butahlecoq/.local/share/codex/captures/mpc01-resource-20261102')
source = Path('/home/butahlecoq/.local/share/codex/worktrees/mpc01-external-capture-20261102')
checker = source / 'scripts/reports/mpc01/verify_saved_exact_optimality.py'
command = [sys.executable, str(checker),
           '--attempts', str(base / 'runner.stdout.jsonl'),
           '--records', str(base / 'comparison-records.jsonl'),
           '--double-integrator', str(source / 'examples/scenarios/double-integrator-generality.json'),
           '--b04-case', str(source / 'docs/research/evidence/b04-reference-v1/canonical-case.json'),
           '--b04-reference', str(source / 'docs/research/evidence/b04-reference-v1/exact-optimal-reference.json'),
           '--output', str(base / 'exact-candidate-checks.jsonl')]
for name in ('exact-candidate-checks.jsonl', 'exact-check-manifest.json'):
    if (base / name).exists():
        raise SystemExit(f'refusing existing output: {base / name}')
cgroup = None
for line in Path('/proc/self/cgroup').read_text().splitlines():
    hierarchy, controllers, path = line.split(':', 2)
    if hierarchy == '0' and not controllers:
        cgroup = Path('/sys/fs/cgroup') / path.lstrip('/')
        break
if cgroup is None:
    raise SystemExit('checker is not running in cgroup v2')
limit = int((cgroup / 'memory.max').read_text().strip())
swap_limit = int((cgroup / 'memory.swap.max').read_text().strip())
if limit != 8 * 1024**3 or swap_limit != 0:
    raise SystemExit(f'unexpected checker limits: memory.max={limit}, swap.max={swap_limit}')
started = time.monotonic_ns()
process = subprocess.Popen(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           start_new_session=True)
status = 'failed'
try:
    stdout, stderr = process.communicate(timeout=5)
    status = 'completed' if process.returncode == 0 else 'failed'
except subprocess.TimeoutExpired:
    status = 'timed_out'
    os.killpg(process.pid, signal.SIGTERM)
    try:
        stdout, stderr = process.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
elapsed = time.monotonic_ns() - started
(base / 'exact-checker.stdout.log').write_text(stdout, encoding='utf-8')
(base / 'exact-checker.stderr.log').write_text(stderr, encoding='utf-8')
checks = [json.loads(line) for line in (base / 'exact-candidate-checks.jsonl').read_text().splitlines() if line] if status == 'completed' else []
profile = {
    'schema': 'csl.mpc01-checker-resource-profile/1', 'status': status,
    'timeout_seconds': 5, 'memory_max_bytes': limit, 'memory_swap_max_bytes': swap_limit,
    'wall_mechanism': 'Python watchdog; SIGTERM then SIGKILL to checker process group',
    'memory_mechanism': 'systemd user scope on Linux cgroup v2, memory.max',
    'elapsed_wall_time_ns': elapsed,
    'peak_process_tree_memory_bytes': int((cgroup / 'memory.peak').read_text().strip()),
    'memory_events': (cgroup / 'memory.events').read_text().splitlines(),
    'exit_code': process.returncode, 'command': command,
    'verified_candidates': len(checks),
}
(base / 'exact-checker-resource-profile.json').write_text(json.dumps(profile, indent=2, sort_keys=True) + '\n')
if status != 'completed' or len(checks) != 90:
    raise SystemExit(f'exact checker result invalid: status={status}, candidates={len(checks)}')
print(json.dumps({'status': status, 'verified_candidates': len(checks), 'elapsed_ns': elapsed,
                  'peak_bytes': profile['peak_process_tree_memory_bytes']}, sort_keys=True))
