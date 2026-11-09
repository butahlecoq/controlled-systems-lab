#!/usr/bin/env python3
"""Collect separate whole-process gprof diagnostics, never primary timings."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from run_horizon_ladder import run_with_resource_receipt
from check_family_query import check_process


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--driver',required=True,type=Path);parser.add_argument('--bundle',required=True,type=Path)
    parser.add_argument('--repetitions',type=int,default=20)
    parser.add_argument('--build-cache',required=True,type=Path)
    args=parser.parse_args();driver=args.driver.resolve(strict=True);root=args.bundle/'limiter-profile'
    if root.exists():parser.error('profile path must be new')
    cache=args.build_cache.read_text()
    if 'CSL_REVIEW05_PROFILE_DRIVER:BOOL=ON' not in cache or 'CMAKE_BUILD_TYPE:STRING=Release' not in cache:
        parser.error('profile needs a Release cache with driver profiling enabled')
    environment=json.loads((args.bundle/'environment.json').read_text())
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=Path(__file__).resolve().parents[3],text=True).strip()
    if revision!=environment['source_commit']:parser.error('profile source must match primary capture commit')
    root.mkdir();(root/'CMakeCache.txt').write_text(cache);profiles=[];receipts=[]
    scenario_path=args.bundle/'scenarios/family-query-flat-t08.json'
    scenario=json.loads(scenario_path.read_text());scenario_hash=hashlib.sha256(scenario_path.read_bytes()).hexdigest()
    for index in range(args.repetitions):
        for side in ('csl.synthesis.reach-back','csl.synthesis.strategy-b'):
            folder=root/f'{len(receipts):04d}';folder.mkdir()
            os.environ['GMON_OUT_PREFIX']=str((folder/'gmon').resolve())
            command=[str(driver),str((args.bundle/'scenarios/family-query-flat-t08.json').resolve()),side,'on']
            code,timeout,stdout,stderr,resources=run_with_resource_receipt(command,150)
            (folder/'stdout.txt').write_bytes(stdout);(folder/'stderr.txt').write_bytes(stderr)
            receipt={'strategy':side,'mode':'on','repetition':index,'returncode':code,'timed_out':timeout,'resources':resources}
            receipt['independent_check']=check_process(receipt,stdout,scenario,scenario_hash)
            (folder/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');receipts.append(receipt)
            profiles.extend(sorted(folder.glob('gmon.*')))
    environment=json.loads((args.bundle/'environment.json').read_text())
    result={'schema':'csl.review05.query-limiter/1','source_commit':environment['source_commit'],
        'profile_binary_sha256':hashlib.sha256(driver.read_bytes()).hexdigest(),
        'primary_binary_sha256':environment['binary_sha256'],'profile_files':len(profiles),'attempts':receipts,
        'scope':'separate whole-process gprof CPU sampling; driver compiled -pg, static-library symbols sampled; uninstrumented library call graph incomplete',
        'timing_use':'excluded from primary groups; no strategy ranking or isolated verifier claim',
        'verdict':'inconclusive until sample density and source attribution reviewed'}
    command=['gprof','-b','-p',str(driver),*[str(p.resolve()) for p in profiles]]
    try:
        completed=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
        (root/'gprof.txt').write_bytes(completed.stdout);(root/'gprof-stderr.txt').write_bytes(completed.stderr)
        result.update(gprof_returncode=completed.returncode,gprof_command=command)
    except (OSError,subprocess.TimeoutExpired) as error:
        result.update(gprof_unavailable=str(error))
    (root/'profile.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'attempts':len(receipts),'profile_files':len(profiles)}))

if __name__=='__main__':main()
