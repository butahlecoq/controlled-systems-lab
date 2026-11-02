# MPC-01 OSQP / HPIPM resource-capped recapture

This is a new seven-fixture comparison on the authored T-S01/T-S02/T-S03 cases, the exact #421 double-integrator input, infeasible and unbounded analytic cases, and the separately identified `b04-reference-v1` article-derived case. It is not a historical B04 reproduction, a closed-loop MPC experiment, or an acados comparison.

The clean Release driver was built from source revision `8d123f95d925cc7ee515088d0930c3a7b99eec10` with GCC 16.2.1 and the pinned OSQP 1.0.0, HPIPM `e3a56c1caddd7f12d125d84f337b9a9e5c186271`, and BLASFEO `d6251233923c9b475fe894fb729fb63ab693e301`. See `build-identity.json` for executable, source tree, build flags and input hashes.

## Results

Five repetitions were captured for each solver / start-mode arm on each fixture. Solver order alternated by repetition. The run retained 140 attempts across seven canonical records; all 140 had native termination `completed`. The independent Fraction checker verified exact feasibility and candidate objective bounds for all 90 attempts the native solvers classified as optimal. The native classification for infeasible, unbounded and singular cases remains separate from that independent candidate evidence.

The four-dimensional B04 state trajectories are shown in the two fuel/oxidizer projections in `b04-repeated-benchmark-projections.html` and `.svg`. The paths are individual saved solver trajectories, not averaged curves. The exact witness and source identity are retained.

## Enforced resources and limits

The solver capture ran in one systemd user scope on Linux cgroup v2 with `memory.max=8 GiB`, `memory.swap.max=0`, one solver worker pinned to CPU 0, and a 300-second process-group watchdog. All seven fixture runs and their attempts execute sequentially, so the cgroup memory cap bounded every solver call. The watchdog applies to the complete seven-fixture suite, not to each individual attempt. The run completed in 1.703 seconds; process-tree peak memory was 24,743,936 bytes, and all memory-limit/OOM counters were zero. `resource-profile.json` binds the raw stdout and canonical record hashes.

The comparison records themselves still say memory is unlimited: the native driver cannot consume this outer cgroup profile. Treat `resource-profile.json` as separate, bound execution evidence rather than as a claim that the `ComparisonSpec` contains the cap. The capture therefore does not prove the contract's per-attempt wall-time profile. The exact checker ran separately under its own 5-second watchdog, 8 GiB cap and no-swap scope; its observed result is in `exact-checker-resource-profile.json`.

`perf` was unavailable, so this capture has no source-mapped limiter profile. Its timings are descriptive and support no speedup or solver-winner claim. These small QPs do not establish end-to-end planning latency or general control-strategy performance.

## Reproduction

Configure a clean checkout of the recorded source commit and build the private report target:

```sh
cmake -S . -B build/mpc01 -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TESTING=ON -DCSL_BUILD_MPC01_REPORT=ON \
  -DCSL_ENABLE_HIGHS=OFF -DCSL_ENABLE_QHULL=OFF
cmake --build build/mpc01 --target csl_mpc01_native_dependencies --parallel 4
cmake --build build/mpc01 --target csl_mpc01_report mpc01_model_tests --parallel 4
ctest --test-dir build/mpc01 --output-on-failure -R '^mpc01_(model_contract|native_smoke)$'
```

Run the seven fixtures with five alternating repetitions, writing the raw native attempts and canonical comparison records to a fresh destination:

```sh
taskset -c 0 build/mpc01/csl_mpc01_report \
  examples/scenarios/double-integrator-generality.json \
  docs/research/evidence/b04-reference-v1/canonical-case.json \
  --repetitions 5 --records build/mpc01/comparison-records.jsonl
```

For a capped rerun, apply `MemoryMax=8G` and `MemorySwapMax=0` to a cgroup-v2 process scope and enforce a 300-second watchdog around the whole invocation. The committed supervisor records that suite-level scope. The exact checker command and captured checker supervisor are retained alongside the checker output.

The saved bundle includes native stdout, canonical comparison records, all 90 exact checks, checker and solver resource profiles, build/input identity, the B04 projections, a summary, and `SHA256SUMS`. It contains no solver binary or third-party source archives. OSQP is Apache-2.0; HPIPM and BLASFEO are BSD-2-Clause.
