"""Shared checked-source and receipt bindings for MPC10 checker and renderer."""
import hashlib
import json
import math
from pathlib import Path,PurePosixPath
import re
import subprocess

SOURCE=Path(__file__).resolve().parent
CHECKING_SOURCE_FILES=frozenset(('check.py','evidence.py','figures.py','fixtures.py','metrics.py','oracle.py','run.py','scip_reference.py'))
SOURCE_PREFIX='benchmarks/reporting/mpc10/'

def revision(value):
    if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{40}',value):raise ValueError('source revision must be full hexadecimal')
    return value

def git_bytes(commit,name):
    return subprocess.check_output(['git','show','--end-of-options',commit+':'+SOURCE_PREFIX+name],cwd=SOURCE)

def validate_map(values,required,label):
    if not isinstance(values,dict) or set(values)!=set(required):raise ValueError(label+' mandatory source inventory differs')
    if any(not isinstance(v,str) or not re.fullmatch('[0-9a-f]{64}',v) for v in values.values()):raise ValueError(label+' source digest invalid')

def captured_source_files(commit):
    # Exactly the top-level glob inventory copied by run.capture at that commit.
    names=subprocess.check_output(['git','ls-tree','--name-only',commit+':'+SOURCE_PREFIX.rstrip('/')],cwd=SOURCE.parents[2],text=True).splitlines()
    required={name for name in names if name.endswith(('.py','.cpp')) or name=='CMakeLists.txt'}
    if not {'run.py','oracle.py','check.py','evidence.py','bridge.cpp','CMakeLists.txt'}<=required:raise ValueError('capture commit lacks required source profile')
    return required

def checking_identity():
    commit=revision(subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip())
    values={name:sha(SOURCE/name) for name in CHECKING_SOURCE_FILES}
    return commit,values

def load(path):
    def finite(text):
        value=float(text)
        if not math.isfinite(value):raise ValueError('nonfinite numerical evidence')
        return value
    def reject(text):raise ValueError('nonfinite numerical evidence: '+text)
    return json.loads(path.read_text(),parse_float=finite,parse_constant=reject)

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def inventory(bundle):
    if any(p.is_symlink() for p in bundle.rglob('*')):raise ValueError('capture symlink unsupported')
    return {p.relative_to(bundle).as_posix():sha(p) for p in sorted(bundle.rglob('*')) if p.is_file() and p!=bundle/'file-hashes.json'}


def checked_capture(bundle):
    expected=load(bundle/'file-hashes.json');actual=inventory(bundle)
    if actual!=expected:raise ValueError('capture inventory/checksum mismatch')
    environment=load(bundle/'environment.json');commit=revision(environment['source_revision'])
    required=captured_source_files(commit)
    validate_map(environment.get('source_sha256'),required,'capture')
    if {p.name for p in (bundle/'source').iterdir()}!=required:raise ValueError('copied source directory inventory differs')
    for name,digest in environment['source_sha256'].items():
        path=(bundle/'source'/name).resolve()
        if PurePosixPath(name).name!=name or name in ['.','..'] or not path.is_relative_to((bundle/'source').resolve()):raise ValueError('unsafe copied source name')
        if sha(path)!=digest:raise ValueError('copied source binding mismatch')
        committed=git_bytes(commit,name)
        if path.read_bytes()!=committed:raise ValueError('copied source differs from capture commit')
    return actual


def checked_verification(bundle,verification):
    actual=checked_capture(bundle);receipt=load(verification)
    if receipt['schema']!='csl.mpc10.check/1' or receipt['input_files']!=actual:raise ValueError('verification input binding mismatch')
    validate_map(receipt.get('checking_sources'),CHECKING_SOURCE_FILES,'checker')
    commit=revision(receipt.get('checking_revision'))
    for name,digest in receipt['checking_sources'].items():
        if PurePosixPath(name).name!=name or name in ['.','..']:raise ValueError('unsafe checker source name')
        if sha(SOURCE/name)!=digest:raise ValueError('verification checker source binding mismatch')
        if (SOURCE/name).read_bytes()!=git_bytes(commit,name):raise ValueError('checker source differs from checking commit')
    return receipt
