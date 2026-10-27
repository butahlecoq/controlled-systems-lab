# Two points on parallel lines: minimax pilot

This is a source-attributed, finite-action pilot for the `TwoPointsOnParallelLines` differential game. The upstream state is `[time, position_1, velocity_1, position_2, velocity_2]`; the two projections are the players’ phase planes `(x1,x2)` and `(x3,x4)`.

## Model and adaptation

The source uses `alpha=1`, `m1=0.01`, `m2=1`, `dt=0.1 s`, ten explicit-Euler substeps per stage, and continuous control bounds `u ∈ [-2.5,2.5]`, `v ∈ [-1,1]`. Its horizon is 10 seconds and terminal reward is `-|position_1-position_2|`. The upstream repository does not declare a license; this pilot re-expresses the equations and does not copy source code.

The authored initial physical state is `(4.5,0,0,0)`. The pilot uses three stages (0.3 s), finite minimizing-control catalogue `{-2.5,0,2.5}`, and disturbance set `conv{-1,0,1}` at each stage. This adapts both the horizon and the control policy class; the solver chooses one open-loop control sequence before the adversary selects its disturbance sequence. It does not reproduce the continuous-control RL task.

The exact discrete map induced by the source’s explicit-Euler substeps is

```text
x1' = x1 + 0.01 x2 + 0.09 u
x2' = u
x3' = x3 + 0.1 x4 + 0.0045 v
x4' = x4 + 0.1 v
```

The source rewards larger terminal separation negatively. Minimizing the maximum squared separation preserves the minimizing plans and worst-case ordering because squaring is monotone on nonnegative gaps. The saved report still gives the worst absolute gap alongside the squared objective.

## Result

The numerical finite-action minimax solver exhausts all 27 control plans and all 27 disturbance-vertex histories per plan. It returns the unique minimizing control sequence `(-2.5,-2.5,-2.5)`, worst-case disturbance vertices `(-1,-1,-1)`, minimax squared gap `14.58094225`, and worst absolute gap `3.8185`.

An independent Python implementation replays the source’s ten Euler substeps, verifies every plan’s worst-case value and maximizing terminal state, and checks the unique minimizing plan. It builds the forward reachable polytopes for each control prefix by taking the convex hull of the disturbance-history vertices. The figure shows their exact two-dimensional projections. Separately, the backward recursion permits state-dependent controls over the finite vertex game; its nodes and forward/backward intersections are not complete continuous-disturbance predecessor sets and are not the fixed-plan solver’s output.

Seven single-threaded solver-call timings after one warmup are retained in `result.json`. Request construction and JSON output are outside the timed interval. No limiter profile, competing solver, or performance winner is included.

## Provenance and reproduction

- Upstream repository commit: [`f4d76c60f4003f50954174e96eafd8e514bd5441`](https://github.com/imm-rl-lab/optimal_control/tree/f4d76c60f4003f50954174e96eafd8e514bd5441)
- Source file blob: [`4e71bed8ceffa1990645fb85e54d6b5b1eeb688d`](https://github.com/imm-rl-lab/optimal_control/blob/f4d76c60f4003f50954174e96eafd8e514bd5441/Environments/TwoPointsOnParallelLines/TwoPointsOnParallelLines.py)
- CSL code commit, compiler and source fingerprints: `result.json`
- Standalone two-panel figure: [`projections.svg`](projections.svg)
- Rendered figure data and capture environment: `figure-data.json`, `capture.json`

Configure and run the smoke/renderer locally:

```sh
cmake -S . -B build/env717 -G 'Unix Makefiles' \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON \
  -DCSL_DEPENDENCY_PROBES=OFF -DCSL_BUILD_ENV717_REPORT=ON
cmake --build build/env717 --target csl_env717_two_points --parallel 4
python3 scripts/reports/env717/check_two_points.py \
  build/env717/csl_env717_two_points --output /tmp/env717-two-points
```

The bundle is descriptive evidence for this finite pilot. It is not a claim about continuous minimax control, feedback strategies, the full 10-second source horizon, or comparative solver performance.
