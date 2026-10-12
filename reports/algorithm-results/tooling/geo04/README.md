# GEO-04 report harness

This is a versioned measurement and saved-data reporting harness for the public
GEO-04 APIs. It is separate from solver code and disabled in ordinary builds.
The first report is descriptive for four small analytic fixtures; it will not
compare competitors or claim speedup, production-scale performance, or scaling.

## Phase 1 review boundary

This commit provides the driver, collector, renderer, and reproducibility
instructions for independent harness review. Do not collect accepted timings
until the harness review is complete and the exact algorithm source commit is
fixed. A `--smoke` run is functional coverage only; discard its timing output.

## Scenarios and oracles

* `crossing_octagon`: intersect `[-1,1]^2` with `|x|+|y|<=1.5`; Qhull output
  must match the eight literal vertices `(±1,±0.5)` and `(±0.5,±1)`, once each.
* `empty_intersection`: `x<=0` and `x>=1`; the H conjunction converts to an
  empty V set.
* `affine_equality`: duplicate the band `0<=x<=2, y=1`; preserve both authored
  equality rows and match the two endpoints `(0,1),(2,1)`.
* `essential_rows_highs`: reduce `0<=x<=1, y<=0, y=0`. The selected HiGHS
  adapter currently publishes no supported objective bounds, so the public
  reducer must report `incomplete`, retain all three inequalities and keep the
  equality. The unit-test fixed-bound fixture is not used here.

Each trial constructs fresh sets, registrations, prepared conversion, exclusive
conversion workspace, and (for reduction) HiGHS workspace. Phase intervals are
in nanoseconds. `total_ns` spans input construction to independent oracle
completion; it excludes object destruction and process startup. Component
intervals overlap the total and must not be added together. The reduction
interval includes internal LP queries, whose individual durations are not
exposed by this public API. Provider setup is included in pipeline preparation.
Failures and failed oracles remain explicit trial rows and invalidate the
report group; failed groups receive no success-only timing summary.

All checks use binary64 and absolute tolerance `1e-7`; they are numerical
fixture checks, not exact or validated geometry. Requested resource policy is
one total thread, one outer worker, one thread per worker. HiGHS is configured
internally for one native thread. OS-observed native thread counts and memory
per trial are not exposed. No random seed is used by these deterministic
algorithms. Record unavailable host observations with a reason rather than
inferring them.

## Build and functional check

Request the CMake File API graph before configuring; the collector binds the
driver, compiler, flags, and dependencies to this exact build tree:

```powershell
$api = 'build/geo04-report/.cmake/api/v1/query'
New-Item -ItemType Directory -Force $api | Out-Null
New-Item -ItemType File -Force "$api/codemodel-v2" | Out-Null
New-Item -ItemType File -Force "$api/toolchains-v1" | Out-Null
cmake -S . -B build/geo04-report -G 'Visual Studio 17 2022' -A x64 -DCSL_BUILD_GEO04_REPORT=ON
cmake --build build/geo04-report --config Release --target csl_geo04_intersection_report --parallel 4
build/geo04-report/Release/csl_geo04_intersection_report.exe --smoke
```

The smoke should report one trial per fixture, all with `passed` and
`oracle_passed=true`. Its timings are not accepted measurements.

## Accepted collection, only after independent review

Pin the algorithm code source commit and preserve a sanitized build-provenance
file automatically generated from the CMake File API and final verbose build,
including compiler and version, C++ standard, Release/NDEBUG flags, dependency
graph, executable hash, and source identity. Record an operator note about concurrent work and host load. For
reproducibility, use at least seven measured repetitions and one excluded
warmup, forward/reverse fixture order, and a clean Release executable. Example:

```powershell
$sourceCommit = '9579f9e936d85d66c59003b2a04157c153df6b63'
$harnessCommit = git rev-parse HEAD
python reports/algorithm-results/tooling/geo04/collect.py `
  --exe build/geo04-report/Release/csl_geo04_intersection_report.exe `
  --build-dir build/geo04-report `
  --source-commit $sourceCommit --harness-commit $harnessCommit `
  --concurrent-work build/geo04-report/concurrent-work.txt `
  --profile-evidence build/geo04-report/profile-evidence.txt `
  --repetitions 7 --warmups 1 --out build/geo04-report/collection-001
python reports/algorithm-results/tooling/geo04/render.py `
  --collection build/geo04-report/collection-001 `
  --out build/geo04-report/geo04-report-bundle
```

Before collection, check and record load/core availability. If the platform
cannot expose load, include that limitation and concurrent-work observation.
Use a separate CPU sampling profile with a separate profile-only execution
(for example Windows Performance Recorder CPU sampling and a profile-only run
of all four fixtures); never mix profiled durations into timing trials. Record
the profile command, output hashes, sample counts, process CPU/counter evidence,
and resolved hot functions in `profile-evidence.txt`. Map the hottest resolved
function to source or state that attribution is unavailable. The harness does
not claim a limiter without that evidence. Preserve all per-repetition data,
failures, build provenance, environment, raw stdout/stderr, command, records,
HTML, manifest, and offline ZIP. Render only from the saved records; rendering
must not call the native executable.

Test the renderer and record summary logic without executing the native driver:

```powershell
python reports/algorithm-results/tooling/geo04/test_report_tools.py
python -m py_compile reports/algorithm-results/tooling/geo04/collect.py reports/algorithm-results/tooling/geo04/render.py
```

The record schema `csl.geo04-polyhedral-report/1` is method-specific and
versioned. A future shared reporting pipeline can adapt this payload without
changing solver APIs. Do not add a public catalogue row or publish a URL from
Phase 1; independent review and measurement review remain separate gates.
