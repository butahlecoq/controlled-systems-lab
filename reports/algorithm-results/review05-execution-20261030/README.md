# REVIEW-05 current-main execution evidence

Captured 2026-10-30 from clean `main` revision `210bbe39377be3131f537d65d4f0857c6b4c3462`. The main paired timing capture uses the ordinary Release OBS-04 driver; the complete immutable comparison record binds the input/problem, request, source tree, binary, backend versions, tolerances, worker counts and runtime. It contains 32 attempts: one warmup and seven measured runs for each strategy with instrumentation off and on. All 32 attempts returned a complete analytically checked family and two distinct independently verified witnesses.

Reproduce the paired capture from a clean checkout of that revision:

```sh
cmake -S benchmarks/reporting/obs04 -B build/obs04 \
  -DCMAKE_BUILD_TYPE=Release -DCSL_SOURCE_ROOT="$PWD"
cmake --build build/obs04 --target csl_obs04_instrumentation_comparison -j4
mkdir -p reports/algorithm-results/review05-execution-20261030
build/obs04/csl_obs04_instrumentation_comparison \
  --record reports/algorithm-results/review05-execution-20261030/obs04-current-main-comparison.json
```

The main timing record predates the profile-driver-only changes in this branch. The gprof experiment is separate and recorded in [`gprof-whole-process/README.md`](gprof-whole-process/README.md). `perf` is not installed, so gprof data is process-wide, not an acknowledged per-strategy timing window. The profile call metadata says this explicitly.

The paired run is a single two-stage scalar T-S01 fixture. Its numbers describe this capture only; there is no multi-axis size ladder or general winner claim. Summary statistics are in `summary.json`; complete build/runtime provenance is in `environment.json`. `SHA256SUMS` covers every evidence file except itself.
