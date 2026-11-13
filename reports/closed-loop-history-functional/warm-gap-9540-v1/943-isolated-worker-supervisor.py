"""External process-placement instrumentation; imports frozen runner unchanged."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

SOURCE=Path('/home/butahlecoq/.codex/worktrees/3e28/controlled-systems-lab')
ORIGINAL_POPEN=subprocess.Popen
PROPERTIES=('Id','MainPID','ActiveState','SubState','Result','ExecMainCode','ExecMainStatus',
            'MemoryCurrent','MemoryPeak','MemorySwapCurrent','MemorySwapPeak','MemoryMax',
            'MemorySwapMax','OOMPolicy','ManagedOOMMemoryPressure','ManagedOOMSwap','ControlGroup')

def inspect_unit(unit):
 command=['/usr/bin/systemctl','--user','show',unit]
 for p in PROPERTIES:command.extend(['-p',p])
 proc=ORIGINAL_POPEN(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 stdout,stderr=proc.communicate(timeout=5)
 return {'observed_unix_seconds':time.time(),'systemctl_exit_code':proc.returncode,
         'properties':dict(line.split('=',1) for line in stdout.splitlines() if '=' in line),
         'stderr':stderr}

class IsolatedWorker(ORIGINAL_POPEN):
 def __init__(self,command,*,attempt,memory_max=2*1024**3,swap_max=2*1024**3,runtime=1800,**kwargs):
  self.unit='csl943-worker-'+uuid.uuid4().hex[:16]+'.service';self.attempt=Path(attempt)
  self.telemetry=self.attempt/'worker-systemd-telemetry.jsonl';self.stop_telemetry=threading.Event()
  env=kwargs.get('env',os.environ)
  wrapped=['/usr/bin/systemd-run','--user','--wait','--pipe','--service-type=exec','--unit='+self.unit,
           '-p','MemoryMax='+str(memory_max),'-p','MemorySwapMax='+str(swap_max),
           '-p','OOMPolicy=stop','-p','RuntimeMaxSec='+str(runtime),'-p','TimeoutStopSec=1',
           '-p','KillMode=control-group','-p','WorkingDirectory='+str(SOURCE)]
  forwarded={}
  for key in ('TMPDIR','OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS','CSL_NATIVE_POLICY_BRIDGE'):
   if key in env:wrapped.append('--setenv='+key+'='+env[key]);forwarded[key]=env[key]
  wrapped.extend(command)
  (self.attempt/'worker-systemd-launch.json').write_text(json.dumps({'unit':self.unit,'command':wrapped,'original_command':command,
      'forwarded_environment':forwarded,'supervisor_pid':os.getpid(),'supervisor_cgroup':Path('/proc/self/cgroup').read_text(),
      'scope':'numerical worker and descendants only; supervisor outside; additional2GiB memory+2GiB swap envelope, original AS8GiB and CPU/wall1800 worker limits retained'},indent=2)+'\n')
  super().__init__(wrapped,**kwargs)
  self.monitor=threading.Thread(target=self._monitor,daemon=True);self.monitor.start()
 def _monitor(self):
  while not self.stop_telemetry.is_set():
   try:
    observation=inspect_unit(self.unit)
    with self.telemetry.open('a') as stream:stream.write(json.dumps(observation)+'\n')
   except Exception as error:
    with self.telemetry.open('a') as stream:stream.write(json.dumps({'telemetry_error':str(error)})+'\n')
   self.stop_telemetry.wait(.5)
 def communicate(self,*args,**kwargs):
  try:result=super().communicate(*args,**kwargs)
  except subprocess.TimeoutExpired:raise
  else:
   terminal=inspect_unit(self.unit);terminal['systemd_run_returncode']=self.returncode
   (self.attempt/'worker-systemd-terminal.json').write_text(json.dumps(terminal,indent=2)+'\n')
   self.stop_telemetry.set();self.monitor.join(timeout=6)
   return result

def popen(command,*args,**kwargs):
 if isinstance(command,(list,tuple)) and '--worker' in command and str(SOURCE/'benchmarks/reporting/closed_loop/run_closed_loop.py') in command:
  assert not args
  attempt=command[command.index('--attempt')+1]
  return IsolatedWorker(command,attempt=attempt,**kwargs)
 return ORIGINAL_POPEN(command,*args,**kwargs)

if __name__=='__main__':
 sys.path.insert(0,str(SOURCE/'benchmarks/reporting/closed_loop'))
 import run_closed_loop
 subprocess.Popen=popen
 raise SystemExit(run_closed_loop.main())
