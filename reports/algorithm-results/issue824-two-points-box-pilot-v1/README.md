# EXP-824 TwoPoints box minimax pilot

This exploratory bundle compares a stagewise four-dimensional interval-box selector with the exhaustive finite-catalog fixed-plan minimax reference for `TwoPointsOnParallelLines`. The adaptation has three 0.1-second stages, controls `(-2.5, 0, 2.5)`, disturbances `(-1, 0, 1)`, initial state `(4.5, 0, 0, 0)`, and terminal squared position gap.

The exact finite minimax value is `14.58094225`. The box-selected plan is `[-2.5, -2.5, -2.5]`; its full-catalogue replay is `14.58094225`, and its terminal box maximum is `14.58094225000008`. The selected box trace contains every exact finite-catalogue state at every stage according to the independent rational checker.

The box maximum is a numerical diagnostic over terminal box corners. This pilot does not claim validated objective bounds, continuous RL reproduction, feedback optimality, or support for ellipsoids, parallelotopes, and zonotopes. No performance measurement was collected. The figure combines this run's boxes and replay with exact forward/backward geometry from the separate MPC-05 finite adaptation report.

## Reproduce

From the repository root, configure and build the Release report driver:

```sh
cmake --preset dev -DCSL_BUILD_ISSUE824_BOX_REPORT=ON
cmake --build build/dev --target csl_issue824_box_minimax_report --parallel 4
python3 scripts/reports/exp824/make_report.py \
  --executable build/dev/csl_issue824_box_minimax_report \
  --build-dir build/dev \
  --output reports/algorithm-results/issue824-two-points-box-pilot-v1
```

Run the independent smoke check with:

```sh
ctest --test-dir build/dev -R '^issue824_box_minimax_report_smoke$' --output-on-failure
```

`capture.json` identifies the clean solver source commit, source hashes, build profile, and exact geometry reference. `check.json` records independent rational transitions, objective replay, and stage enclosure results. `result.json` stores every finite-plan score and the selected plan's worst-case disturbance path. `projections.svg` shows both player phase planes `(x1,x2)` and `(x3,x4)`.

This pilot is not the complete acceptance scope of issue #824. Publication through the site and a live URL check remain pending.
