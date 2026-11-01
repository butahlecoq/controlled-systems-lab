# Matched TwoPoints fixed-plan minimax run

This report compares the exact finite-polytope search and outer box, zonotope, fixed-frame parallelotope, and axis-aligned ellipsoid selectors on the pinned `TwoPointsOnParallelLines` source adaptation. It uses state `(x1,x2,x3,x4)`, initial `(4.5,0,0,0)`, horizon 3, control catalog `(-2.5, 0, 2.5)`, disturbance catalog `(-1, 0, 1)`, and terminal squared position gap. Re-expressing the pinned source's ten Euler substeps gives `x1'=x1+0.01x2+0.09u`, `x2'=u`, `x3'=x3+0.1x4+0.0045v`, and `x4'=x4+0.1v`; first-player damping resets its velocity to the selected input each outer step.

All methods received the same immutable request and attempted to score all 27 action plans. Completed selected plans were replayed across all 27 disturbance histories. Independent rational enumeration verifies completed replays and the exact minimax value. Any failed method call remains in `result.json`; the independent check is marked `incomplete` when one or more attempts fail or are absent. Approximation scores are numerical ranking estimates; no objective bound or global optimizer-family completeness is claimed.

## Timings

Release build, one warmup and five order-rotated attempts per method. The timed interval covers the public call and extraction/checking of its selected result. Fixture construction, serialization, independent rational checking, and plotting are excluded. Failed calls retain their elapsed duration and error detail and are not silently dropped.

| Track | Runs | Median | Range |
| --- | ---: | ---: | ---: |
| Exact finite polytope | 5/5 (failures: 0) | 0.360 ms | 0.345–0.369 ms |
| Outer box | 5/5 (failures: 0) | 0.181 ms | 0.177–0.184 ms |
| Outer zonotope | 5/5 (failures: 0) | 151.913 ms | 151.314–152.705 ms |
| Fixed-frame parallelotope | 5/5 (failures: 0) | 0.691 ms | 0.687–0.705 ms |
| Axis-aligned ellipsoid | 5/5 (failures: 0) | 0.214 ms | 0.206–0.234 ms |

The differences describe this one small fixture only. The methods do not use the same candidate-score representation, so these numbers do not establish a general performance winner. The run was uncapped: no process-tree wall or memory limit was requested or enforced, and process-tree peak memory was not observed. The zonotope limiter profile is separate from the reported timing build and identifies `score_corners` as the main sampled CPU path for this workload. Profiling used GNU gprof 2.47, Release `-O3 -DNDEBUG -pg`, ten calls, and 10 ms sampling. See `limiter-profile.json`.

Five end-to-end report-data trials (solver run, exact rational checker, JSON serialization and SHA-256 verification) took median 0.992 s, range 0.970–1.011 s. Raw trials and output hashes are in `e2e-timing.json`.

The two phase-plane SVGs reuse the independently checked geometry figures from the [ellipsoid v2 bundle](../issue824-two-points-ellipsoid-minimax-v2/index.html) and [zonotope/parallelotope v2 bundle](../issue824-two-points-zonotope-minimax-v2/index.html). Those source records preserve forward/backward sets, intersections, selected plan replays and the finite RL adaptation limits.

## Reproduce

```sh
cmake --preset dev -DCSL_BUILD_ISSUE824_MATCHED_MINIMAX_REPORT=ON
cmake --build build/dev --target csl_issue824_matched_minimax_report --parallel 4
python3 scripts/reports/exp824/make_matched_minimax_report.py \
  build/dev/csl_issue824_matched_minimax_report build/dev \
  reports/algorithm-results/issue824-two-points-matched-minimax-v1
ctest --test-dir build/dev -R '^issue824_matched_minimax_report_smoke$' --output-on-failure
```

The input follows pinned upstream commit `f4d76c60f4003f50954174e96eafd8e514bd5441`. This report is a finite-action three-stage adaptation, not a reproduction of the continuous-action 10-second RL task.
