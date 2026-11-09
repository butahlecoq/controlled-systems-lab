"""Recheck a saved first capture; never launch an algorithm or rewrite inputs."""
import argparse
import csv
from fractions import Fraction as Q
import hashlib
import json
from pathlib import Path,PurePosixPath
import re
import subprocess
import tempfile
import exact_regions as R
import capture_exact_regions as C


def decode(value):
    if isinstance(value,str) and re.fullmatch(r'-?[0-9]+(?:/[0-9]+)?',value):return Q(value)
    if isinstance(value,list):return [decode(x) for x in value]
    if isinstance(value,dict):return {key:decode(x) for key,x in value.items()}
    return value


def check(bundle):
    if bundle.is_symlink() or any(p.is_symlink() for p in bundle.rglob('*')):raise ValueError('symlink capture refused')
    files={p.relative_to(bundle).as_posix():p.read_bytes() for p in bundle.rglob('*') if p.is_file()};expected={}
    for line in files['SHA256SUMS'].decode().splitlines():
        h,n=line.split('  ',1);path=PurePosixPath(n)
        if not re.fullmatch('[0-9a-f]{64}',h) or path.is_absolute() or '..' in path.parts or n in expected:raise ValueError('unsafe/duplicate checksum entry')
        expected[n]=h
    if expected!={n:hashlib.sha256(b).hexdigest() for n,b in files.items() if n!='SHA256SUMS'}:raise ValueError('complete capture inventory differs')
    record=decode(json.loads(files['exact-reference.json']));manifest=json.loads(files['manifest.json'])
    if not re.fullmatch('[0-9a-f]{40}',manifest['source_commit']) or manifest['source_status']:raise ValueError('unclean source identity')
    for name,h in manifest['source_sha256'].items():
        committed=subprocess.check_output(['git','show','--end-of-options',manifest['source_commit']+':'+name],cwd=C.ROOT)
        if hashlib.sha256(committed).hexdigest()!=h:raise ValueError('capture source differs from recorded commit')
    build=json.loads(files['native-build-receipt.json'])
    if build['binary_sha256']!=manifest['binary_sha256'] or build['client_source_sha256']!=manifest['source_sha256']['benchmarks/reporting/mpc08_explicit/mpc08_strategy_comparison.cpp']:
        raise ValueError('native binary/source receipt differs')
    proofs=dict(regions=R.check_regions(record['regions']),geometry=R.check_geometry(record['geometry']),fibers=R.check_fibers(record['fibers']))
    if C.plain(proofs)!=C.plain(record['checks']):raise ValueError('saved exact disposition differs')
    with tempfile.TemporaryDirectory(prefix='mpc08-recheck-') as temporary:
        tmp=Path(temporary);lookup=C.queries(record,tmp);supports=C.support_queries(record,tmp)
        for name in ('unique.csv','nonunique.csv','support.csv'):
            if (tmp/name).read_bytes()!=files[name]:raise ValueError('actual native query input differs from checked reference')
    rows=[];support_rows=[]
    if [p['profile'] for p in manifest['processes']]!=['unique','nonunique','set-support-LP']:raise ValueError('process inventory differs')
    for p in manifest['processes']:
        name='support' if p['profile']=='set-support-LP' else p['profile']
        stdout=files[name+'.stdout.jsonl'];stderr=files[name+'.stderr.txt']
        if hashlib.sha256(stdout).hexdigest()!=p['stdout_sha256'] or hashlib.sha256(stderr).hexdigest()!=p['stderr_sha256']:
            raise ValueError('raw process stream binding differs')
        if p['return_code']!=0 or p['timed_out']:return dict(status='inconclusive-process',proofs=C.plain(proofs))
        (support_rows if name=='support' else rows).extend(json.loads(line) for line in stdout.splitlines())
    numerical=C.check_native(rows,lookup);numerical['lp_support']=C.check_support(support_rows,supports)
    if C.plain(numerical)!=json.loads(files['native-summary.json']):raise ValueError('saved numerical/timing summary differs')
    return dict(status='checked',proofs=C.plain(proofs),native_observations=len(rows),support_observations=len(support_rows),
        scope='exact fixed-fixture reference proofs and numerical native witnesses/candidate observations; no algorithm rerun')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('bundle',type=Path);args=parser.parse_args();print(json.dumps(check(args.bundle.resolve())))
