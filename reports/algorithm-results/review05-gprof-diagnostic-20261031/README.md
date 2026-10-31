# REVIEW-05 gprof call-graph diagnostic

This is a source-attribution probe for the existing T-S01/T-S02/T-S03 paired
profile matrix. It is not timing evidence: the executable was built with GCC
Release optimization and `-pg`, and its reported durations must not be compared
with ordinary Release measurements.

## Capture identity

- Source commit: `be94be8923a576d6f7cb9b527d818b3469cd0606`
- Executable SHA-256: `c1b471b8092bf270ff306e27c6daf59a6b1f65a26e2cedc187d5b26f91a02b2e`
- Compiler: GCC 16.2.1, Release `-O3 -DNDEBUG -pg`
- Profiler: GNU gprof 2.47
- Existing matrix driver: one warmup and 7/5/5 measured alternating pairs
- Process limits: 300 seconds CPU, 8 GiB address space, 300 seconds wall time
- Host: Linux x86_64, 8 logical CPUs
- gprof data: the three `gmon/capture.*` files in `gmon-data.zip`, emitted using `GMON_OUT_PREFIX`
- Raw events and process receipts: `raw-gmon/`
- Independent family/witness checks: `checks.json`

The paired correctness checker passed all measured attempts: T-S01 7/7,
T-S02 5/5, and T-S03 5/5 per strategy. All six profile processes exited zero
without timing out.

## Result

The samples are too sparse for a limiter conclusion. T-S01 and T-S02 each
accumulated about 0.02 seconds at gprof's 0.01-second sample resolution;
T-S03 accumulated no timer samples. The sampled T-S01 entries include HiGHS
factor solves and KKT checks, but two coarse ticks cannot distinguish solver
work from setup or attribute a strategy bottleneck. T-S02's samples are also
too sparse, and T-S03 provides call counts without sampled-time attribution.

The full gmon inputs are compressed in `gmon-data.zip`. The text call graphs
are `gprof-ts01.txt`, `gprof-ts02.txt`, and `gprof-ts03.txt`. The raw JSONL
events contain strategy outputs used by the independent checker. Their
`strategy_run_ns` fields come from the instrumented executable and are retained
for provenance only; they are not reportable timing data.

This diagnostic does not address the #95 matched size/output-growth sweep.
The existing profiles all use the same one-state, one-control, two-step
dynamics. No complexity, winner, speedup, or general limiter claim follows.

## Reproduction

At the source commit above, configure `benchmarks/reporting/review05` as a
Release CMake build with `CMAKE_CXX_FLAGS_RELEASE='-O3 -DNDEBUG -pg'` and
`CMAKE_EXE_LINKER_FLAGS=-pg`, then build `csl_review05_profile_matrix`. Run
`capture_profile_matrix.py` with `GMON_OUT_PREFIX` set to an empty output
directory prefix, validate its raw output with `check_profile_matrix.py`, and
run `gprof -b <executable> <gmon-file>` for each captured process. Keep all
instrumented durations out of performance comparisons.
