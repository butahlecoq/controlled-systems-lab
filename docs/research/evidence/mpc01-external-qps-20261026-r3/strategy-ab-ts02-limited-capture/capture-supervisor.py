import json, os, pathlib, platform, signal, subprocess, time
base = pathlib.Path('/var/tmp/csl-mpc01-limited-ts02-20261102')
events = base / 'strategy-ab-ts02-limited-events.jsonl'
if events.exists():
    raise SystemExit(f'refusing existing output: {events}')
cgroup = None
for line in pathlib.Path('/proc/self/cgroup').read_text().splitlines():
    hierarchy, controllers, path = line.split(':', 2)
    if hierarchy == '0' and not controllers:
        cgroup = pathlib.Path('/sys/fs/cgroup') / path.lstrip('/')
        break
if cgroup is None:
    raise SystemExit('not running in cgroup v2')
limit = int((cgroup / 'memory.max').read_text().strip())
swap_limit = int((cgroup / 'memory.swap.max').read_text().strip())
if limit != 2 * 1024**3 or swap_limit != 0:
    raise SystemExit(f'unexpected cgroup limits memory={limit} swap={swap_limit}')
command = ['/home/butahlecoq/.local/share/codex/worktrees/mpc06-tube-mpc-602-20261028/build/dev/installed-consumer/examples-build/registered_synthesis_comparison', '--measure-profile', 'ts02_constant_integrator', '/home/butahlecoq/.local/share/codex/worktrees/mpc01-canonical-pair-20261102/docs/research/evidence/mpc01-external-qps-20261026-r3/strategy-ab-ts02-limited-capture/scenario.json', str(events)]
started = time.monotonic_ns()
load_before = os.getloadavg()
status, exit_code = 'failed', None
stdout = stderr = ''
process = subprocess.Popen(command, cwd='/home/butahlecoq/.local/share/codex/worktrees/mpc06-tube-mpc-602-20261028', text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
try:
    stdout, stderr = process.communicate(timeout=300)
    exit_code = process.returncode
    status = 'completed' if exit_code == 0 else 'failed'
except subprocess.TimeoutExpired:
    status = 'timed_out'
    os.killpg(process.pid, signal.SIGTERM)
    try:
        stdout, stderr = process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
    exit_code = process.returncode
elapsed = time.monotonic_ns() - started
(base / 'stdout.log').write_text(stdout, encoding='utf-8')
(base / 'stderr.log').write_text(stderr, encoding='utf-8')
profile = {
    'schema': 'csl.mpc01-resource-profile/1',
    'profile': 'local-host-constrained-process-tree',
    'status': status,
    'command': command,
    'timeout_scope': 'one complete strategy A/B capture process group; applies to the suite invocation, not individually restarted trials',
    'elapsed_wall_time_ns': elapsed,
    'requested_limits': {'process_tree_wall_time_seconds': 300, 'process_tree_memory_bytes': limit, 'maximum_concurrent_jobs': 1},
    'enforced_limits': {'process_tree_wall_time': True, 'process_tree_memory': True, 'wall_mechanism': 'Python watchdog; SIGTERM then SIGKILL to supervised process group', 'memory_mechanism': 'systemd user scope on Linux cgroup v2, memory.max', 'memory_max_bytes': limit, 'memory_swap_max_bytes': swap_limit},
    'observed': {'process_tree_peak_memory_bytes': int((cgroup / 'memory.peak').read_text().strip()), 'memory_events': (cgroup / 'memory.events').read_text().splitlines(), 'memory_current_bytes': int((cgroup / 'memory.current').read_text().strip()), 'timed_out': status == 'timed_out', 'exit_code': exit_code},
    'host': {'system': platform.system(), 'release': platform.release(), 'machine': platform.machine(), 'logical_cpu_count': os.cpu_count(), 'load_average_before': load_before, 'load_average_after': os.getloadavg()},
}
(base / 'resource-profile.json').write_text(json.dumps(profile, indent=2, sort_keys=True) + '\n', encoding='utf-8')
if status != 'completed':
    raise SystemExit(f'capture status: {status}, exit={exit_code}')
rows = [json.loads(line) for line in events.read_text().splitlines() if line]
trials = [row for row in rows if row.get('event') == 'trial']
if len(rows) != 13 or len(trials) != 12 or any(row.get('status') != 'passed' for row in trials):
    raise SystemExit(f'capture rows/status invalid: total={len(rows)} trials={len(trials)}')
print(json.dumps({'status': status, 'events': str(events), 'trials': len(trials), 'peak_bytes': profile['observed']['process_tree_peak_memory_bytes'], 'elapsed_ns': elapsed}, sort_keys=True))
