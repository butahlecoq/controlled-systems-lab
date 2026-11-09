# Optional MPC-11 environment

This environment supports the two authored scenarios in `../scenarios` under
[the controller-study contract](../../../../docs/contracts/mpc11-synthetic-controller-study.md).
It is optional research tooling and adds no required CSL runtime dependency.
No acados package or plugin is installed or invoked.

The lock targets Linux x86-64 CPython 3.11.14. It pins the exact wheels selected
on the capture host, not every platform distribution of the same package
version. A different platform requires a new artifact lock and smoke receipt.
The wheel manifest records publisher URLs, SHA-256 values, declared
requirements and license/notice members retained byte-for-byte in `notices.zip`. Installed binary versions and
hashes are recorded separately by the smoke script.

Create a dedicated environment using an existing CPython 3.11.14 installation:

```sh
python3.11 -m venv "$MPC11_VENV"
"$MPC11_VENV/bin/python" -m pip download --only-binary=:all: \
  --require-hashes -r benchmarks/reporting/mpc11/environment/requirements-linux-cp311.lock \
  --dest "$MPC11_WHEELS"
"$MPC11_VENV/bin/python" -m pip install --no-index --find-links "$MPC11_WHEELS" \
  --require-hashes -r benchmarks/reporting/mpc11/environment/requirements-linux-cp311.lock
"$MPC11_VENV/bin/python" -m pip check
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  "$MPC11_VENV/bin/python" benchmarks/reporting/mpc11/environment/smoke.py \
  > environment-smoke.json
```

Set `MPC11_VENV` and `MPC11_WHEELS` to dedicated user-owned directories before
running these commands. Do not point them at a system environment. Retain the
Python interpreter provenance and executable hash; the requirements lock covers
third-party distributions, not Python itself or the operating system.

`lock_wheels.py --wheels "$MPC11_WHEELS" --output <NEW_DIRECTORY>` independently
checks each wheel against PyPI publisher metadata and archives its notice
files. Use a new output directory when qualifying a changed environment;
preserve the previous manifest and smoke outcome. The script does not install
anything. Version pins do not imply that every bundled optional solver is
licensed for every use. The initial profile loads only IPOPT/MUMPS and CVODES;
other bundled interfaces are outside this study.

The smoke script imports do-mpc/CasADi and checks IPOPT plugin availability. It
uses one BLAS/OpenMP thread, a 60-second CPU cap and 4 GiB address-space cap.
It does not create or solve an NLP. Its success is environment evidence only,
not model feasibility, controller correctness or benchmark evidence.

Scenario validation uses the Python standard library:

```sh
python3 benchmarks/reporting/mpc11/check_scenarios.py
python3 -m unittest tests.reporting.test_mpc11_scenarios
```

These checks cover configuration dimensions, units, bounds, physical grids,
objective scaling, declared controller conventions, fuel nominal commands and
LV reference consistency. They do not numerically integrate either plant or
certify a feasible control plan.

No library/package release is needed for these input and optional-environment
files. Later solver/controller integration needs its own evidence and delivery
review. The source implementation, numerical capture and result publication
remain tracked by #607.

## Captured qualification

The retained smoke receipt uses CPython 3.11.14, do-mpc 5.1.2 and CasADi
3.8.0. IPOPT and CVODES plugins load; bundled headers declare IPOPT 3.14.19
and MUMPS 5.8.2. The IPOPT C API version getter is unavailable in this binary,
so the record labels its version as header/library evidence rather than a
runtime solver report. No NLP or factorization was executed. `pip check`
reports no broken requirements. The actual CasADi wheel is
`casadi-3.8.0-cp311-abi3-manylinux_2_28_x86_64.whl`, differing from the earlier
manylinux2014 candidate in the design note; the manifest's publisher hash is
binding for this optional environment.

The environment omits optional ONNX, OPC UA and PyTorch features. Their three
import warnings are retained as text in the smoke JSON. The notice inventory
contains all 146 selected notice/license members from the exact 15 wheels.
CasADi includes third-party interfaces beyond the chosen IPOPT/MUMPS/CVODES
profile; copying their notices does not activate or qualify those interfaces.
The bundled MUMPS notice identifies CeCILL-C. Its referenced English and French
license documents and PORD README are supplied separately in
`upstream-mumps-license.zip`, extracted from the authoritative MUMPS 5.8.2
source archive. `upstream-mumps-license.json` records its source URL, archive
hash and each copied member hash. The original wheel notice archive remains
unchanged. CeCILL-C Article 5.3.1 conditions redistribution of unmodified
software on providing the agreement, warranty/liability notice and effective
source access when redistributing object code. Thus the license text is
relevant to redistribution, not merely optional reading. This local environment
qualification does not redistribute the solver binary or establish blanket
license compliance for every future packaging route.
The environment is installed locally for research, not redistributed as a CSL
binary package.

The interpreter was installed as a user tool with `mise install
python@3.11.14`, using the python-build-standalone artifact
`cpython-3.11.14+20260211-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz`.
The smoke receipt records the installed Python executable hash. Recreating
Python on a different system may produce a different executable hash even with
the same Python version; retain that difference explicitly.

The checker accepts only the two fixed authored scenario profiles. A semantic
change requires a reviewed new profile; canonical digests are independent of
JSON formatting and object-key order. Successful environment qualification
requires both IPOPT and CVODES plugin flags; missing either yields exit 1 after
writing the receipt.
