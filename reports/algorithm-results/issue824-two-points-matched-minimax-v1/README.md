# Matched TwoPoints fixed-plan minimax run

This report compares the exact finite-polytope search and outer box, zonotope, fixed-frame parallelotope, and axis-aligned ellipsoid selectors on the pinned `TwoPointsOnParallelLines` source adaptation. It uses state `(x1,x2,x3,x4)`, initial `(4.5,0,0,0)`, horizon 3, control catalog `(-2.5, 0, 2.5)`, disturbance catalog `(-1, 0, 1)`, and terminal squared position gap. Re-expressing the pinned source's ten Euler substeps gives `x1'=x1+0.01x2+0.09u`, `x2'=u`, `x3'=x3+0.1x4+0.0045v`, and `x4'=x4+0.1v`; first-player damping resets its velocity to the selected input each outer step.

All methods received the same immutable request. Each scored all 27 action plans, and every selected plan was replayed across all 27 disturbance histories. Independent rational enumeration verified the exact minimax value and each replay. Approximation scores are numerical ranking estimates; no objective bound or global optimizer-family completeness is claimed.

## Timings

Release build, one warmup and five order-rotated measurements per method. The timed interval covers the public call and extraction/checking of its selected result. Fixture construction, serialization, independent rational checking, and plotting are excluded.

| Track | Runs | Median | Range |
| --- | ---: | ---: | ---: |
| Exact finite polytope | 5/5 | 0.441 ms | 0.413–0.448 ms |
| Outer box | 5/5 | 0.189 ms | 0.183–0.214 ms |
| Outer zonotope | 5/5 | 151.108 ms | 148.574–155.836 ms |
| Fixed-frame parallelotope | 5/5 | 0.703 ms | 0.686–0.705 ms |
| Axis-aligned ellipsoid | 5/5 | 0.218 ms | 0.210–0.224 ms |

The differences describe this one small fixture only. The methods do not use the same candidate-score representation, so these numbers do not establish a general performance winner. The zonotope limiter profile is separate from the reported timing build and identifies `score_corners` as the main sampled CPU path for this workload. Profiling used GNU gprof 2.47, Release `-O3 -DNDEBUG -pg`, ten calls, and 10 ms sampling. See `limiter-profile.json`.

Five end-to-end report-data trials (solver run, exact rational checker, JSON serialization and SHA-256 verification) took median 1.003 s, range 0.985–1.159 s. Raw trials and output hashes are in `e2e-timing.json`.

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
