# Issue 824 classic nominal TwoPoints pilot

This report adds a distinct classic nominal open-loop comparison to the existing `TwoPointsOnParallelLines` differential-game pilot. It uses the pinned source re-expression and current three-stage finite action catalog. The known opponent signal is `v=(+1,+1,+1)`. The comparison enumerates 27 minimizing-control plans for exact polytopes, boxes, zonotopes, parallelotopes and ellipsoids. The selected exact nominal objective is `13.92409225`; its selected action indices are `[0, 0, 0]`.

The separate exact finite minimax reference has value `14.58094225` with the opponent selecting from `(-1, 0, 1)` at each stage. These values use different opponent information and disturbance assumptions. They are shown as adjacent context, not as directly comparable claims.

The source task uses continuous actions and a 10-second horizon. This is an explicit three-stage adaptation. The objective is squared terminal position gap, monotone-equivalent for minimizers to the source negative absolute-gap reward. All values are numerical, not validated arithmetic certificates. Approximation scores are ranking estimates only and establish no certified lower or upper bound on the objective; the saved selected replay is a feasible finite-catalog witness.

The two-panel figure uses player phase planes `(x1,x2)` and `(x3,x4)`. It overlays the nominal replay on the prior report's forward/backward game geometry, intersections, representation projections, and finite minimax trajectories. The geometry is identified by its frozen report hashes in `result.json`.

## Reproduce

```sh
cmake --preset dev -DCSL_BUILD_ISSUE824_NOMINAL_REPORT=ON
cmake --build build/dev --target csl_issue824_nominal_report --parallel 4
python3 scripts/reports/exp824/make_nominal_report.py \
  build/dev/csl_issue824_nominal_report build/dev \
  reports/algorithm-results/issue824-two-points-nominal-v1
python3 scripts/reports/exp824/check_nominal.py \
  reports/algorithm-results/issue824-two-points-nominal-v1/result.json
```

One warmup and seven batches of ten calls record descriptive API timings for all five nominal tracks together. Caller-side status checks and score consumption occur after each timed interval. The interval excludes fixture construction, the separate minimax reference, serialization, independent checking, build and rendering. The immutable v1 capture made no speedup, scalability or bottleneck claim. This v2 bundle adds separate report-path timing and a limiter profile, described below.

## Limiter and report-path evidence (v2)

Five serial end-to-end report generations, each followed by the independent exact checker and manifest verification, took median `1.840 s` (range `1.792–1.931 s`). The API timed region represented median `76.3%`. Across these five trials, 350 measured calls completed with zero failures and identical score checksums. Raw trial data is in `e2e-timing.json`.

A separate Release `-pg` gprof run profiled five runs of 70 calls plus one warmup each. The top sampled self-CPU rows were zonotope corner scoring (54.23%), matrix access (24.86%), and objective evaluation (14.41%). The profiler data is not used for timing. Ten-millisecond sampling and one combined five-track, three-stage fixture limit this inference; there is no per-representation timing, winner, or speedup claim. See `limiter-profile.json`, `limiter-profile.txt`, and `limiter-profile-raw.tar.gz`.

To recompose this v2 record from the saved evidence, first generate the baseline v1 capture using the command above, extract `limiter-profile-raw.tar.gz` into a temporary directory, and run:

```sh
python3 scripts/reports/exp824/compose_nominal_limiter_v2.py \
  --source reports/algorithm-results/issue824-two-points-nominal-v1 \
  --e2e reports/algorithm-results/issue824-two-points-nominal-v2/e2e-timing.json \
  --profile /tmp/issue824-gprof \
  --output reports/algorithm-results/issue824-two-points-nominal-v2-rebuilt
```

The extracted profile directory must contain the five `gprof-run-*.json` files, `gprof-flat.txt`, `gprof-profile.txt`, and five `gmon-*.out` files.
