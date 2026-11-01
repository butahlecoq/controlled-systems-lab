# Issue 824 classic nominal TwoPoints pilot

This report adds a distinct classic nominal open-loop comparison to the existing `TwoPointsOnParallelLines` differential-game pilot. It uses the pinned source re-expression and current three-stage finite action catalog. The known opponent signal is `v=(+1,+1,+1)`. The comparison enumerates 27 minimizing-control plans for exact polytopes, boxes, zonotopes, parallelotopes and ellipsoids. The selected exact nominal objective is `13.92409225`; its selected action indices are `[0, 0, 0]`.

The separate exact finite minimax reference has value `14.58094225` with the opponent selecting from `(-1, 0, 1)` at each stage. These values use different opponent information and disturbance assumptions. They are shown as adjacent context, not as directly comparable claims.

The source task uses continuous actions and a 10-second horizon. This is an explicit three-stage adaptation. The objective is squared terminal position gap, monotone-equivalent for minimizers to the source negative absolute-gap reward. All values and approximation scores are numerical, not validated arithmetic certificates.

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

One warmup and seven batches of ten calls record descriptive end-to-end API timings for all five nominal tracks together. The interval excludes fixture construction, the separate minimax reference, serialization, independent checking, build and rendering. The report makes no speedup, scalability or bottleneck claim; no separate limiter profile was performed.
