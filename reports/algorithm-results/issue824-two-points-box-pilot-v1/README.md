# EXP-824 TwoPoints box minimax pilot

This exploratory bundle compares a stagewise four-dimensional interval-box selector with the exhaustive finite-catalog fixed-plan minimax reference for `TwoPointsOnParallelLines`. The adaptation has three 0.1-second stages, controls `(-2.5, 0, 2.5)`, disturbances `(-1, 0, 1)`, initial state `(4.5, 0, 0, 0)`, and terminal squared position gap.

The exact finite minimax value is `14.58094225`. The box-selected plan is `[-2.5, -2.5, -2.5]`; its full-catalogue replay is `14.58094225`, and its terminal box maximum is `14.58094225000008`. The selected box trace contains every exact finite-catalogue state at every stage according to the independent rational checker.

The box maximum is a numerical diagnostic over terminal box corners. This pilot does not claim validated objective bounds, continuous RL reproduction, feedback optimality, or support for ellipsoids, parallelotopes, and zonotopes. No performance measurement was collected. The figure combines this run's boxes and replay with exact forward/backward geometry from the separate MPC-05 finite adaptation report.

## Supported representation and cost

The implementation accepts bounded V-representation or singleton initial/disturbance sets and universal state constraints. For state dimension `n`, control dimension `m`, disturbance dimension `q`, horizon `H`, `A` actions per stage, and `P=A^H` plans, interval propagation costs `O(H n(n+m+q))` per plan. The terminal score enumerates `2^n` box corners and evaluates the objective at each; for quadratic objectives each evaluation costs `O(n^2)`. The selected plan is replayed over `R=|I|∏|D_k|` initial/disturbance histories at `O(R H n(n+m+q))` arithmetic cost. Overall work is `O(P[Hn(n+m+q)+2^n C_obj]+RHn(n+m+q))`, where `C_obj` is the cost of one objective evaluation.

Memory is `O(PH + Hn + 2^n n + K H n + ∑|D_k|q)` for saved plan scores, stage boxes, terminal corners, exact replay stages, and disturbance catalogues, where `K` is the per-stage exact-point limit. The witness search retains only one path of length `H`; its history-count limit `R` bounds work rather than stored histories. Explicit caller limits bound plan count, exact points per stage, full replay histories, and terminal corners. Both action-plan and corner enumeration are exponential in horizon and state dimension, respectively; the four-state, three-stage example does not establish practical scaling beyond this fixture.

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
