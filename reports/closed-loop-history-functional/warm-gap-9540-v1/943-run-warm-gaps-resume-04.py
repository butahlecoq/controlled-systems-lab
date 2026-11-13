"""Sequential orchestration only; decisions remain in existing admitted profiles."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

R = Path('/home/butahlecoq/.local/share/codex/tmp/learning-control-execution-20261111')
SOURCE = Path('/home/butahlecoq/.codex/worktrees/3e28/controlled-systems-lab')
PYTHON = R / 'controller-env/bin/python'
BUILD = R / '943-warm-gap-installed-build'
ROOT = R / '943-warm-gap-functional-9540-resume-04'
PREFLIGHT = json.loads((R / '943-warm-gap-preflight.json').read_text())
CASES = [
 ('syn-nl-lv-01','direct-ipopt'), ('syn-nl-fuel-01','direct-ipopt'), ('earth-orbit','direct-ipopt'),
 ('syn-nl-lv-01','polytope'),
 *[('syn-nl-fuel-01',f) for f in ('zonotope','parallelotope','ellipsoid','polytope')],
 *[('earth-orbit',f) for f in ('box','zonotope','parallelotope','ellipsoid','polytope')],
 ('syn-nl-lv-01','direct-highs'), ('syn-nl-fuel-01','direct-highs'),
]

def sha(path):
 return hashlib.sha256(path.read_bytes()).hexdigest()

def binding_check():
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip()==PREFLIGHT['source_commit']
 assert subprocess.check_output(['git','status','--porcelain'],cwd=SOURCE,text=True)==''
 for name,digest in PREFLIGHT['bridge_binaries'].items(): assert sha(BUILD/name)==digest,name
 assert sha(SOURCE/'docs/catalogue/closed-loop-history-capabilities-v1.json')==PREFLIGHT['history_manifest_sha256']
 for rel,digest in PREFLIGHT['installed_libraries_and_cmake'].items(): assert sha(Path(PREFLIGHT['sdk_snapshot'])/rel)==digest,rel

CASES = CASES[5:]
# Previous numerical episode is complete; its coverage composition may finish independently.
old_attempt=next((R/'943-warm-gap-functional-9540-resume-03').glob('*/results/*/attempts/*/attempt.json'))
while True:
 old=json.loads(old_attempt.read_text())
 if all(old.get(k)=='complete' for k in ('overall_status','postcheck_status','render_status')):break
 time.sleep(1)
def retire_old_launcher():
 old_parent=Path('/proc/4145350/stat')
 while old_parent.exists() and old_parent.read_text().split(') ',1)[1].split()[0] != 'Z':time.sleep(1)
 (R/'943-warm-gap-resume-03-observed-terminal.json').write_text(json.dumps({'parent_proc_stat':old_parent.read_text() if old_parent.exists() else None,'attempt':json.loads(old_attempt.read_text()),'observation':'Previous numerical worker and replay/render finished before new numerical work. Its outer coverage composition finished separately; only the deliberately paused sequential launcher is retired.'},indent=2)+'\n')
 subprocess.run(['/usr/bin/systemctl','--user','stop','csl943-warm-gaps-9540-03.service'],check=True)
__import__('threading').Thread(target=retire_old_launcher,daemon=True).start()

binding_check()
ROOT.mkdir(exist_ok=False)
(ROOT/'preflight.json').write_text(json.dumps(PREFLIGHT,indent=2)+'\n')
(ROOT/'launcher-source.py').write_bytes(Path(__file__).read_bytes())
(ROOT/'external-worker-placement-source.py').write_bytes((R/'943-isolated-worker-supervisor.py').read_bytes())
subprocess.run(['git','archive','--format=tar.gz','--output='+str(ROOT/'source-9540.tar.gz'),PREFLIGHT['source_commit']],cwd=SOURCE,check=True)
env = os.environ.copy()
env.update(TMPDIR='/home/butahlecoq/.local/share/codex/tmp',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1',CSL_NATIVE_POLICY_BRIDGE=str(BUILD/'history_policy'))
summary=[]
for index,(task,family) in enumerate(CASES):
 binding_check()
 cid=('native-continuous-affine-history-mpc/1' if family=='direct-highs' or (family=='direct-ipopt' and task=='earth-orbit') else
      'native-continuous-affine-history-ipopt/1' if family=='direct-ipopt' else f'native-continuous-history-{family}-ipopt/1')
 cell=ROOT/f'{index+1:02d}-{task}-{family}';cell.mkdir()
 command=[str(PYTHON),str(R/'943-isolated-worker-supervisor.py'),'--task',task,'--bridge',str(BUILD/'nonlinear_replay'),'--policy-adapter','history_policy:create_policy','--controller-id',cid,'--output-root',str(cell/'results'),'--attempt-wall-seconds','1800','--attempt-cpu-seconds','1800']
 launch={'task':task,'family':family,'controller_id':cid,'command':command,'source_commit':PREFLIGHT['source_commit'],'sdk_producer_commit':PREFLIGHT['sdk_producer_commit'],'binary_sha256':PREFLIGHT['bridge_binaries'],'task_sha256':PREFLIGHT['tasks'][task]['task_sha256'],'environment':{k:env[k] for k in ('TMPDIR','OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS','CSL_NATIVE_POLICY_BRIDGE')},'scope':'#943 one-off functional outcome; not timing/exhaustive #947 completion','native_stderr':'shared supervised worker stream; query request/response associated separately','external_resource_envelope':{'worker_units':'per-attempt csl943-worker-*.service','memory_max_bytes':2*1024**3,'memory_swap_max_bytes':2*1024**3,'oom_policy':'stop','scope':'numerical worker subtree only; outer supervisor outside worker memory domain; original worker1800s wall/CPU and8GiB per-process RLIMIT_AS retained; not uniform with initial direct runs'},'start_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
 (cell/'launch.json').write_text(json.dumps(launch,indent=2)+'\n')
 print(f'START {index+1}/10 {task} {family}',flush=True)
 with (cell/'parent-stdout.log').open('wb') as stdout,(cell/'parent-stderr.log').open('wb') as stderr:
  result=subprocess.run(command,cwd=SOURCE,env=env,stdout=stdout,stderr=stderr)
 attempts=[json.loads(p.read_text()) for p in (cell/'results').glob('*/attempts/*/attempt.json')]
 row={'task':task,'family':family,'controller_id':cid,'cell':str(cell),'parent_exit_code':result.returncode,'end_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'outcomes':[{k:a.get(k) for k in ('attempt_id','status','algorithm_status','overall_status','completed_holds','postcheck_status','render_status')} for a in attempts]}
 (cell/'parent-terminal.json').write_text(json.dumps(row,indent=2)+'\n')
 summary.append(row);(ROOT/'sequential-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 print('TERMINAL '+json.dumps(row),flush=True)
print('All 10 resumed sequential attempts have terminal parent outcomes',flush=True)
