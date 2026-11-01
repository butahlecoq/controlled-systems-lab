# Issue 824 TwoPoints zonotope minimax pilot

This bundle compares exact finite-catalog fixed-plan minimax, the existing outer-box selector, and candidate selection using stagewise outer zonotopes on the three-stage `TwoPointsOnParallelLines` adaptation. The model has state `(x1,x2,x3,x4)`, initial state `(4.5,0,0,0)`, controls `(-2.5,0,2.5)`, disturbances `(-1,0,1)`, and terminal squared position gap.

The exact finite minimax value is `14.58094225`. The box-selected plan replay is `14.58094225`. The zonotope-selected plan replay is `14.58094225`. The selected terminal zonotope's numerical factor-corner candidate score is `14.58094225000005`. The selector scored all 27 fixed plans. It evaluates every one of the 32,768 terminal factor corners for each plan under the explicit caller limit.

Candidate scores are numerical maxima over stored binary64 factor corners. They are not validated objective bounds. The selected finite plan has a separate exact finite-catalog replay score and worst-history witness. The checker reconstructs every exact state with integer transitions and rational costs. In four dimensions it checks every state coordinate against each candidate zonotope's coordinate bounds. It does not prove full four-dimensional zonotope membership. The planar companion has axis-aligned generators; its complete finite terminal-set inclusion follows from the independently checked coordinate bounds.

This is a fixed open-loop finite-catalog comparison. It does not claim global minimax optimizer completeness, continuous-action RL reproduction, feedback optimality, parallelotope or ellipsoid support, or performance results. The stagewise geometry figure also overlays exact forward/backward sets and intersections from the separate MPC-05 finite adaptation report.

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
