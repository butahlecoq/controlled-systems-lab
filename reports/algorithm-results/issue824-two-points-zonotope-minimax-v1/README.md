# Issue 824 TwoPoints zonotope minimax pilot

This bundle compares exact finite-catalog fixed-plan minimax, the existing outer-box selector, and candidate selection using stagewise outer zonotopes on the three-stage `TwoPointsOnParallelLines` adaptation. The model has state `(x1,x2,x3,x4)`, initial state `(4.5,0,0,0)`, controls `(-2.5,0,2.5)`, disturbances `(-1,0,1)`, and terminal squared position gap.

The exact finite minimax value is `14.58094225`. The box-selected plan replay is `14.58094225`. The zonotope-selected plan replay is `14.58094225`. The selected terminal zonotope's numerical factor-corner candidate score is `14.58094225000005`. The selector scored all 27 fixed plans. It evaluates every one of the 32,768 terminal factor corners for each plan under the explicit caller limit.

Candidate scores are numerical maxima over stored binary64 factor corners. They are not validated objective bounds. The selected finite plan has a separate exact finite-catalog replay score and worst-history witness. The checker reconstructs every exact state with integer transitions and rational costs. In four dimensions it checks every state coordinate against each candidate zonotope's coordinate bounds. It does not prove full four-dimensional zonotope membership. The planar companion has axis-aligned generators; its complete finite terminal-set inclusion follows from the independently checked coordinate bounds.

This is a fixed open-loop finite-catalog comparison. It does not claim global minimax optimizer completeness, continuous-action RL reproduction, feedback optimality, parallelotope or ellipsoid support, or a performance winner/speedup. The stagewise geometry figure also overlays exact forward/backward sets and intersections from the separate MPC-05 finite adaptation report.

## Descriptive timings

The result contains one excluded warmup and seven order-rotated API-call measurements per method, including raw per-repetition durations and returned values. Fixture/request construction and JSON serialization are outside the measured interval; no algorithm workspace is reused. The same immutable request is used for all arms. The timing driver is single-threaded and deterministic, uses binary64 with the default absolute and relative tolerances of `1e-8`, and has no random seed. Timings are descriptive for this host and build only; no performance winner is claimed. `perf` and `strace` were unavailable, so the 884,736 factor-corner evaluations per zonotope call are reported as a known work count rather than a profiler-confirmed CPU limiter.

| Method | Median (ns) | Range (ns) |
| --- | ---: | ---: |
| exact_finite_minimax | 349,348 | 345,437–435,462 |
| outer_box_selector | 182,217 | 170,064–194,719 |
| zonotope_selector | 153,271,274 | 151,687,195–155,751,981 |


`capture.json` records host CPU/model/load, OS, Release compiler and flags, build generator and optional backend settings. The source commit is recorded separately from this measurement commit.

## Reproduce

Configure and build the Release driver from the repository root:

```sh
cmake --preset dev -DCSL_BUILD_ISSUE824_ZONOTOPE_MINIMAX_REPORT=ON
cmake --build build/dev --target csl_issue824_zonotope_minimax_report --parallel 4
python3 scripts/reports/exp824/make_zonotope_minimax_report.py \
  build/dev/csl_issue824_zonotope_minimax_report build/dev \
  reports/algorithm-results/issue824-two-points-zonotope-minimax-v1
```

Run the driver and its functional smoke check with:

```sh
ctest --test-dir build/dev -R '^issue824_zonotope_minimax_report_smoke$' --output-on-failure
```

`capture.json` records the clean source commit, source hashes, Release compiler, and exact geometry reference. `result.json` stores all candidate scores and traces, the selected plan replay, the box baseline, the exact reference, and the 2D fixture. `check.json` preserves the exact replay checks and the limits of the 4D zonotope evidence. `projections.svg` shows both player phase planes. `planar-example.html` includes the minimal input, all candidate scores, the selected witness, and its independently checked 2D inclusion.
