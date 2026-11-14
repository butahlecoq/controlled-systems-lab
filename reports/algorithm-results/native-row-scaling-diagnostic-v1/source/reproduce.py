"""Optional Linux source-only replay against a caller-supplied matching SDK. Not used by staging."""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk-prefix', type=Path, required=True)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cmake', default='cmake')
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    root = source.parent
    prefix = args.sdk_prefix.resolve(strict=True)
    inventory = json.loads((root / 'records/sdk-inventory.json').read_text())['files_sha256']
    def verify_sdk():
        for name, digest in inventory.items():
            path = prefix / name
            if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError('Caller SDK differs from captured snapshot: ' + name)
    verify_sdk()
    if args.build.exists() or args.output.exists():
        raise ValueError('Build and output paths must be fresh; no previous attempt may be overwritten')
    args.output.mkdir(parents=True)
    environment = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    def limits():
        resource.setrlimit(resource.RLIMIT_AS, (8*1024**3, 8*1024**3))
        resource.setrlimit(resource.RLIMIT_CPU, (300, 300))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    def run(name, command):
        directory = args.output / name
        directory.mkdir()
        with (directory/'stdout.log').open('wb') as out, (directory/'stderr.log').open('wb') as err:
            process = subprocess.Popen(list(map(str, command)), stdout=out, stderr=err,
                                       env=environment, start_new_session=True, preexec_fn=limits)
            timed_out = False
            try:
                code = process.wait(timeout=300)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(process.pid, signal.SIGKILL)
                code = process.wait()
        (directory/'attempt.json').write_text(json.dumps({'command':list(map(str,command)),
            'returncode':code,'wall_timeout':timed_out,'status':'completed' if code==0 else 'failed_or_refused',
            'scope':'New source replay; does not replace or claim the captured binary/source qualification'},indent=2)+'\n')
        return code
    with (args.output/'native-build.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        subprocess.run([args.cmake,'-S',str(source),'-B',str(args.build),'-DCMAKE_BUILD_TYPE=Release',
                        '-DCMAKE_PREFIX_PATH='+str(prefix)],check=True,env=environment)
        subprocess.run([args.cmake,'--build',str(args.build),'--parallel','1'],check=True,env=environment)
        if run('analytic',[args.build/'analytic',args.output/'analytic-output']) != 0:
            raise RuntimeError('Analytic sanity failed; model runs not started')
        for number in (23,27,28):
            run(f'model-{number}-export',[args.build/'row_scaling_driver','export',f'catalogue-2026/model-{number}/1',args.output/f'model-{number}-original-output'])
            run(f'model-{number}-scale',[args.build/'row_scaling_driver','row-scale',f'catalogue-2026/model-{number}/1',args.output/f'model-{number}-scaled-output'])
    verify_sdk()

if __name__ == '__main__':
    main()
