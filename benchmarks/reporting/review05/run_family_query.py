#!/usr/bin/env python3
"""Retain bounded matched complete-family and real-query attempts; Linux capture."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
from run_horizon_ladder import run_with_resource_receipt

STRATEGIES=('csl.synthesis.reach-back','csl.synthesis.strategy-b')
FILES=[f'{fixture}-t{t:02}.json' for fixture in ('horizon01','family-query-flat') for t in (2,4,8)]

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def command_output(command,cwd=None):
    result=subprocess.run(command,cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    return {'command':command,'returncode':result.returncode,'output':result.stdout}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--driver',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--scenarios',type=Path,default=Path(__file__).parent/'scenarios')
    parser.add_argument('--repetitions',type=int,default=6)
    parser.add_argument('--build-cache',required=True,type=Path)
    args=parser.parse_args()
    if args.repetitions<5:parser.error('at least five measured repetitions required')
    if args.output.exists():parser.error('output must be new; failed attempts are immutable')
    root=Path(__file__).resolve().parents[3];source=Path(__file__).resolve().parent
    revision=command_output(['git','rev-parse','HEAD'],root)['output'].strip()
    status=command_output(['git','status','--porcelain'],root)['output']
    if status:parser.error('capture requires a clean source worktree')
    driver=args.driver.resolve(strict=True);scenarios=args.scenarios.resolve(strict=True)
    cache=args.build_cache.read_text()
    if 'CMAKE_BUILD_TYPE:STRING=Release' not in cache:parser.error('capture requires a Release build cache')
    if 'CSL_REVIEW05_PROFILE_DRIVER:BOOL=ON' in cache:parser.error('primary capture must use the unprofiled driver')
    args.output.mkdir(parents=True);(args.output/'attempts').mkdir();(args.output/'scenarios').mkdir();(args.output/'source').mkdir()
    for name in FILES:shutil.copy2(scenarios/name,args.output/'scenarios'/name)
    for name in ('family_query_ladder.cpp','CMakeLists.txt','run_family_query.py','check_family_query.py','scalar_query_oracle.py','render_family_query.py','run_horizon_ladder.py','profile_family_query.py'):
        shutil.copy2(source/name,args.output/'source'/name)
    # Keep the historical capture/publication route while the working note is
    # stored as plain text in the source tree.
    shutil.copy2(source/'FAMILY-QUERY.txt',args.output/'source'/'FAMILY-QUERY.md')
    for name in ('figure_style.py','plot.py','report_data.py'):
        shutil.copy2(root/'scripts/reports'/name,args.output/'source'/name)
    shutil.copy2(args.build_cache,args.output/'CMakeCache.txt')
    environment={'schema':'csl.review05.family-query-environment/1','source_commit':revision,'source_status':status,
        'binary_sha256':sha(driver),'binary_path':str(driver),'build_cache_sha256':sha(args.build_cache),
        'platform':platform.platform(),'host':platform.node(),'machine':platform.machine(),'python':platform.python_version(),
        'logical_cpus':os.cpu_count(),'cpu':command_output(['lscpu']),
        'load_average_before':os.getloadavg(),'compiler':command_output(['c++','--version']),
        'source_sha256':{p.name:sha(p) for p in (args.output/'source').iterdir()},
        'scenario_sha256':{p.name:sha(p) for p in (args.output/'scenarios').iterdir()},
        'dependency_definition_sha256':{str(p.relative_to(root)):sha(p) for p in (root/'cmake').glob('*Dependencies.cmake')},
        'thread_environment':{key:os.environ.get(key) for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS')},
        'resource_limits':{'cpu_seconds':300,'address_space_bytes':8*1024**3,'wall_timeout_seconds':150,
            'mechanism':'POSIX RLIMIT_CPU/RLIMIT_AS and wait4; hard native heap budgeting unsupported'},
        'execution':'one fresh process per attempt; one requested outer worker and backend thread; alternating AB/BA within each fixture/mode',
        'repetitions':args.repetitions,'warmup_pairs_per_fixture_mode':1,
        'instrumentation':'OBS actual-operation collector enabled/disabled in same binary; native-clock instrumentation not part of this capture',
        'comparison_claim':'inconclusive; descriptive matched-workload observations, no ranking, asymptotic or real-time claim',
        'unavailable':['isolated verifier wall time','native heap high-water enforcement','generic membership/slice APIs','native-clock enabled/disabled overhead']}
    (args.output/'environment.json').write_text(json.dumps(environment,indent=2)+'\n')
    index=0
    # Rotate fixture and collector order each repetition; alternate strategy side.
    for repetition in range(-1,args.repetitions):
        names=FILES[repetition%len(FILES):]+FILES[:repetition%len(FILES)]
        modes=('off','on') if repetition%2==0 else ('on','off')
        for name in names:
            for mode in modes:
                sides=STRATEGIES if repetition%2==0 else STRATEGIES[::-1]
                for side in sides:
                    attempt=args.output/'attempts'/f'{index:04d}';attempt.mkdir();index+=1
                    command=[str(driver),str((args.output/'scenarios'/name).resolve()),side,mode]
                    start=time.perf_counter_ns();load=os.getloadavg()
                    code,timed_out,stdout,stderr,resources=run_with_resource_receipt(command,150)
                    (attempt/'stdout.txt').write_bytes(stdout);(attempt/'stderr.txt').write_bytes(stderr)
                    receipt={'scenario':name,'strategy':side,'mode':mode,'repetition':repetition,'warmup':repetition==-1,
                        'command':command,'returncode':code,'timed_out':timed_out,'process_wall_ns':time.perf_counter_ns()-start,
                        'load_average_at_start':load,'active_compiler_processes':command_output(['pgrep','-c','cc1plus'])['output'].strip(),'resources':resources,'stdout_sha256':sha(attempt/'stdout.txt'),'stderr_sha256':sha(attempt/'stderr.txt')}
                    (attempt/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    # Deliberate row-budget refusal is retained separately and excluded from timing summaries.
    for side in STRATEGIES:
        attempt=args.output/'attempts'/f'{index:04d}';attempt.mkdir();index+=1;name=FILES[0]
        command=[str(driver),str((args.output/'scenarios'/name).resolve()),side,'on','1']
        code,timeout,stdout,stderr,resources=run_with_resource_receipt(command,150)
        (attempt/'stdout.txt').write_bytes(stdout);(attempt/'stderr.txt').write_bytes(stderr)
        (attempt/'receipt.json').write_text(json.dumps({'scenario':name,'strategy':side,'mode':'on','repetition':None,'warmup':False,
            'refusal_probe':True,'command':command,'returncode':code,'timed_out':timeout,'resources':resources,
            'stdout_sha256':sha(attempt/'stdout.txt'),'stderr_sha256':sha(attempt/'stderr.txt')},indent=2)+'\n')
    environment['load_average_after']=os.getloadavg();environment['attempts']=index
    (args.output/'environment.json').write_text(json.dumps(environment,indent=2)+'\n')
    print(json.dumps({'bundle':str(args.output),'attempts':index,'source_commit':revision}))
    return 0

if __name__=='__main__':raise SystemExit(main())
