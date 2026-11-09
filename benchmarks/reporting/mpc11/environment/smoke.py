#!/usr/bin/env python3
"""Record bounded optional-environment imports and IPOPT plugin availability."""
from __future__ import annotations
import ctypes
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import resource
import sys
import warnings

# This script checks plugin loading only. It never creates or solves an NLP.
for variable in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[variable] = '1'
resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
resource.setrlimit(resource.RLIMIT_AS, (4 * 1024**3, 4 * 1024**3))
import casadi
with warnings.catch_warnings(record=True) as import_warnings:
    warnings.simplefilter("always")
    import do_mpc

root = Path(casadi.__file__).parent
plugins = sorted(str(p.relative_to(root)) for p in root.glob('*')
                 if any(token in p.name.lower() for token in ('ipopt', 'mumps', 'blas')))
ipopt_version = None
library = next(iter(sorted(root.glob('libipopt.so*'))), None)
if library is not None:
    lib = ctypes.CDLL(str(library))
    try:
        get_version = lib.IpoptGetVersion
        get_version.argtypes = [ctypes.POINTER(ctypes.c_int)] * 3
        major, minor, release = ctypes.c_int(), ctypes.c_int(), ctypes.c_int()
        get_version(ctypes.byref(major), ctypes.byref(minor), ctypes.byref(release))
        ipopt_version = f'{major.value}.{minor.value}.{release.value}'
    except AttributeError:
        pass
mumps_header = root / 'include/coin-or/mumps/dmumps_c.h'
mumps_match = re.search(r'#define MUMPS_VERSION "([^"]+)"', mumps_header.read_text())
ipopt_header = root / 'include/coin-or/IpoptConfig.h'
ipopt_match = re.search(r'#define IPOPT_VERSION "([^"]+)"', ipopt_header.read_text())
result = {
    'schema': 'csl.mpc11.environment-smoke/1',
    'python': platform.python_version(), 'implementation': platform.python_implementation(),
    'platform': platform.platform(), 'machine': platform.machine(),
    'packages': {name: importlib.metadata.version(name) for name in
                 ('do-mpc','casadi','numpy','scipy','pandas','matplotlib')},
    'casadi_version': casadi.__version__, 'ipopt_plugin_available': bool(casadi.has_nlpsol('ipopt')),
    'ipopt_c_api_version': ipopt_version,
    'ipopt_header_version': ipopt_match.group(1) if ipopt_match else None,
    'ipopt_header_sha256': hashlib.sha256(ipopt_header.read_bytes()).hexdigest(),
    'ipopt_version_scope': 'bundled header/library filename; C API getter unavailable when null',
    'cvodes_plugin_available': bool(casadi.has_integrator('cvodes')),
    'import_warnings': [str(item.message) for item in import_warnings],
    'mumps_header_version': mumps_match.group(1) if mumps_match else None,
    'mumps_header_sha256': hashlib.sha256(mumps_header.read_bytes()).hexdigest(),
    'mumps_version_scope': 'bundled header declaration; no MUMPS factorization performed',
    'python_executable_sha256': hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
    'native_libraries': [{'file': name, 'sha256': hashlib.sha256((root/name).read_bytes()).hexdigest()}
                         for name in plugins if (root/name).is_file()],
    'thread_environment': {name: os.environ[name] for name in
                           ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')},
    'limits': {'cpu_seconds':60, 'address_space_bytes':4*1024**3, 'scope':'smoke process'},
    'solver_invoked': False, 'claim': 'import/plugin-load smoke; no controller or numerical performance evidence',
}
print(json.dumps(result, indent=2))
if not result['ipopt_plugin_available']:
    sys.exit(1)
