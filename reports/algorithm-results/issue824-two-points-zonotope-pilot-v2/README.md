# EXP-824 TwoPoints box and zonotope pilot

This exploratory bundle compares a stagewise four-dimensional interval-box fixed-plan selector with an outer zonotope recurrence of the same selected plan, alongside the exhaustive finite-catalog fixed-plan minimax reference for `TwoPointsOnParallelLines`. The adaptation has three 0.1-second stages, controls `(-2.5, 0, 2.5)`, disturbances `(-1, 0, 1)`, initial state `(4.5, 0, 0, 0)`, and terminal squared position gap.

The exact finite minimax value is `14.58094225`. The box-selected plan is `[-2.5, -2.5, -2.5]`; its full-catalogue replay is `14.58094225`, and its terminal box maximum is `14.58094225000008`. The zonotope recurrence propagates that same fixed plan and records center and generator matrices at all four state stages. The independent checker verifies every exact finite-catalogue state lies within the zonotope coordinate bounds; it does not certify full zonotope membership in four dimensions.

The box maximum is a numerical diagnostic over terminal box corners. The zonotope recurrence includes outward rounding slack and is a numerical outer enclosure. The companion planar example checks complete inclusion for a two-dimensional axis-aligned image. This pilot does not claim validated objective bounds, continuous RL reproduction, zonotope-based minimax selection, feedback optimality, or ellipsoid and non-box parallelotope propagation. No performance measurement was collected. The figure combines this run's box and zonotope projections and replay with exact forward/backward geometry from the separate MPC-05 finite adaptation report.

## Supported representation and cost

The implementation accepts bounded V-representation or singleton initial/disturbance sets and universal state constraints. For state dimension `n`, control dimension `m`, disturbance dimension `q`, horizon `H`, `A` actions per stage, and `P=A^H` plans, interval propagation costs `O(H n(n+m+q))` per plan. The terminal score enumerates `2^n` box corners and evaluates the objective at each; for quadratic objectives each evaluation costs `O(n^2)`. The selected plan is replayed over `R=|I|∏|D_k|` initial/disturbance histories at `O(R H n(n+m+q))` arithmetic cost. Overall work is `O(P[Hn(n+m+q)+2^n C_obj]+RHn(n+m+q))`, where `C_obj` is the cost of one objective evaluation.

Memory is `O(PH + Hn + 2^n n + K H n + ∑|D_k|q)` for saved plan scores, stage boxes, terminal corners, exact replay stages, and disturbance catalogues, where `K` is the per-stage exact-point limit. The witness search retains one path of length `H`; its history-count limit `R` bounds work rather than stored histories. Explicit caller limits bound plan count, exact points per stage, full replay histories, and terminal corners. Both action-plan and corner enumeration are exponential in horizon and state dimension, respectively; this four-state, three-stage example does not establish practical scaling beyond this fixture.

The zonotope recurrence itself keeps `G_k` state generators, `W_k` disturbance generators, and adds at most `n` outward-rounding generators at each `n`-state stage. One step costs `O(n²G_k + nqW_k + n(n+m+q))` arithmetic operations and stores `O(n(G_k+W_k+n))` generator values; the full trace stores `O(HnK)` values under the caller's per-stage generator cap `K`. No generator reduction is performed: a stage that would exceed `K` returns `Unsupported`. These are operation-count estimates, not measured performance claims.

## Reproduce

From the repository root, configure and build the Release report driver:

```sh
cmake --preset dev -DCSL_BUILD_ISSUE824_BOX_REPORT=ON
cmake --build build/dev --target csl_issue824_box_minimax_report --parallel 4
python3 scripts/reports/exp824/make_report.py \
  --executable build/dev/csl_issue824_box_minimax_report \
  --build-dir build/dev \
  --output reports/algorithm-results/issue824-two-points-zonotope-pilot-v2
```

Run the independent smoke check with:

```sh
ctest --test-dir build/dev -R '^issue824_box_minimax_report_smoke$' --output-on-failure
```

`capture.json` identifies the solver source commit, source hashes, build profile, and exact geometry reference. `check.json` records independent rational transitions, objective replay, and stage coordinate checks. `result.json` stores every finite-plan score, the selected plan's worst-case disturbance path, the TwoPoints zonotope stages, and the planar fixture. `projections.svg` shows exact reachable and backward-winning sets, intersections, boxes, true zonotope projections, and trajectories in both player phase planes `(x1,x2)` and `(x3,x4)`. `planar-example.svg` and `planar-example.html` provide the complete supported 2D example and analytic inclusion check.

This pilot is not the complete acceptance scope of issue #824. The report workflow stages the versioned bundle and its 2D companion in the published Pages gallery; check the PR and issue discussion for the verified live URL after main-only deployment.
