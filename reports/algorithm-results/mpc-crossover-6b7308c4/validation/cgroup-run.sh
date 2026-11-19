set -eu
dest=$1
binary=$2
group=/sys/fs/cgroup$(cut -d: -f3 /proc/self/cgroup)
for setting in memory.max memory.swap.max cpu.max; do
  echo "$setting $(cat "$group/$setting")"
done
rg -F Cpus_allowed_list /proc/self/status || awk '/Cpus_allowed_list/' /proc/self/status
cat "$group/cpu.stat" > "$dest/cpu-before"
cat "$group/memory.events" > "$dest/memory-before"
/usr/bin/python3 - "$dest" "$binary" <<'PY'
import json,resource,subprocess,sys,time
from pathlib import Path
dest=Path(sys.argv[1]);t=time.monotonic_ns()
result=subprocess.run([sys.argv[2],str(dest/'workload.json'),str(dest/'raw.jsonl')])
u=resource.getrusage(resource.RUSAGE_CHILDREN)
(dest/'process.json').write_text(json.dumps(dict(status=result.returncode, wall_ns=time.monotonic_ns()-t,user_s=u.ru_utime,system_s=u.ru_stime,max_rss_kib=u.ru_maxrss))+'\n')
result.check_returncode()
PY
cat "$group/cpu.stat" > "$dest/cpu-after"
cat "$group/memory.events" > "$dest/memory-after"
cat "$group/memory.peak" > "$dest/memory-peak"
