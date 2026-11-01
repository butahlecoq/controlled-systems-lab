# Issue 824 TwoPoints zonotope minimax pilot

This bundle compares exact finite-catalog fixed-plan minimax, the outer-box selector, stagewise zonotope candidate selection, and stagewise fixed-frame parallelotope candidate selection on the three-stage `TwoPointsOnParallelLines` adaptation. The model has state `(x1,x2,x3,x4)`, initial state `(4.5,0,0,0)`, controls `(-2.5,0,2.5)`, disturbances `(-1,0,1)`, and terminal squared position gap.

The exact finite minimax value is `14.58094225`. The box-selected plan replay is `14.58094225`. The zonotope-selected plan replay is `14.58094225`. The selected terminal zonotope's numerical factor-corner candidate score is `14.58094225000005`. The parallelotope-selected plan replay is `14.58094225` with frame-box corner score `31.62296496490081`. Both approximation selectors scored all 27 fixed plans.

Candidate scores are numerical maxima over stored binary64 enclosure corners. They are not validated objective bounds. Each selected finite plan has a separate exact finite-catalog replay score and worst-history witness. The checker reconstructs every exact state with integer transitions and rational costs. It interprets each zonotope's stored binary64 center and generators as exact dyadic rationals, reduces to the exact affine span, and checks all facet inequalities for every finite-history state. It also transforms every exact state into each parallelotope candidate's frame bounds.

This is a fixed open-loop finite-catalog comparison. The fixed-frame parallelotope is a selected orientation, not an orientation optimizer. The report does not claim global minimax optimizer completeness, continuous-action RL reproduction, feedback optimality, ellipsoid support, or a performance winner/speedup. The stagewise geometry figure also overlays exact forward/backward sets and intersections from the separate MPC-05 finite adaptation report.

## Descriptive timings

The result contains one excluded warmup and seven order-rotated API-call measurements per method, including raw per-repetition durations and returned values. Fixture/request construction and JSON serialization are outside the measured interval; no algorithm workspace is reused. The same immutable request is used for all arms. The timing driver is single-threaded and deterministic, uses binary64 with the default absolute and relative tolerances of `1e-8`, and has no random seed. Timings are descriptive for this host and build only; no performance winner is claimed. `perf` and `strace` were unavailable, so corner counts are known work counts rather than profiler-confirmed CPU limiters.

| Method | Median (ns) | Range (ns) |
| --- | ---: | ---: |
| exact_finite_minimax | 358,777 | 344,460–438,257 |
| outer_box_selector | 175,094 | 173,277–214,763 |
| zonotope_selector | 152,769,650 | 151,012,569–155,381,106 |
| parallelotope_selector | 153,927,767 | 151,730,334–155,598,035 |


`capture.json` records host CPU/model/load, OS, Release compiler and flags, build generator and optional backend settings. The source commit is recorded separately from this measurement commit.

## Reproduce

Configure and build the Release driver from the repository root:

```sh
cmake --preset dev -DCSL_BUILD_ISSUE824_ZONOTOPE_MINIMAX_REPORT=ON
cmake --build build/dev --target csl_issue824_zonotope_minimax_report --parallel 4
python3 scripts/reports/exp824/make_zonotope_minimax_report.py \
  build/dev/csl_issue824_zonotope_minimax_report build/dev \
  reports/algorithm-results/issue824-two-points-zonotope-minimax-v2
```

Run the driver and its functional smoke check with:

```sh
ctest --test-dir build/dev -R '^issue824_zonotope_minimax_report_smoke$' --output-on-failure
```

`capture.json` records the clean source commit, source hashes, Release compiler, and exact geometry reference. `result.json` stores all candidate scores and traces, the selected plan replay, the box baseline, the exact reference, and the 2D fixture. `check.json` verifies exact finite-state membership in every stored 4D zonotope and preserves the limits of the objective-score evidence. `projections.svg` shows both player phase planes. `planar-example.html` includes the minimal input, all candidate scores, the selected witness, and its independently checked 2D inclusion.
