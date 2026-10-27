# Stage projection demonstrations

Run the fuel and nonfuel demonstrations through the same saved-batch validator
and offline figure renderer:

```sh
python3 -m venv build/stage-projection-venv
build/stage-projection-venv/bin/python -m pip install -r scripts/reports/requirements.txt
build/stage-projection-venv/bin/python benchmarks/reporting/stage-projection/prepare_demos.py \
  --out build/stage-projection-demo
```

The command prints absolute paths for each saved batch, SVG, PNG, and local HTML
index. Open either `fuel-four-state-figures/index.html` or
`nonfuel-integrator-figures/index.html` under the output directory. The batch
files are validated with their exact source SHA-256 before rendering. The
renderer reads only those saved batches; it does not call a solver, route, or
geometry provider. Use a new `--out` directory for each run; existing output is
never overwritten.

The checked-in [v1 demonstration bundle](bundle-v1/README.md)
contains the generated figures, offline indexes, saved batches, manifest, and
checksums.

## Fuel model

`examples/fuel-four-state.json` defines a four-state affine model using the
owner-confirmed B06/L09 flow and stock equations, with an independent control
interval `[-1,1]` at each of five stages and zero disturbance. This is a
standalone illustrative open-loop reachability case. It is not the B06 minimax
result, a historical reproduction, or benchmark data. All control-box endpoint
histories are propagated, and their state points are retained as V generators.
The figure shows these generators at every stage. It does not draw a filled
boundary or claim the stored points are all exposed extreme points. Negative
fuel stock values are preserved.

The four requested coordinate views are:

- flow/flow: oxidizer flow `x1` against fuel flow `x3`;
- stock/stock: oxidizer stock `x2` against fuel stock `x4`;
- oxidizer flow `x1` against fuel stock `x4`;
- oxidizer stock `x2` against fuel flow `x3`.

The green dashed path is the declared fixed control `u=1` at every stage. It
is an illustrative trajectory, separate from the reachable-set V generators;
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
expanded into missing stages. The demonstration route provides a complete
stage sequence for both examples. It is an analytic demo adapter; the existing
`nominal_forward` route's per-stage results are documented but are not yet
connected to this command, so issue #713 remains open for that integration.
Existing frozen four-state terminal figures
remain available in the [B06 bundle](../../../reports/algorithm-results/b06-owner-confirmed-7df01ba3af5e4c46/terminal-projections.svg),
[B07 bundle](../../../reports/algorithm-results/b07-owner-approved-eight-case-v1/projections.svg),
and [B09 bundle](../../../reports/algorithm-results/b09-a08-source-reference-4818ddde/projections-lambda0.svg).
