"""Shared checked-source and receipt bindings for MPC10 checker and renderer."""
import hashlib
import json
import math
from pathlib import Path,PurePosixPath
import re
import subprocess

SOURCE=Path(__file__).resolve().parent

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
    environment=load(bundle/'environment.json');revision=environment['source_revision']
    if not isinstance(revision,str) or not re.fullmatch('[0-9a-f]{40}',revision):raise ValueError('capture revision must be full hexadecimal')
    for name,digest in environment['source_sha256'].items():
        path=(bundle/'source'/name).resolve()
        if PurePosixPath(name).name!=name or name in ['.','..'] or not path.is_relative_to((bundle/'source').resolve()):raise ValueError('unsafe copied source name')
        if sha(path)!=digest:raise ValueError('copied source binding mismatch')
        committed=subprocess.check_output(['git','show','--end-of-options',revision+':benchmarks/reporting/mpc10/'+name],cwd=SOURCE)
        if path.read_bytes()!=committed:raise ValueError('copied source differs from capture commit')
    return actual


def checked_verification(bundle,verification):
    actual=checked_capture(bundle);receipt=load(verification)
    if receipt['schema']!='csl.mpc10.check/1' or receipt['input_files']!=actual:raise ValueError('verification input binding mismatch')
    for name,digest in receipt['checking_sources'].items():
        if PurePosixPath(name).name!=name or name in ['.','..']:raise ValueError('unsafe checker source name')
        if sha(SOURCE/name)!=digest:raise ValueError('verification checker source binding mismatch')
    return receipt
