#!/usr/bin/env python3
"""Capture matched DIMENSION-01 vector-integrator runs."""
from __future__ import annotations
import argparse, hashlib, json, os, platform, shutil, subprocess, time
from pathlib import Path

STRATEGIES = ("csl.synthesis.reach-back", "csl.synthesis.strategy-b")
CASES = ((1,2),(1,4),(2,2),(2,4))

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def limit_process() -> None:
    import resource
    resource.setrlimit(resource.RLIMIT_CPU,(300,300))
    cap=8*1024**3
    resource.setrlimit(resource.RLIMIT_AS,(cap,cap))

def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument('--driver',required=True,type=Path)
    parser.add_argument('--scenarios',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    driver=args.driver.resolve(strict=True); scenarios=args.scenarios.resolve(strict=True)
    source=Path(__file__).resolve().parent; repo=scenarios.parents[3]
    output=args.output.resolve()
    if output.exists() and any(output.iterdir()): parser.error('output directory must be empty')
    output.mkdir(parents=True,exist_ok=True); (output/'raw').mkdir(); (output/'inputs').mkdir()
    paths={f'n{n}-t{t}':scenarios/f'dimension01-n{n}-t{t}.json' for n,t in CASES}
    for path in paths.values():
        if not path.is_file(): parser.error(f'missing fixture: {path}')
        shutil.copyfile(path,output/'inputs'/path.name)
    revision=subprocess.run(['git','rev-parse','HEAD'],cwd=repo,check=True,capture_output=True,text=True).stdout.strip()
    dirty=bool(subprocess.run(['git','status','--porcelain','--untracked-files=no'],cwd=repo,check=True,capture_output=True,text=True).stdout)
    try: load=list(os.getloadavg())
    except (AttributeError,OSError): load=None
    env={'source_revision':revision,'source_worktree_dirty':dirty,
         'measurement_source_sha256':{name:sha(source/name) for name in ('CMakeLists.txt','dimension_ladder.cpp','run_dimension_ladder.py','check_dimension_ladder.py','summarize_dimension_ladder.py','render_dimension_ladder.py')},
         'host':platform.node(),'platform':platform.platform(),'machine':platform.machine(),'logical_cpus':os.cpu_count(),
         'physical_memory_bytes':int(os.sysconf('SC_PHYS_PAGES'))*int(os.sysconf('SC_PAGE_SIZE')),
         'python':platform.python_version(),'load_average_at_start':load,'binary_sha256':sha(driver),
         'requested_threads_per_strategy':1,'requested_driver_workers':1,
         'limits':{'cpu_seconds':300,'address_space_bytes':8*1024**3,'process_timeout_seconds':300,'scope':'one strategy process','enforced':True,'mechanism':'POSIX RLIMIT_CPU and RLIMIT_AS'}}
    manifest={'schema':'csl.review05.dimension-manifest/1','track':'new-comparison','fixture':'DIMENSION-01-vector-integrator',
              'cases':{key:{'state_dimension':n,'control_dimension':n,'horizon':t,'scenario_sha256':sha(path)} for (n,t), (key,path) in zip(CASES,paths.items())},
              'environment':env,'schedule':{'warmup_pairs_per_case':1,'measured_pairs_per_case':6,'order':'alternating AB/BA; case order rotates by repetition','timed_region':'steady_clock around SynthesisWorkspace::run only','startup_setup':'excluded from strategy_run_ns; process wall time retained'}}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    attempts_path=output/'attempts.jsonl'
    with attempts_path.open('x'):
        pass
    number=0
    for repetition in range(7):
        keys=list(paths); shift=repetition%len(keys); keys=keys[shift:]+keys[:shift]
        for key in keys:
            n,t=key.removeprefix('n').split('-t'); n=int(n); t=int(t)
            warm=repetition==0
            first=(repetition+int(n)+t//2)%2
            order=(STRATEGIES[first],STRATEGIES[1-first])
            for pos,strategy in enumerate(order):
                number+=1; aid=f'n{n}-t{t}-r{repetition:02d}-p{pos}-{number:03d}'
                cmd=[str(driver),str(paths[key]),strategy]; start=time.monotonic_ns()
                try:
                    proc=subprocess.run(cmd,check=False,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=300,preexec_fn=limit_process)
                    wall=time.monotonic_ns()-start; stdout=proc.stdout; stderr=proc.stderr; code=proc.returncode
                    status='completed' if code==0 else 'failed'
                except subprocess.TimeoutExpired as e:
                    wall=time.monotonic_ns()-start; stdout=e.stdout or b''; stderr=e.stderr or b''; code=None; status='timed_out'
                except Exception as e:
                    wall=time.monotonic_ns()-start; stdout=b''; stderr=str(e).encode(); code=None; status='failed_to_launch'
                outpath=output/'raw'/f'{aid}.stdout'; errpath=output/'raw'/f'{aid}.stderr'; outpath.write_bytes(stdout); errpath.write_bytes(stderr)
                try: result=json.loads(stdout.decode()) if status=='completed' else None; parse_error=None
                except (UnicodeDecodeError,json.JSONDecodeError) as e: result=None; parse_error=str(e); status='invalid_output'
                row={'attempt_id':aid,'case':key,'state_dimension':n,'horizon':t,'repetition':repetition,'warmup':warm,'order_position':pos,'strategy':strategy,
                     'process_status':status,'return_code':code,'process_wall_ns':wall,'scenario_sha256':manifest['cases'][key]['scenario_sha256'],'command':cmd,
                     'stdout_path':str(outpath.relative_to(output)),'stdout_sha256':sha(outpath),'stderr_path':str(errpath.relative_to(output)),'stderr_sha256':sha(errpath),'parse_error':parse_error,'result':result}
                with attempts_path.open('a',encoding='utf-8') as f:
                    f.write(json.dumps(row,separators=(',',':'),allow_nan=False)+'\n')
                    f.flush(); os.fsync(f.fileno())
    return 0
if __name__=='__main__': raise SystemExit(main())
