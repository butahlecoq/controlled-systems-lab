# Issue 824 TwoPoints ellipsoid minimax pilot

This bundle compares exact finite-catalog fixed-plan minimax, outer-box and zonotope selection, and a stagewise outer-ellipsoid selector on the three-stage `TwoPointsOnParallelLines` adaptation. It retains both player projections `(x1,x2)` and `(x3,x4)`, exact forward/backward geometry, intersections, and replayed trajectories. The model uses state `(x1,x2,x3,x4)`, initial state `(4.5,0,0,0)`, controls `(-2.5,0,2.5)`, disturbances `(-1,0,1)`, and terminal squared position gap.

The exact finite minimax value is `14.58094225`. The box-selected replay is `14.58094225`, the zonotope-selected replay is `14.58094225`, and the ellipsoid-selected replay is `14.58094225`. The ellipsoid selector scored all 27 fixed plans; its selected candidate support estimate is `15.55459769547920`.

The ellipsoid score uses a support upper-estimate formula for the stored axis-aligned ellipsoid and a numerical PSD check. It is not validated arithmetic or an optimality proof. The independent checker reconstructs each exact finite history using rational arithmetic and verifies full 4D membership in every plan's ellipsoid at every stage, then checks the selected plan's worst-history replay. A separate planar example visualizes the 2D propagation and exact corner membership.

This is a fixed open-loop finite-catalog comparison. It does not claim global minimax optimizer completeness, continuous-action RL reproduction, feedback optimality or a performance winner/speedup. Timings are descriptive and the limiter profile was unavailable. The stagewise geometry figure overlays the approximation projections with exact forward/backward sets and intersections from the separate MPC-05 finite adaptation report.

## Descriptive timings

The result contains one excluded warmup and seven order-rotated API-call measurements per method, including raw per-repetition durations and returned values. Fixture/request construction and JSON serialization are outside the measured interval; no algorithm workspace is reused. The same immutable request is used for all arms. The timing driver is single-threaded and deterministic, uses binary64 with the default absolute and relative tolerances of `1e-8`, and has no random seed. Timings are descriptive for this host and build only; no performance winner is claimed. `perf` and `strace` were unavailable, so the 884,736 factor-corner evaluations per zonotope call are reported as a known work count rather than a profiler-confirmed CPU limiter.

| Method | Median (ns) | Range (ns) |
| --- | ---: | ---: |
| exact_finite_minimax | 368,277 | 345,788–533,803 |
| outer_box_selector | 172,370 | 168,109–182,427 |
| zonotope_selector | 148,433,750 | 147,549,619–149,975,722 |
| ellipsoid_selector | 219,024 | 209,317–260,441 |


`capture.json` records host CPU/model/load, OS, Release compiler and flags, build generator and optional backend settings. The source commit is recorded separately from this measurement commit.

## Reproduce

Configure and build the Release driver from the repository root:

```sh
cmake --preset dev -DCSL_BUILD_ISSUE824_ELLIPSOID_MINIMAX_REPORT=ON
cmake --build build/dev --target csl_issue824_ellipsoid_minimax_report --parallel 4
python3 scripts/reports/exp824/make_ellipsoid_minimax_report.py \
  build/dev/csl_issue824_ellipsoid_minimax_report build/dev \
  reports/algorithm-results/issue824-two-points-ellipsoid-minimax-v1
```

Run the driver and its functional smoke check with:

```sh
ctest --test-dir build/dev -R '^issue824_ellipsoid_minimax_report_smoke$' --output-on-failure
```

`capture.json` records the clean source commit, source hashes, Release compiler and exact geometry reference. `result.json` stores all candidate scores and traces, selected-plan replays and timings. `check.json` preserves the rational finite-history inclusion checks. `projections.svg` shows both player phase planes. `ellipsoid-planar-example.html` documents the minimal two-state ellipsoid case.
