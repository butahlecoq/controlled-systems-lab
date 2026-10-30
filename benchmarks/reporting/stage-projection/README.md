# Stage projection demonstrations

Build the native nominal-forward adapter, then run both demonstrations through
the same capture, saved-batch validator, and offline figure renderer:

```sh
cmake -S . -B build/stage-projection-route-build -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TESTING=OFF -DCSL_BUILD_STAGE_PROJECTION_ROUTE=ON
cmake --build build/stage-projection-route-build --target csl_stage_projection_route -j2
python3 -m venv build/stage-projection-venv
build/stage-projection-venv/bin/python -m pip install -r scripts/reports/requirements.txt
build/stage-projection-venv/bin/python benchmarks/reporting/stage-projection/prepare_demos.py \
  --out build/stage-projection-demo
```

The command prints absolute paths for each saved batch, SVG, PNG, and local HTML
index. Open either `fuel-four-state-figures/index.html` or
`nonfuel-integrator-figures/index.html` under the output directory. The batch
files are validated with their exact source SHA-256 before rendering. The
renderer reads only those saved batches; it does not call the route or geometry
providers. Use a new `--out` directory for each run; existing output is
never overwritten. The native route batch records missing or failed stages
explicitly. The full R0–R5 fuel figure uses a separate analytic demonstration
batch and does not fill or replace the native route's unavailable stages.

The checked-in [v2 demonstration bundle](bundle-v2/README.md) contains the
corrected fuel phase planes alongside the flow/flow and stock/stock views,
generated figures, offline indexes, saved batches, manifest, and checksums.
The earlier [v1 bundle](bundle-v1/README.md) is retained unchanged for
provenance; use v2 for the requested coordinate pairs.

The fuel model is a plant-specific open-loop projection example. For the
reachability/minimax algorithm showcase from the RL environment suite, see the
published [TwoPointsOnParallelLines fixed-plan report](https://butahlecoq.github.io/controlled-systems-lab/env717-two-points-33ebdad360671940fb54/index.html)
and [finite-feedback report](https://butahlecoq.github.io/controlled-systems-lab/env717-two-points-4fbedf73c6f198fd57e2/index.html).
They plot both player phase planes `(x1,x2)` and `(x3,x4)`, with forward sets,
backward-winning intersections, and a replayed minimax path. The reports use a
short finite-catalogue adaptation, not the original continuous-action RL task.

## Fuel model

`examples/fuel-four-state.json` runs a four-state affine model using the
B06/L09 flow and stock coupling, with an independent scalar control in
`[-1,1]` at each of five stages and zero disturbance. This is a
standalone illustrative open-loop reachability case. It is not the B06 minimax
result, a historical reproduction, or benchmark data. The native
`nominal_forward` route batch is saved separately with per-stage evidence and
explicit provider gaps; H/V conversion stops at R2 on affine-rank ambiguity for
this scalar-control case. A source-bound evidence sidecar retains each available
marginal's OperationResult evidence, H-to-V conversion evidence, and provider
lineage. The full figure is the separate analytic
demonstration. It does not draw a filled boundary or claim its plotted points
are all exposed extreme points. Negative fuel stock values are preserved.

The four requested coordinate views are:

- oxidizer phase plane: flow `x1` against stock `x2`;
- fuel phase plane: flow `x3` against stock `x4`;
- flow/flow: oxidizer flow `x1` against fuel flow `x3`;
- stock/stock: oxidizer stock `x2` against fuel stock `x4`.

The green dashed path is the declared fixed control `u=1` at every stage. It
is an illustrative trajectory, separate from the reachable-set vertices;
it is not optimized. Stage panels mark `R0` and `RT` and use independent scales.

## Nonfuel model

`examples/nonfuel-integrator.json` is a planar discrete integrator with a
bounded scalar control. It uses the same affine propagation, batch schema,
validator, style, and offline renderer as the fuel model.

## Route capability boundaries

[`stage_projection_route_capabilities.json`](../../../scripts/reports/stage_projection_route_capabilities.json)
records current route outputs and their limits. In particular, B06 saved data
contains terminal geometry but no intermediate stage sets, and B09 replay
states are trajectories rather than set marginals. Neither is silently
expanded into missing stages. The native `nominal_forward` batch records its
available fuel prefix and unavailable suffix. The full fuel figures come from
the separately identified analytic demonstration; nonfuel uses the same
demonstration adapter.
Existing frozen four-state terminal figures
remain available in the [B06 bundle](../../../reports/algorithm-results/b06-owner-confirmed-7df01ba3af5e4c46/terminal-projections.svg),
[B07 bundle](../../../reports/algorithm-results/b07-owner-approved-eight-case-v1/projections.svg),
and [B09 bundle](../../../reports/algorithm-results/b09-a08-source-reference-4818ddde/projections-lambda0.svg).
